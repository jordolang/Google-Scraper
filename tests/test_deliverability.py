"""Sending-side checks: the MIME message, plain text, Resend, DNS, image host."""

from unittest import mock

import pytest

import deliverability
import image_host
import send_emails

HTML = """<html><head><style>p{}</style></head><body>
<div style="display:none;max-height:0;">hidden preheader</div>
<table><tr><td><p>Hi Bright Spark team,</p>
<p>The site is <strong>$400</strong>
  (normally $499).</p>
<a href="https://jlang.dev/promo">See what I'd build</a>
<img src="https://x/y.png" alt="preview"></td></tr></table></body></html>"""


# --------------------------------------------------------------- message
def test_html_to_text_is_readable():
    text = send_emails.html_to_text(HTML)
    assert "hidden preheader" not in text
    assert "The site is $400 (normally $499)." in text
    assert "See what I'd build (https://jlang.dev/promo)" in text
    assert "p{}" not in text


def test_build_message_has_both_parts_and_the_headers_inboxes_check():
    msg = send_emails.build_message(
        from_name="Jordan Lang", from_email="jordan@jlang.dev", to_email="a@b.com",
        subject="Hi", html=HTML, reply_to="r@jlang.dev",
        unsubscribe_url="https://jlang.dev/unsub")
    assert msg["From"] == "Jordan Lang <jordan@jlang.dev>"
    assert msg["Message-ID"].endswith("@jlang.dev>")
    assert msg["Date"]
    assert msg["Reply-To"] == "r@jlang.dev"
    assert msg["List-Unsubscribe"] == (
        "<https://jlang.dev/unsub>, <mailto:jordan@jlang.dev?subject=Unsubscribe>")
    assert msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    types = [part.get_content_type() for part in msg.iter_parts()]
    assert types == ["text/plain", "text/html"]


def test_mailto_only_unsubscribe_has_no_one_click_header():
    msg = send_emails.build_message(
        from_name="", from_email="jordan@jlang.dev", to_email="a@b.com",
        subject="Hi", html=HTML)
    assert msg["List-Unsubscribe"] == "<mailto:jordan@jlang.dev?subject=Unsubscribe>"
    assert msg["List-Unsubscribe-Post"] is None


def test_resend_sender_posts_html_text_and_headers():
    sender = send_emails.ResendSender(from_email="jordan@jlang.dev", from_name="Jordan Lang",
                                      reply_to="r@jlang.dev")
    assert not sender.connect("not-a-key")
    assert sender.connect("re_123")
    sender._session = mock.Mock()
    sender._session.post.return_value = mock.Mock(status_code=200)
    assert sender.send_email("a@b.com", "Hi", HTML, "Bright Spark")
    url = sender._session.post.call_args.args[0]
    payload = sender._session.post.call_args.kwargs["json"]
    assert url == send_emails.RESEND_API_URL
    assert payload["to"] == ["a@b.com"] and payload["reply_to"] == "r@jlang.dev"
    assert payload["text"].startswith("Hi Bright Spark team,")
    assert "List-Unsubscribe" in payload["headers"]


def test_resend_failure_is_counted_not_raised():
    sender = send_emails.ResendSender(from_email="jordan@jlang.dev")
    sender.connect("re_123")
    sender._session = mock.Mock()
    sender._session.post.return_value = mock.Mock(
        status_code=403, json=lambda: {"message": "domain not verified"})
    assert not sender.send_email("a@b.com", "Hi", HTML, "Bright Spark")
    assert sender.failed_count == 1
    assert "domain not verified" in sender.failed_emails[0][2]


def test_pipeline_picks_resend_when_asked(tmp_path):
    from tui.pipeline import LivePipeline

    assert isinstance(LivePipeline(send_via="resend", data_root=tmp_path)._sender(),
                      send_emails.ResendSender)
    sender = LivePipeline(data_root=tmp_path, from_name="Pat")._sender()
    assert type(sender) is send_emails.EmailSender and sender.from_name == "Pat"


# --------------------------------------------------------------- DNS
def _resolver(records):
    return lambda name, kind: records.get((name, kind), [])


def test_check_domain_all_good_for_icloud():
    records = {
        ("jlang.dev", "MX"): ["10 mx01.mail.icloud.com."],
        ("jlang.dev", "TXT"): ["v=spf1 include:icloud.com ~all"],
        ("sig1._domainkey.jlang.dev", "TXT"): ["v=DKIM1; k=rsa; p=MIGf"],
        ("_dmarc.jlang.dev", "TXT"): ["v=DMARC1; p=quarantine"],
    }
    checks = deliverability.check_domain("jordan@jlang.dev", smtp_server="smtp.mail.me.com",
                                         resolve=_resolver(records))
    assert [c.status for c in checks] == ["pass"] * 4
    assert deliverability.summary(checks).startswith("All set")


def test_check_domain_explains_what_is_missing():
    records = {("jlang.dev", "MX"): ["10 mx01.mail.icloud.com."]}
    checks = {c.name: c for c in deliverability.check_domain(
        "jlang.dev", resolve=_resolver(records))}
    assert checks["SPF"].status == "fail" and "include:icloud.com" in checks["SPF"].fix
    assert checks["DKIM"].status == "fail" and "sig1" in checks["DKIM"].fix
    assert checks["DMARC"].status == "fail" and "_dmarc.jlang.dev" in checks["DMARC"].fix
    assert "Fix before sending" in deliverability.summary(list(checks.values()))


def test_check_domain_flags_two_spf_records_and_a_missing_include():
    records = {("x.com", "TXT"): ["v=spf1 a ~all", "v=spf1 mx ~all"]}
    spf = [c for c in deliverability.check_domain(
        "x.com", smtp_server="smtp.gmail.com", resolve=_resolver(records)) if c.name == "SPF"]
    assert spf[0].status == "fail" and "2 SPF records" in spf[0].detail
    records = {("x.com", "TXT"): ["v=spf1 a ~all"]}
    spf = [c for c in deliverability.check_domain(
        "x.com", smtp_server="smtp.gmail.com", resolve=_resolver(records)) if c.name == "SPF"]
    assert spf[0].status == "warn" and "_spf.google.com" in spf[0].fix


def test_resend_spf_lives_on_the_send_subdomain():
    records = {("send.x.com", "TXT"): ["v=spf1 include:amazonses.com ~all"],
               ("resend._domainkey.x.com", "TXT"): ["p=MIGf"]}
    checks = {c.name: c for c in deliverability.check_domain(
        "x.com", send_via="resend", resolve=_resolver(records))}
    assert checks["SPF"].status == "pass" and checks["DKIM"].status == "pass"


def test_free_mailbox_gets_advice_not_dns():
    (check,) = deliverability.check_domain("someone@gmail.com", resolve=_resolver({}))
    assert check.status == "warn" and "own domain" in check.fix


# --------------------------------------------------------------- images
TOKEN = "vercel_blob_rw_Store123_fakesecret"


class FakeBlob:
    """Just enough of the Vercel Blob API: PUT stores, GET lists."""

    def __init__(self, status=200, text=""):
        self.calls = []
        self.status = status
        self.text = text

    def request(self, method, url, params=None, timeout=None, data=None, headers=None):
        self.calls.append(dict(method=method, url=url, params=params, data=data,
                               headers=headers))
        if self.status >= 300:
            return mock.Mock(status_code=self.status, text=self.text)
        path = params["pathname"]
        body = {"url": f"https://store123.public.blob.vercel-storage.com/{path}",
                "pathname": path}
        return mock.Mock(status_code=200, json=lambda: body, text="")


def test_image_host_uploads_and_returns_the_public_url(tmp_path):
    image = tmp_path / "Shop Front.PNG"
    image.write_bytes(b"\x89PNG fake")
    host = image_host.ImageHost(token=TOKEN, folder="email-images")
    fake = host.store._session = FakeBlob()
    url = host.upload_file(image)
    call = fake.calls[0]
    path = call["params"]["pathname"]
    assert call["method"] == "PUT" and call["url"] == "https://vercel.com/api/blob/"
    assert path.startswith("email-images/") and path.endswith(".png")
    assert "shop-front-" in path
    assert url == f"https://store123.public.blob.vercel-storage.com/{path}"
    headers = call["headers"]
    assert headers["authorization"] == f"Bearer {TOKEN}"
    assert headers["x-vercel-blob-store-id"] == "Store123"
    assert headers["x-vercel-blob-access"] == "public"
    assert headers["x-content-type"] == "image/png"
    assert headers["x-add-random-suffix"] == "0"
    assert host.identity == "vercel-blob:Store123"


def test_image_host_reads_the_token_from_the_environment(monkeypatch):
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", f'"{TOKEN}"')
    assert image_host.ImageHost().configured()
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "sb_secret_from_supabase")
    assert not image_host.ImageHost().configured()


def test_image_host_explains_its_failures(tmp_path, monkeypatch):
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    image = tmp_path / "a.png"
    image.write_bytes(b"x")
    with pytest.raises(image_host.ImageHostError, match="not set up"):
        image_host.ImageHost().upload_file(image)
    bad = tmp_path / "a.bmp"
    bad.write_bytes(b"x")
    host = image_host.ImageHost(token=TOKEN)
    with pytest.raises(image_host.ImageHostError, match="PNG, JPG"):
        host.upload_file(bad)
    with pytest.raises(image_host.ImageHostError, match="does not exist"):
        host.upload_file(tmp_path / "missing.png")
    host.store._session = FakeBlob(status=403, text="Access denied, please provide a valid token")
    with pytest.raises(image_host.ImageHostError, match="refused the token"):
        host.upload_file(image)


def test_image_host_maps_status_codes_to_fixes():
    assert "vercel_blob_rw_" in image_host.explain(401, "")
    assert "Public access" in image_host.explain(403, "Cannot use public access on a private store")
    assert "Storage" in image_host.explain(404, "store_not_found")
    assert "wait a minute" in image_host.explain(429, "")
