"""Tests for the per-industry templates and their rendering via EmailGenerator."""

import glob

import industries
from generate_emails import EmailGenerator

REQUIRED_TOKENS = [
    "{{SENDER_NAME}}", "{{SENDER_ADDRESS}}", "{{UNSUBSCRIBE_URL}}",
    "{{BUSINESS_NAME}}", "{{CATEGORY}}", "{{LOCATION}}", "{{ADDRESS}}",
    "{{CURRENT_WEBSITE_NOTE}}", "{{RATING_INFO}}", "{{CONTACT_INFO}}",
    "{{FROM_EMAIL}}", "{{HERO_IMAGE}}",
    "{{LAUNCHPAD_PRICE}}", "{{LAUNCHPAD_SALE_PRICE}}", "{{ATTRIBUTION_PRICE}}",
    "{{PROFESSIONAL_PRICE}}", "{{ENTERPRISE_PRICE}}",
]


def test_every_registered_industry_has_a_template_file():
    for ind in industries.all_industries():
        assert glob.glob(f"email_templates/{ind.template_filename}"), ind.key


#: Every template, variants included, must carry these (CAN-SPAM footer and
#: the unsubscribe link the sender fills per recipient).
CORE_TOKENS = ["{{SENDER_NAME}}", "{{SENDER_ADDRESS}}", "{{UNSUBSCRIBE_URL}}",
               "{{BUSINESS_NAME}}", "{{FROM_EMAIL}}", "{{GREETING}}",
               "{{LAUNCHPAD_SALE_PRICE}}"]


def test_every_template_has_the_core_tokens():
    files = glob.glob("email_templates/*.html")
    assert len(files) > 11
    for path in files:
        html = open(path, encoding="utf-8").read()
        for token in CORE_TOKENS:
            assert token in html, f"{token} missing from {path}"


def test_classic_templates_contain_every_token():
    files = [path for path in glob.glob("email_templates/*.html")
             if "__" not in path and "roofing" not in path]
    assert files, "no templates found"
    for path in files:
        html = open(path, encoding="utf-8").read()
        assert "%%" not in html, f"unresolved build marker in {path}"
        for token in REQUIRED_TOKENS:
            assert token in html, f"{token} missing from {path}"


def _row(category="Electrician", name="Bright Spark Electric"):
    return {
        "name": name, "category": category,
        "address": "123 Main St, Columbus, OH 43215",
        "email": "info@example.com", "rating": "4.8",
        "website": "https://example.com",
    }


def test_generate_email_injects_pricing_and_leaves_no_tokens():
    g = EmailGenerator(output_dir="generated_emails")
    pricing = {
        "launchpad": "$999", "launchpad_sale": "$777", "attribution": "$555",
        "professional": "From $2k", "enterprise": "By quote",
    }
    html, _fn, _email = g.generate_email(
        _row(), industry_key="food_beverage", pricing=pricing
    )
    assert "restaurants &amp; bars" in html          # picked the food template
    assert "$777" in html and "From $2k" in html  # prices injected
    assert "{{" not in html                        # every token resolved


def test_auto_classification_selects_industry_template():
    g = EmailGenerator(output_dir="generated_emails")
    html, _fn, _email = g.generate_email(_row("Plumbing service"))
    assert "home-service pros" in html


def test_no_hero_image_drops_the_image_block():
    g = EmailGenerator(output_dir="generated_emails")
    html, _fn, _email = g.generate_email(_row(), industry_key="general", hero_image="")
    assert "<img" not in html
    assert 'src=""' not in html
    assert "IF:" not in html and "ENDIF" not in html


def test_legacy_template_without_the_block_still_gets_a_pixel(tmp_path):
    legacy = tmp_path / "old.html"
    legacy.write_text("<div style=\"background:url('{{HERO_IMAGE}}')\">{{BUSINESS_NAME}}</div>")
    g = EmailGenerator(template_path=str(legacy), output_dir=str(tmp_path / "out"))
    html, _fn, _email = g.generate_email(_row(), hero_image="")
    assert "data:image/gif;base64" in html


def test_business_values_are_html_escaped():
    g = EmailGenerator(output_dir="generated_emails")
    html, _fn, _email = g.generate_email(_row(name="Smith & <Sons>"), industry_key="general")
    assert "Smith &amp; &lt;Sons&gt;" in html
    assert "<Sons>" not in html


def test_footer_has_unsubscribe_and_optional_postal_address():
    g = EmailGenerator(output_dir="generated_emails", from_email="me@jlang.dev")
    html, _fn, _email = g.generate_email(_row(), industry_key="general")
    assert "mailto:me@jlang.dev?subject=Unsubscribe" in html
    assert "123 Example" not in html
    g = EmailGenerator(output_dir="generated_emails", sender_address="123 Example St",
                       unsubscribe_url="https://jlang.dev/unsubscribe", sender_name="Pat")
    html, _fn, _email = g.generate_email(_row(), industry_key="general")
    assert "123 Example St" in html and "https://jlang.dev/unsubscribe" in html
    assert "Pat" in html


def test_templates_match_the_build_script():
    """The checked-in templates are exactly what the build script writes."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "build_email_templates", "scripts/build_email_templates.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)

    built = build.render_all()
    on_disk = {Path(p).stem for p in glob.glob("email_templates/*.html")}
    assert on_disk == set(built), "rebuild the templates"
    for stem, html in built.items():
        assert Path(f"email_templates/{stem}.html").read_text(encoding="utf-8") == html, \
            f"rebuild {stem}.html"


def test_every_banner_image_is_bundled():
    import email_assets
    from generate_emails import template_meta

    for path in glob.glob("email_templates/*.html"):
        hero = template_meta(open(path, encoding="utf-8").read()).get("hero")
        if hero:
            assert email_assets.local_path(hero).is_file(), f"{hero} ({path})"


def test_hero_image_url_is_embedded():
    g = EmailGenerator(output_dir="generated_emails")
    url = "https://cdn.example.com/hero.jpg"
    html, _fn, _email = g.generate_email(_row(), industry_key="general", hero_image=url)
    assert url in html


def test_legacy_single_template_mode_ignores_industry():
    # Explicit template_path -> the one file is used, industry logic bypassed.
    g = EmailGenerator(template_path="email_template.html", output_dir="generated_emails")
    html, _fn, _email = g.generate_email(_row("Bakery"))
    assert "restaurants &amp; bars" not in html
    assert "home-service pros" not in html
    assert "Bright Spark Electric" in html


ROOFER = {
    "name": "Summit Peak Roofing", "category": "Roofing contractor",
    "address": "412 High St, Columbus, OH 43215", "email": "office@summit.example",
    "rating": "4.9", "reviews_count": "(187)", "website": "https://www.summitpeak.example/",
    "contact_name": "Mike Daniels", "original_phone": "6145550142",
}


def test_roofers_get_the_roofing_template_and_its_subject():
    g = EmailGenerator(output_dir="generated_emails")
    html, _fn, _email = g.generate_email(ROOFER)
    assert "roofing companies" in html
    assert g.last_subject == "A new website for Summit Peak Roofing?"
    assert "{{" not in html and "IF:" not in html


def test_copy_follows_the_scraped_listing():
    g = EmailGenerator(output_dir="generated_emails")
    html, _fn, _email = g.generate_email(ROOFER, industry_key="roofing__reviews")
    assert "Hi Mike," in html
    assert "4.9★ from 187 Google reviews" in html
    assert "summitpeak.example" in html and "None found" not in html
    assert "(614) 555-0142" in html

    bare = dict(ROOFER, website="", rating="", reviews_count="", contact_name="",
                original_phone="")
    html, _fn, _email = g.generate_email(bare, industry_key="roofing__reviews")
    assert "Hi Summit Peak Roofing team," in html
    assert "None found" in html and "couldn’t find a website" in html
    assert "Google rating" not in html and "Reviews</div>" not in html


def test_contact_names_that_are_not_people_fall_back_to_the_team():
    g = EmailGenerator(output_dir="generated_emails")
    html, _fn, _email = g.generate_email(dict(ROOFER, contact_name="Office Manager"),
                                         industry_key="roofing__note")
    assert "Hi Summit Peak Roofing team," in html


def test_showcase_style_uses_each_businesses_own_industry_and_banner():
    g = EmailGenerator(output_dir="generated_emails", asset_url=lambda n: f"https://img.example/{n}")
    html, _fn, _email = g.generate_email(_row("Mexican restaurant", "Casa Azul"),
                                         industry_key="@showcase")
    assert "https://img.example/heroes/food_beverage.jpg" in html
    # A style the industry doesn't have falls back to its default template.
    html, _fn, _email = g.generate_email(_row(), industry_key="@nonexistent")
    assert "home-service pros" in html


def test_unknown_template_id_falls_back_to_its_industry():
    g = EmailGenerator(output_dir="generated_emails")
    html, _fn, _email = g.generate_email(ROOFER, industry_key="roofing__gone")
    assert "roofing companies" in html
