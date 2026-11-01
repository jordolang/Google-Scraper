"""Website previews: the standard prompt, the Higgsfield client, the pipeline step."""

from __future__ import annotations

import csv

import pytest

import site_preview
from site_preview import (
    HiggsfieldClient, PreviewError, PreviewMaker, build_prompt, explain,
)
from tui.models import Business
from tui.pipeline import DemoPipeline


class FakeResponse:
    def __init__(self, status=200, data=None, content=b"", text=""):
        self.status_code = status
        self._data = data or {}
        self.content = content
        self.text = text

    def json(self):
        return self._data


class FakeSession:
    """Records requests; answers status polls from a queue."""

    def __init__(self, submit=None, polls=(), image=b"jpegbytes"):
        self.posts, self.gets = [], []
        self.submit = submit or FakeResponse(200, {
            "status": "queued", "request_id": "r1",
            "status_url": "https://api.higgsfield.ai/requests/r1/status"})
        self.polls = list(polls)
        self.image = image

    def post(self, url, headers=None, json=None, timeout=None):
        self.posts.append((url, headers, json))
        return self.submit

    def get(self, url, headers=None, timeout=None):
        self.gets.append(url)
        if "/requests/" in url:
            return self.polls.pop(0)
        return FakeResponse(200, content=self.image)


def done(url="https://cdn.higgsfield.ai/out.jpg"):
    return FakeResponse(200, {"status": "completed", "images": [{"url": url}]})


def business(**kw):
    defaults = dict(name="Bright Spark Electric", category="Electrician",
                    address="123 Main St, Columbus, OH 43215")
    defaults.update(kw)
    return Business(**defaults)


# -- prompt ------------------------------------------------------------------
def test_prompt_uses_name_category_town_and_industry_scene():
    prompt = build_prompt(business())
    assert '"Bright Spark Electric"' in prompt
    assert "an electrician in Columbus, OH" in prompt
    photo, palette = site_preview.SCENES["home_trade_services"]
    assert photo in prompt and f"{palette} colour palette" in prompt
    assert "Get a Free Quote" in prompt


def test_prompt_is_the_same_every_time_and_follows_the_industry():
    assert build_prompt(business()) == build_prompt(business())
    cafe = build_prompt(business(name="Sunny Cafe", category="Cafe"))
    assert site_preview.SCENES["food_beverage"][0] in cafe
    assert "a cafe in" in cafe
    assert "View Menu" in cafe


def test_prompt_strips_quotes_that_would_break_it():
    prompt = build_prompt(business(name='Joe\'s "Best" Pizza\n'))
    assert '"Joe\'s Best Pizza"' in prompt


def test_prompt_falls_back_when_details_are_missing():
    prompt = build_prompt(Business(name="Acme"))
    assert "a local business in your area" in prompt
    assert "Contact Us" in prompt


# -- client ------------------------------------------------------------------
def test_client_submits_with_key_header_and_polls_until_done():
    session = FakeSession(polls=[FakeResponse(200, {"status": "queued"}),
                                 FakeResponse(200, {"status": "in_progress"}),
                                 done()])
    naps = []
    client = HiggsfieldClient("id", "secret", session=session, sleep=naps.append)
    assert client.generate("a prompt") == "https://cdn.higgsfield.ai/out.jpg"
    url, headers, body = session.posts[0]
    assert url == "https://api.higgsfield.ai/recraft/v4.1/utility/pro/text-to-image"
    assert headers["Authorization"] == "Key id:secret"
    assert headers["Idempotency-Key"]
    assert body == {"prompt": "a prompt", "resolution": "2k",
                    "aspect_ratio": "16:9", "output_format": "jpg"}
    assert len(naps) == 2


def test_client_model_choice_changes_endpoint_and_body():
    session = FakeSession(polls=[done()])
    HiggsfieldClient("id", "secret", "soul-v2", session=session).generate("p")
    url, _headers, body = session.posts[0]
    assert url.endswith("/higgsfield-ai/soul/v2/standard")
    assert body["resolution"] == "1080p"


def test_client_reads_keys_from_environment(monkeypatch):
    monkeypatch.setenv("HF_API_KEY_ID", "envid")
    monkeypatch.setenv("HF_API_KEY_SECRET", "envsecret")
    assert HiggsfieldClient().configured()
    monkeypatch.delenv("HF_API_KEY_SECRET")
    assert not HiggsfieldClient().configured()


def test_client_without_keys_says_where_to_add_them(monkeypatch):
    monkeypatch.delenv("HF_API_KEY_ID", raising=False)
    monkeypatch.delenv("HF_API_KEY_SECRET", raising=False)
    with pytest.raises(PreviewError, match="Settings → Website Previews"):
        HiggsfieldClient(session=FakeSession()).generate("p")


@pytest.mark.parametrize("status, expected", [
    ("failed", "could not make"), ("nsfw", "content filter")])
def test_client_reports_failed_requests(status, expected):
    session = FakeSession(polls=[FakeResponse(200, {"status": status})])
    with pytest.raises(PreviewError, match=expected):
        HiggsfieldClient("id", "s", session=session).generate("p")


def test_client_gives_up_after_timeout():
    session = FakeSession(polls=[FakeResponse(200, {"status": "queued"})] * 5)
    client = HiggsfieldClient("id", "s", session=session, sleep=lambda _s: None)
    with pytest.raises(PreviewError, match="too long"):
        client.wait(client.submit("p"), timeout=6, every=3)


def test_explain_maps_errors_to_fixes():
    assert "refused the API key" in explain(401, "")
    assert "out of credits" in explain(402, "")
    assert "rate-limiting" in explain(429, "")
    assert "500" in explain(500, "boom")


# -- maker -------------------------------------------------------------------
class FakeHost:
    def __init__(self, ready=True):
        self.ready = ready
        self.uploads = []

    def configured(self):
        return self.ready

    def upload_bytes(self, data, name, content_type=""):
        self.uploads.append((data, name, content_type))
        return f"https://store.public.blob.vercel-storage.com/email-images/{name}"


def test_maker_rehosts_the_image_and_sets_hero_image():
    session = FakeSession(polls=[done()])
    host = FakeHost()
    b = business()
    url = PreviewMaker(HiggsfieldClient("id", "s", session=session), host).make(b)
    assert host.uploads == [(b"jpegbytes", "preview-bright-spark-electric.jpg", "image/jpeg")]
    assert b.hero_image == url and "blob.vercel-storage.com" in url


def test_maker_without_a_host_keeps_the_higgsfield_link():
    session = FakeSession(polls=[done()])
    b = business()
    maker = PreviewMaker(HiggsfieldClient("id", "s", session=session), FakeHost(False))
    assert maker.make(b) == "https://cdn.higgsfield.ai/out.jpg"
    assert not maker.hosts_images


# -- pipeline ----------------------------------------------------------------
def test_demo_pipeline_makes_previews_only_where_missing(tmp_path):
    pipeline = DemoPipeline(data_root=tmp_path)
    have = business(name="Has One", hero_image="https://keep.me/x.png")
    need = business(name="Needs One")
    lines = []
    assert pipeline.make_previews([have, need], progress=lines.append) == 1
    assert have.hero_image == "https://keep.me/x.png"
    assert need.hero_image.startswith("https://placehold.co/")
    assert any("[1/1] Needs One" in line for line in lines)


def test_pipeline_stops_the_batch_when_keys_are_missing(tmp_path):
    class NoKeys:
        hosts_images = True
        calls = 0

        def make(self, business, industry_key=""):
            NoKeys.calls += 1
            raise PreviewError("Higgsfield is not set up.")

    pipeline = DemoPipeline(data_root=tmp_path)
    pipeline._preview_maker = NoKeys
    assert pipeline.make_previews([business(name="A"), business(name="B")]) == 0
    assert NoKeys.calls == 1


def test_preview_survives_a_csv_round_trip():
    b = business(hero_image="https://img.example/p.jpg")
    assert Business.from_dict(b.to_contact_row()).hero_image == "https://img.example/p.jpg"


def test_command_line_fills_a_preview_column(tmp_path, monkeypatch):
    path = tmp_path / "contacts.csv"
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "category", "address"])
        writer.writeheader()
        writer.writerow({"name": "Sunny Cafe", "category": "Cafe", "address": ""})

    class Maker:
        hosts_images = True

        def __init__(self, *_a, **_k):
            pass

        def make(self, business, industry_key=""):
            return "https://img.example/sunny.jpg"

    monkeypatch.setattr(site_preview, "PreviewMaker", Maker)
    assert site_preview.main([str(path)]) == 0
    with open(path, newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["preview_image"] == "https://img.example/sunny.jpg"
