# External Template Catalog Implementation Plan

**Goal:** Add templates using HTML files and templates.json without rebuilding.
**Spec:** ../specs/2026-11-01-external-template-catalog-design.md
**Architecture:** Existing industry APIs read validated catalog entries. The
renderer, pricing store and GUI consume those APIs with the editable folder.
**Tech stack:** Python, JSON, HTML, PySide6, pytest.

- [x] Ship all 40 existing entries in email_templates/templates.json.
- [x] Read and validate IDs, filenames, optional metadata and pricing defaults.
- [x] Preserve priority matching and compiled fallback for absent catalogs.
- [x] Render custom filenames and read edited HTML on the next use.
- [x] Seed missing catalogs without overwriting user changes.
- [x] Add folder/reload controls, preserve selection and report catalog errors.
- [x] Document exact workflow and supported placeholders.
- [x] Test custom matching/rendering, reloads, removals, priorities, invalid JSON,
  duplicates, missing files, traversal, pricing overrides and asset preservation.

Verification: 63 passed, 2 skipped (PySide6 unavailable); includes terminal UI.
Desktop control coverage is added to the existing PySide6 test module.
