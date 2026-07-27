"""Tests for the per-industry templates and their rendering via EmailGenerator."""

import glob

import industries
from generate_emails import EmailGenerator

REQUIRED_TOKENS = [
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
    assert "restaurants & bars" in html          # picked the food template
    assert "$777" in html and "From $2k" in html  # prices injected
    assert "{{" not in html                        # every token resolved


def test_auto_classification_selects_industry_template():
    g = EmailGenerator(output_dir="generated_emails")
    html, _fn, _email = g.generate_email(_row("Plumbing service"))
    assert "home-service pros" in html


def test_hero_image_empty_uses_transparent_pixel_not_empty_url():
    g = EmailGenerator(output_dir="generated_emails")
    html, _fn, _email = g.generate_email(_row(), industry_key="general", hero_image="")
    assert "url('')" not in html
    assert "data:image/gif;base64" in html


def test_hero_image_url_is_embedded():
    g = EmailGenerator(output_dir="generated_emails")
    url = "https://cdn.example.com/hero.jpg"
    html, _fn, _email = g.generate_email(_row(), industry_key="general", hero_image=url)
    assert url in html


def test_legacy_single_template_mode_ignores_industry():
    # Explicit template_path -> the one file is used, industry logic bypassed.
    g = EmailGenerator(template_path="email_template.html", output_dir="generated_emails")
    html, _fn, _email = g.generate_email(_row("Bakery"))
    assert "restaurants & bars" not in html
    assert "home-service pros" not in html
    assert "Bright Spark Electric" in html
