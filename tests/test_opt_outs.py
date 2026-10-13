"""Per-recipient unsubscribe links and skipping people who used them."""

from unittest import mock

import pytest

import opt_outs
import send_emails
from tui.models import Business, EmailMessage
from tui.pipeline import LivePipeline

URL = "https://abcd.supabase.co"


class FakeTable:
    """Just enough of PostgREST's outreach_recipients endpoint."""

    def __init__(self, missing=False):
        self.rows = {}
        self.missing = missing
        self.calls = []

    def request(self, method, url, headers=None, timeout=None, params=None, json=None):
        self.calls.append((method, url, headers, params, json))
        assert url == f"{URL}/rest/v1/outreach_recipients"
        if self.missing:
            return mock.Mock(status_code=404, text='{"code":"PGRST205"}')
        if method == "POST":
            assert headers["Prefer"].startswith("resolution=ignore-duplicates")
            for row in json:
                self.rows.setdefault(row["email"], {**row, "unsubscribed_at": None})
            return mock.Mock(status_code=201, text="")
        if "token" in params["select"]:
            email = params["email"].removeprefix("eq.")
            found = [r for r in self.rows.values() if r["email"] == email]
        else:
            wanted = params["email"].removeprefix("in.(").removesuffix(")")
            wanted = {e.strip('"') for e in wanted.split(",")}
            found = [r for r in self.rows.values()
                     if r["email"] in wanted and r["unsubscribed_at"]]
        return mock.Mock(status_code=200, json=lambda: found, text="")


def make_list(table, key="sb_secret_abc"):
    optouts = opt_outs.OptOutList(url=URL, key=key)
    optouts._session = table
    return optouts


def test_each_recipient_gets_their_own_stable_link():
    table = FakeTable()
    optouts = make_list(table)
    link = optouts.link_for("Owner@Shop.com ")
    assert link.startswith(f"{URL}/functions/v1/unsubscribe?t=")
    assert table.rows["owner@shop.com"]["token"] == link.split("t=", 1)[1]
    # A fresh client (a later campaign) reuses the saved token.
    assert make_list(table).link_for("owner@shop.com") == link
    assert make_list(table).link_for("info@bakery.com") != link


def test_secret_keys_stay_out_of_authorization():
    table = FakeTable()
    make_list(table, key="sb_secret_abc").link_for("a@b.com")
    assert "Authorization" not in table.calls[0][2]
    make_list(table, key="eyJhbGciOi.legacy").link_for("a@b.com")
    assert table.calls[-1][2]["Authorization"] == "Bearer eyJhbGciOi.legacy"


def test_opted_out_reports_only_unsubscribed_addresses():
    table = FakeTable()
    optouts = make_list(table)
    optouts.link_for("gone@x.com")
    optouts.link_for("still@x.com")
    table.rows["gone@x.com"]["unsubscribed_at"] = "2026-10-13T00:00:00Z"
    assert optouts.opted_out(["GONE@x.com", "still@x.com", "new@x.com", ""]) == {"gone@x.com"}


def test_missing_table_is_reported_as_not_set_up():
    with pytest.raises(opt_outs.OptOutsNotSetUp):
        make_list(FakeTable(missing=True)).link_for("a@b.com")


def test_unconfigured_list_says_so(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    assert not opt_outs.OptOutList().configured()


# ----------------------------------------------------------------- pipeline
@pytest.fixture
def pipeline(tmp_path):
    pipe = LivePipeline(data_root=tmp_path, image_host_url=URL,
                        templates_dir="email_templates")
    table = FakeTable()
    pipe._opt_out_list = make_list(table)
    pipe._opt_outs_missing = False
    pipe.table = table
    return pipe


def test_email_carries_the_recipients_link_in_footer_and_header(pipeline):
    business = Business(name="Bright Spark", category="Electrician",
                        emails=["owner@brightspark.com"])
    msg = pipeline.build_message(business)
    link = pipeline.table.rows["owner@brightspark.com"]["token"]
    assert msg.unsubscribe_url.endswith(f"?t={link}")
    assert f'href="{msg.unsubscribe_url}"' in msg.html

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
    pipeline.table.rows["gone@x.com"] = {
        "email": "gone@x.com", "token": "t" * 22, "unsubscribed_at": "2026-10-13"}
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
    def unreachable(*_a, **_k):
        raise opt_outs.OptOutError("Could not reach Supabase")

    pipeline._opt_out_list.opted_out = unreachable
    msg = EmailMessage(business=Business(name="A"), to_email="a@x.com", subject="s", html="h")
    fake_sender = mock.Mock()
    with mock.patch.object(LivePipeline, "_sender", return_value=fake_sender):
        stats = pipeline.send([msg], password="pw")
    assert stats["sent"] == 0 and "unsubscribe" in stats["error"]
    fake_sender.connect.assert_not_called()


def test_without_the_table_emails_fall_back_to_the_shared_link(pipeline):
    pipeline.table.missing = True
    pipeline.unsubscribe_url = "https://jlang.dev/unsubscribe"
    msg = pipeline.build_message(Business(name="A", emails=["a@x.com"]))
    assert msg.unsubscribe_url == ""
    assert 'href="https://jlang.dev/unsubscribe"' in msg.html
