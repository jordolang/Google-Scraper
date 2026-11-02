"""External catalogs configure selection, matching and rendering without Python edits."""
import json

import pytest

import industries
from generate_emails import EmailGenerator


def write_catalog(folder, entries=None):
    folder.mkdir(exist_ok=True)
    (folder / 'custom-offer.html').write_text('<h1>{{BUSINESS_NAME}}</h1>Custom offer {{LAUNCHPAD_SALE_PRICE}}')
    (folder / 'general.html').write_text('General {{BUSINESS_NAME}}')
    entries = entries if entries is not None else [
        {'id': 'test_custom', 'name': 'Custom Local Service', 'file': 'custom-offer.html',
         'keywords': ['custom local'], 'default_pricing': {'launchpad_sale': '$123'}}]
    (folder / 'templates.json').write_text(json.dumps({'version': 1, 'templates': entries}))
    return folder


def test_catalog_configures_matching_and_rendering_and_reloads_html(tmp_path):
    folder = write_catalog(tmp_path)
    assert industries.get('test_custom', folder).template_filename == 'custom-offer.html'
    assert industries.classify('Custom local service', templates_dir=folder) == 'test_custom'
    generator = EmailGenerator(templates_dir=folder, output_dir=str(tmp_path / 'output'))
    row = {'name': 'Local Example', 'category': 'Custom local service'}
    html, _, _ = generator.generate_email(row)
    assert html == '<h1>Local Example</h1>Custom offer $123'
    (folder / 'custom-offer.html').write_text('Edited {{BUSINESS_NAME}}')
    assert generator.generate_email(row)[0] == 'Edited Local Example'
    data = json.loads((folder / 'templates.json').read_text())
    data['templates'][0]['name'] = 'Renamed'
    (folder / 'templates.json').write_text(json.dumps(data))
    assert industries.get('test_custom', folder).label == 'Renamed'


@pytest.mark.parametrize('entry', [
    {'id': 'bad', 'name': 'Bad', 'file': '../outside.html'},
    {'id': 'bad', 'name': 'Bad', 'file': 'missing.html'},
    {'id': 'bad', 'name': 'Bad', 'file': 'custom-offer.html', 'keywords': 'text'},
    {'id': 'bad', 'name': 'Bad', 'file': 'custom-offer.html', 'default_pricing': {'launchpad_sale': 123}},
])
def test_invalid_entries_have_actionable_errors(tmp_path, entry):
    write_catalog(tmp_path, [entry])
    with pytest.raises(industries.CatalogError, match='templates.json'):
        industries.all_industries(tmp_path)


def test_invalid_json_and_duplicates_are_reported(tmp_path):
    write_catalog(tmp_path)
    path = tmp_path / 'templates.json'
    path.write_text('{broken')
    with pytest.raises(industries.CatalogError, match='templates.json'):
        industries.all_industries(tmp_path)
    row = {'id': 'custom', 'name': 'Custom', 'file': 'custom-offer.html'}
    write_catalog(tmp_path, [row, row])
    with pytest.raises(industries.CatalogError, match='Duplicate'):
        industries.all_industries(tmp_path)


def test_missing_catalog_keeps_legacy_defaults(tmp_path):
    assert industries.get('insurance_home', tmp_path).key == 'insurance_home'


def test_catalog_listing_uses_file_field_and_removal_hides_entry(tmp_path):
    from gui import services

    write_catalog(tmp_path)
    assert ('Custom Local Service', 'test_custom') in services.available_templates(str(tmp_path))
    (tmp_path / 'templates.json').write_text(json.dumps({'templates': []}))
    assert 'test_custom' not in dict((key, label) for label, key in services.available_templates(str(tmp_path)))


def test_catalog_pricing_defaults_and_saved_overrides(tmp_path, monkeypatch):
    import pricing_store

    write_catalog(tmp_path, [{'id': 'lawncare', 'name': 'Custom Lawn', 'file': 'custom-offer.html',
        'default_pricing': {'launchpad_sale': '$123'}}])
    monkeypatch.chdir(tmp_path)
    assert pricing_store.prices_for('lawncare', templates_dir=tmp_path)['launchpad_sale'] == '$123'
    (tmp_path / 'pricing.json').write_text(json.dumps({'industries': {'lawncare': {'launchpad_sale': '$456'}}}))
    assert pricing_store.prices_for('lawncare', templates_dir=tmp_path)['launchpad_sale'] == '$456'


def test_catalog_priority_and_manual_templates(tmp_path):
    write_catalog(tmp_path, [
        {'id': 'broad', 'name': 'Broad', 'file': 'custom-offer.html',
         'keywords': ['local', 'service'], 'priority': 0},
        {'id': 'specific', 'name': 'Specific', 'file': 'custom-offer.html',
         'keywords': ['custom local']},
        {'id': 'manual', 'name': 'Manual', 'file': 'custom-offer.html'},
    ])
    assert industries.classify('Custom local service', templates_dir=tmp_path) == 'specific'
    assert industries.classify('Manual', templates_dir=tmp_path) == 'general'


def test_legacy_variant_inherits_base_pricing(tmp_path, monkeypatch):
    write_catalog(tmp_path, [
        {'id': 'roofing', 'name': 'Roofing', 'file': 'custom-offer.html'},
        {'id': 'roofing__note', 'name': 'Note', 'file': 'note.html'},
    ])
    (tmp_path / 'note.html').write_text('Variant {{LAUNCHPAD_SALE_PRICE}}')
    (tmp_path / 'pricing.json').write_text(json.dumps({'industries': {'roofing': {'launchpad_sale': '$321'}}}))
    monkeypatch.chdir(tmp_path)
    generator = EmailGenerator(templates_dir=tmp_path, output_dir=str(tmp_path / 'output'))
    assert generator.generate_email({'name': 'Roofer'}, industry_key='roofing__note')[0] == 'Variant $321'
