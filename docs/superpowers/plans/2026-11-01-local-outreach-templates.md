# Local Outreach Templates Implementation Plan

> **For agentic workers:** Implement tasks in order in this session.

**Goal:** Add 20 industry emails and four manually selected seasonal emails.
**Architecture:** Extend industries.py and standalone email_templates HTML; retain pricing and personalization interfaces.
**Tech Stack:** Python, HTML, pytest.
**Spec:** docs/superpowers/specs/2026-11-01-local-outreach-templates-design.md

## Global Constraints
Preserve personalization tokens, editable pricing, existing templates and user edits.

## Review Focus
Specific categories must beat broad keywords; seasonal variants must stay manual;
all templates must render without tokens; unknown categories must retain fallback;
packaged upgrades must seed missing files without overwriting edits.

### Task 1: Registry and content
- [x] Add 20 specific industry registry entries and four keyword-free seasonal entries.
- [x] Create 24 tailored HTML files retaining all required rendering tokens.
- [x] Verify category routing, manual seasonal selection and full rendering with pytest.

### Task 2: Packaged assets and documentation
- [x] Seed missing files into existing template directories without replacing edits.
- [x] Document available templates and seasonal usage.
- [x] Run related registry, rendering, pricing and GUI runtime tests.

Validation: 51 passed, 1 skipped (desktop GUI requires unavailable PySide6).
HTML parsing and git diff --check passed. Category-first matching prevents
unrelated business names from selecting a specific-service template.
