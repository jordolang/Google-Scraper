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


def test_all_templates_contain_every_token():
    files = glob.glob("email_templates/*.html")
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
    import json

    content = json.loads(build.CONTENT.read_text(encoding="utf-8"))
    for key, copy in content.items():
        on_disk = Path(f"email_templates/{key}.html").read_text(encoding="utf-8")
        assert on_disk == build.render(key, copy), f"rebuild {key}.html"


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
