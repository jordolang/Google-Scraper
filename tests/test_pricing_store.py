"""Tests for the persisted per-industry pricing store."""

import json

import industries
import pricing_store


def test_load_pricing_without_file_returns_defaults(tmp_path):
    table = pricing_store.load_pricing(tmp_path / "nope.json")
    assert table == industries.default_pricing()


def test_save_then_load_roundtrips(tmp_path):
    path = tmp_path / "pricing.json"
    table = industries.default_pricing()
    table["food_beverage"]["launchpad_sale"] = "$299"
    pricing_store.save_pricing(table, path)
    loaded = pricing_store.load_pricing(path)
    assert loaded["food_beverage"]["launchpad_sale"] == "$299"


def test_partial_file_is_backfilled_with_defaults(tmp_path):
    path = tmp_path / "pricing.json"
    path.write_text(json.dumps({
        "version": 1,
        "industries": {"automotive": {"enterprise": "By quote"}},
    }), encoding="utf-8")
    loaded = pricing_store.load_pricing(path)
    # The one overridden field is honoured…
    assert loaded["automotive"]["enterprise"] == "By quote"
    # …and every other field/industry is still present from defaults.
    assert loaded["automotive"]["launchpad"] == industries.get("automotive").default_pricing["launchpad"]
    assert set(loaded) == set(industries.default_pricing())


def test_malformed_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "pricing.json"
    path.write_text("{ this is not json", encoding="utf-8")
    assert pricing_store.load_pricing(path) == industries.default_pricing()


def test_prices_for_unknown_industry_uses_general_defaults():
    row = pricing_store.prices_for("nope", store=industries.default_pricing())
    assert set(row) >= set(pricing_store.PACKAGE_FIELDS)


def test_pricing_tokens_maps_all_fields():
    row = pricing_store.prices_for("general")
    tokens = pricing_store.pricing_tokens(row)
    assert tokens["{{LAUNCHPAD_PRICE}}"] == row["launchpad"]
    assert tokens["{{LAUNCHPAD_SALE_PRICE}}"] == row["launchpad_sale"]
    assert tokens["{{ATTRIBUTION_PRICE}}"] == row["attribution"]
    assert tokens["{{PROFESSIONAL_PRICE}}"] == row["professional"]
    assert tokens["{{ENTERPRISE_PRICE}}"] == row["enterprise"]


def test_save_is_atomic_no_tmp_left_behind(tmp_path):
    path = tmp_path / "pricing.json"
    pricing_store.save_pricing(industries.default_pricing(), path)
    assert path.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_hero_urls_saved_and_loaded(tmp_path):
    path = tmp_path / "pricing.json"
    heroes = {"food_beverage": "https://cdn.example.com/food.jpg"}
    pricing_store.save_pricing(industries.default_pricing(), path, heroes=heroes)
    assert pricing_store.load_heroes(path) == heroes
    assert pricing_store.hero_for("food_beverage", pricing_store.load_heroes(path)) == heroes["food_beverage"]
    assert pricing_store.hero_for("automotive", pricing_store.load_heroes(path)) == ""


def test_price_only_save_preserves_existing_heroes(tmp_path):
    path = tmp_path / "pricing.json"
    heroes = {"automotive": "https://cdn.example.com/auto.jpg"}
    pricing_store.save_pricing(industries.default_pricing(), path, heroes=heroes)
    # A later price-only save (heroes=None) must not wipe the stored hero URL.
    table = industries.default_pricing()
    table["automotive"]["launchpad"] = "$444"
    pricing_store.save_pricing(table, path)
    assert pricing_store.load_heroes(path) == heroes
    assert pricing_store.load_pricing(path)["automotive"]["launchpad"] == "$444"
