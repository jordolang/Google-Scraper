"""Template upgrades preserve edits while adding newly bundled campaigns."""
from gui import runtime


def test_upgrade_seeds_new_templates_without_overwriting_edits(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    user = tmp_path / "user"
    (bundle / "email_templates").mkdir(parents=True)
    (user / "email_templates").mkdir(parents=True)
    (bundle / "email_templates/general.html").write_text("bundled")
    (user / "email_templates/general.html").write_text("my custom copy")
    (bundle / "email_templates/seasonal_snow_removal.html").write_text("snow campaign")
    monkeypatch.setattr(runtime, "frozen", lambda: True)
    monkeypatch.setattr(runtime, "bundle_dir", lambda: bundle)
    monkeypatch.setattr(runtime, "app_data_dir", lambda: user)
    (bundle / "email_templates/templates.json").write_text('{"templates": []}')
    runtime.user_asset("email_templates")
    assert (user / "email_templates/templates.json").read_text() == '{"templates": []}'
    (user / "email_templates/templates.json").write_text("my edited catalog")
    runtime.user_asset("email_templates")
    assert (user / "email_templates/templates.json").read_text() == "my edited catalog"
    assert (user / "email_templates/general.html").read_text() == "my custom copy"
    assert (user / "email_templates/seasonal_snow_removal.html").read_text() == "snow campaign"


def test_catalog_managed_html_survives_legacy_template_refresh(tmp_path, monkeypatch):
    bundle, user = tmp_path / "bundle", tmp_path / "user"
    (bundle / "email_templates").mkdir(parents=True)
    (user / "email_templates").mkdir(parents=True)
    (user / "email_templates/templates.json").write_text('{"templates": []}')
    custom = user / "email_templates/custom.html"
    custom.write_text("My custom HTML without a generator marker")
    monkeypatch.setattr(runtime, "frozen", lambda: True)
    monkeypatch.setattr(runtime, "bundle_dir", lambda: bundle)
    monkeypatch.setattr(runtime, "app_data_dir", lambda: user)
    assert runtime.refresh_templates() is None
    assert custom.read_text() == "My custom HTML without a generator marker"
