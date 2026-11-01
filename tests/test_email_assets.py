"""Template banner images: bundled files turned into public addresses."""

import json

import email_assets


class FakeHost:
    def __init__(self, ok=True):
        self.ok = ok
        self.uploads = []

    def configured(self):
        return True

    def upload_bytes(self, data, name, content_type=""):
        if not self.ok:
            raise RuntimeError("bucket missing")
        self.uploads.append(name)
        return f"https://host.example/{name}"


def test_without_a_host_the_public_copy_is_used():
    assert email_assets.hosted_resolver(None)("heroes/general.jpg") == \
        email_assets.PUBLIC_BASE + "heroes/general.jpg"


def test_a_host_gets_each_file_once(tmp_path):
    host = FakeHost()
    cache = tmp_path / "cache.json"
    resolve = email_assets.hosted_resolver(host, cache)
    assert resolve("heroes/general.jpg") == "https://host.example/general.jpg"
    assert email_assets.hosted_resolver(host, cache)("heroes/general.jpg") == \
        "https://host.example/general.jpg"
    assert host.uploads == ["general.jpg"]
    assert "heroes/general.jpg" in json.loads(cache.read_text())


def test_switching_hosts_uploads_again(tmp_path):
    """A URL cached from the old Supabase bucket isn't reused for Vercel Blob."""
    cache = tmp_path / "cache.json"
    old = FakeHost()
    email_assets.hosted_resolver(old, cache)("heroes/general.jpg")
    entry = json.loads(cache.read_text())["heroes/general.jpg"]
    entry.pop("host")  # how entries written before this change look
    cache.write_text(json.dumps({"heroes/general.jpg": entry}))

    new = FakeHost()
    new.identity = "vercel-blob:Store123"
    email_assets.hosted_resolver(new, cache)("heroes/general.jpg")
    assert new.uploads == ["general.jpg"]
    assert json.loads(cache.read_text())["heroes/general.jpg"]["host"] == "vercel-blob:Store123"
    email_assets.hosted_resolver(new, cache)("heroes/general.jpg")
    assert new.uploads == ["general.jpg"]  # cached for the same store


def test_a_failed_upload_falls_back_to_the_public_copy(tmp_path):
    errors = []
    resolve = email_assets.hosted_resolver(FakeHost(ok=False), tmp_path / "c.json",
                                           on_error=errors.append)
    assert resolve("heroes/general.jpg").startswith(email_assets.PUBLIC_BASE)
    assert errors
