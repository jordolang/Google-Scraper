"""Tests for the industry registry and classifier."""

import industries


def test_classify_maps_common_categories():
    cases = {
        "Electrician": "home_trade_services",
        "Plumbing service": "home_trade_services",
        "Graphic designer": "creative_design",
        "Sign shop": "creative_design",
        "Mexican restaurant": "food_beverage",
        "Coffee shop": "food_beverage",
        "Yoga studio": "health_wellness",
        "Hair salon": "beauty_personal_care",
        "Barber shop": "beauty_personal_care",
        "Auto repair shop": "automotive",
        "Law firm": "professional_services",
        "Real estate agency": "real_estate_property",
        "Boutique": "retail_boutique",
        "Wedding venue": "events_hospitality",
    }
    for category, expected in cases.items():
        assert industries.classify(category) == expected, category


def test_classify_unknown_falls_back_to_general():
    assert industries.classify("") == "general"
    assert industries.classify("Quantum flux reactor") == "general"


def test_registry_keys_match_template_filenames():
    for ind in industries.all_industries():
        assert ind.template_filename == f"{ind.key}.html"


def test_choices_cover_every_industry_and_are_label_key_pairs():
    keys = {key for _label, key in industries.choices()}
    assert keys == {ind.key for ind in industries.all_industries()}
    assert "general" in keys


def test_get_unknown_returns_general():
    assert industries.get("does-not-exist").key == "general"


def test_default_pricing_has_all_fields():
    table = industries.default_pricing()
    assert set(table) == {ind.key for ind in industries.all_industries()}
    for row in table.values():
        assert set(row) >= {
            "launchpad", "launchpad_sale", "attribution", "professional", "enterprise"
        }
