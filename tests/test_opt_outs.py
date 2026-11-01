"""Per-recipient unsubscribe links and skipping people who used them."""

from unittest import mock

import pytest

import opt_outs
import send_emails
from tui.models import Business, EmailMessage
from tui.pipeline import LivePipeline

SITE = "https://lead-optout.vercel.app"
TOKEN = "vercel_blob_rw_Store123_fakesecret"
SIGNING_KEY = "k1"


class FakeBlobList:
    """The Vercel Blob list endpoint over a set of stored pathnames, in pages."""

    def __init__(self, page_size=2, status=200):
        self.paths = set()
        self.page_size = page_size
        self.status = status
        self.calls = []

    def unsubscribe(self, email):
        """What the vercel/ function stores when ``email`` clicks their link."""
        self.paths.add(f"optouts/{opt_outs.fingerprint(email)}.json")

    def request(self, method, url, params=None, timeout=None, headers=None, **_):
        self.calls.append((method, params, headers))
        if self.status >= 300:
            return mock.Mock(status_code=self.status, text="Access denied")
        assert method == "GET" and params["prefix"] == "optouts/"
        names = sorted(p for p in self.paths if p.startswith(params["prefix"]))
        start = int(params.get("cursor") or 0)
        chunk = names[start:start + self.page_size]
        more = start + self.page_size < len(names)
        body = {"blobs": [{"pathname": p} for p in chunk],
                "hasMore": more, "cursor": str(start + self.page_size) if more else None}
        return mock.Mock(status_code=200, json=lambda: body, text="")


def make_list(blobs=None, secret=SIGNING_KEY, url=SITE):
    optouts = opt_outs.OptOutList(url=url, secret=secret, token=TOKEN)
    optouts.store._session = blobs or FakeBlobList()
    return optouts


def test_each_recipient_gets_their_own_stable_signed_link():
    link = make_list().link_for("Owner@Shop.com ")
    digest = opt_outs.fingerprint("owner@shop.com")
    assert link == (f"{SITE}/api/unsubscribe?h={digest}"
                    f"&s={opt_outs.sign(SIGNING_KEY, digest)}")
    # The address itself never appears in the link.
    assert "owner" not in link and "shop.com" not in link
    # A later campaign makes the same link; another address a different one.
    assert make_list().link_for("owner@shop.com") == link
    assert make_list().link_for("info@bakery.com") != link
    # Another secret signs differently, so links can't be forged without it.
    assert make_list(secret="other").link_for("owner@shop.com") != link


def test_signature_matches_the_vercel_function():
    # The same vector is checked in vercel/test/unsubscribe.test.js.
    digest = opt_outs.fingerprint("Owner@Shop.com ")
    assert digest == "231af1e209e7597ff54ab1b3fc35b00c961f870a0220dbe351166d2f6d3f3296"
    assert opt_outs.sign("k1", digest) == "68120365eee8e58a1ef4f290cf0d6c24"


def test_making_links_needs_no_network():
    blobs = FakeBlobList()
    make_list(blobs).link_for("a@b.com")
    assert blobs.calls == []


def test_opted_out_reports_only_unsubscribed_addresses_across_pages():
    blobs = FakeBlobList(page_size=2)
    for email in ("gone@x.com", "other1@y.com", "other2@y.com", "other3@y.com"):
        blobs.unsubscribe(email)
    optouts = make_list(blobs)
    assert optouts.opted_out(["GONE@x.com", "still@x.com", "new@x.com", ""]) == {"gone@x.com"}
    assert len(blobs.calls) == 2  # followed the cursor to the second page
    assert blobs.calls[0][2]["authorization"] == f"Bearer {TOKEN}"


def test_nothing_to_check_means_no_request():
    blobs = FakeBlobList()
    assert make_list(blobs).opted_out(["", "  "]) == set()
    assert blobs.calls == []


def test_unreadable_list_is_an_error_not_an_empty_list():
    with pytest.raises(opt_outs.OptOutError, match="refused the token"):
        make_list(FakeBlobList(status=403)).opted_out(["a@b.com"])


@pytest.mark.parametrize("url,secret", [("", SIGNING_KEY), (SITE, ""), ("http://x", SIGNING_KEY)])
def test_incomplete_setup_says_so(url, secret, monkeypatch):
    monkeypatch.delenv(opt_outs.URL_ENV, raising=False)
    monkeypatch.delenv(opt_outs.SECRET_ENV, raising=False)
    optouts = make_list(url=url, secret=secret)
    assert not optouts.configured()
    with pytest.raises(opt_outs.OptOutsNotSetUp):
        optouts.link_for("a@b.com")


def test_new_secrets_are_long_and_different():
    first, second = opt_outs.new_secret(), opt_outs.new_secret()
    assert first != second and len(first) >= 40


# ----------------------------------------------------------------- pipeline
@pytest.fixture
def pipeline(tmp_path):
    pipe = LivePipeline(data_root=tmp_path, unsubscribe_site=SITE,
                        templates_dir="email_templates")
    blobs = FakeBlobList()
    pipe._opt_out_list = make_list(blobs)
    pipe._opt_outs_missing = False
    pipe.blobs = blobs
    return pipe


def test_email_carries_the_recipients_link_in_footer_and_header(pipeline):
    business = Business(name="Bright Spark", category="Electrician",
                        emails=["owner@brightspark.com"])
    msg = pipeline.build_message(business)
    digest = opt_outs.fingerprint("owner@brightspark.com")
    assert msg.unsubscribe_url.startswith(f"{SITE}/api/unsubscribe?h={digest}&s=")
    assert f'href="{msg.unsubscribe_url}"' in msg.html.replace("&amp;", "&")

    sender = send_emails.ResendSender(from_email="jordan@jlang.dev")
    sender.connect("re_123")
    sender._session = mock.Mock()
    sender._session.post.return_value = mock.Mock(status_code=200)
    sender.send_email(msg.to_email, msg.subject, msg.html, "Bright Spark",
                      unsubscribe_url=msg.unsubscribe_url)
    headers = sender._session.post.call_args.kwargs["json"]["headers"]
    assert headers["List-Unsubscribe"].startswith(f"<{msg.unsubscribe_url}>")
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


def test_unsubscribed_recipients_are_skipped(pipeline):
    messages = [
        EmailMessage(business=Business(name=name), to_email=email, subject="s", html="h")
        for name, email in [("Gone", "gone@x.com"), ("Here", "here@x.com")]
    ]
    pipeline.blobs.unsubscribe("gone@x.com")
    sent = []
    fake_sender = mock.Mock(smtp_server="s", smtp_port=1)
    fake_sender.connect.return_value = True
    fake_sender.send_email.side_effect = lambda to, *a, **k: sent.append(to) or True
    with mock.patch.object(LivePipeline, "_sender", return_value=fake_sender), \
            mock.patch("tui.pipeline.time.sleep"):
        stats = pipeline.send(messages, password="pw")
    assert sent == ["here@x.com"]
    assert stats["skipped"] == 1 and stats["sent"] == 1


def test_send_stops_if_the_unsubscribe_list_cannot_be_read(pipeline):
    pipeline.blobs.status = 500
    msg = EmailMessage(business=Business(name="A"), to_email="a@x.com", subject="s", html="h")
    fake_sender = mock.Mock()
    with mock.patch.object(LivePipeline, "_sender", return_value=fake_sender):
        stats = pipeline.send([msg], password="pw")
    assert stats["sent"] == 0 and "unsubscribe" in stats["error"]
    fake_sender.connect.assert_not_called()


def test_without_the_site_emails_fall_back_to_the_shared_link(pipeline):
    pipeline._opt_out_list = make_list(url="")
    pipeline.unsubscribe_url = "https://jlang.dev/unsubscribe"
    msg = pipeline.build_message(Business(name="A", emails=["a@x.com"]))
    assert msg.unsubscribe_url == ""
    assert 'href="https://jlang.dev/unsubscribe"' in msg.html


def test_test_send_goes_only_to_you_and_logs_nothing(pipeline):
    business = Business(name="Bright Spark", category="Electrician",
                        emails=["owner@brightspark.com"])
    msg = pipeline.build_message(business, unsubscribe_for="me@mine.com")
    # The test copy's unsubscribe link is the tester's, never the business's.
    assert opt_outs.fingerprint("me@mine.com") in msg.unsubscribe_url
    assert opt_outs.fingerprint("owner@brightspark.com") not in msg.unsubscribe_url
    assert msg.to_email == "owner@brightspark.com"

    fake_sender = mock.Mock(smtp_server="s", smtp_port=1)
    fake_sender.connect.return_value = True
    fake_sender.send_email.return_value = True
    with mock.patch.object(LivePipeline, "_sender", return_value=fake_sender), \
            mock.patch.object(LivePipeline, "record_outreach") as record:
        stats = pipeline.send_test(msg, "me@mine.com", password="pw")
    args = fake_sender.send_email.call_args
    assert args.args[0] == "me@mine.com"
    assert args.args[1] == msg.subject and args.args[2] == msg.html
    assert stats["sent"] == 1 and stats["test"]
    record.assert_not_called()
    assert not business.emailed
    fake_sender.disconnect.assert_called_once()


def test_test_send_needs_an_address(pipeline):
    msg = EmailMessage(business=Business(name="A"), to_email="a@x.com", subject="s", html="h")
    fake_sender = mock.Mock()
    with mock.patch.object(LivePipeline, "_sender", return_value=fake_sender):
        stats = pipeline.send_test(msg, "", password="pw")
    assert stats["sent"] == 0 and "address" in stats["error"]
    fake_sender.connect.assert_not_called()
