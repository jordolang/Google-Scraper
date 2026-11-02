"""Tests for the industry registry and classifier."""

import industries


def test_classify_maps_common_categories():
    cases = {
        "Electrician": "electrical",
        "Plumbing service": "plumbing",
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


def test_specific_local_services_take_precedence_over_broad_groups():
    cases = {
        "Lawn care service": "lawncare", "Tree service": "tree_removal",
        "Roofing contractor": "roofing", "Gutter cleaning service": "gutters",
        "Air conditioning contractor": "hvac", "Drain cleaning service": "plumbing",
        "Electrical installation service": "electrical", "Excavating contractor": "excavation",
        "Septic system service": "septic", "Concrete contractor": "concrete_masonry",
        "Fence contractor": "fencing_decks", "Painting contractor": "painting",
        "Flooring store": "flooring", "Pressure washing service": "pressure_washing",
        "House cleaning service": "residential_cleaning", "Junk removal service": "junk_removal",
        "Pest control service": "pest_control", "Towing service": "towing",
        "Pet grooming salon": "pet_grooming", "Farm equipment repair shop": "farm_equipment_repair",
    }
    for category, key in cases.items():
        assert industries.classify(category) == key, category


def test_category_takes_priority_over_unrelated_business_name():
    assert industries.classify("Restaurant", "Electric Diner") == "food_beverage"
    assert industries.classify("Law firm", "Mason Legal") == "professional_services"
    assert industries.classify("", "Muskingum Tree Removal") == "tree_removal"


def test_insurance_specialties_match_without_swallowing_other_industries():
    cases = {
        "Home insurance agency": "insurance_home",
        "Homeowners insurance": "insurance_home",
        "Auto insurance agency": "insurance_auto",
        "Car insurance provider": "insurance_auto",
        "Renter's insurance agency": "insurance_renters",
        "Renters insurance": "insurance_renters",
        "Rental property insurance": "insurance_renters",
        "Boat insurance agency": "insurance_boat",
        "Marine insurance": "insurance_boat",
        "Health insurance agency": "insurance_health",
        "Healthcare insurance provider": "insurance_health",
        "Insurance agency": "professional_services",
        "Auto repair shop": "automotive",
        "Medical clinic": "health_wellness",
        "Boat rental": "real_estate_property",
    }
    for category, expected in cases.items():
        assert industries.classify(category) == expected, category
