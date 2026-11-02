# External template catalog

Approved in chat: users add HTML files to a folder and edit templates.json to
register them without rebuilding. The catalog supplies IDs, names, filenames,
matching keywords, optional accent, priority and package-price defaults.

Extend the current registry API with an external catalog, keeping compiled
fallback entries when no catalog exists. Ship the complete initial catalog.
Preserve existing user HTML, catalog and pricing edits on upgrade. Read HTML and
metadata fresh; validate JSON, IDs, duplicates, field types and file locations.
Use catalog filenames for rendering and editing. Add Open Templates Folder and
Reload Templates controls; reload preserves selection or resets to Auto if its
entry was removed. Report errors and keep existing selector choices on failure.

Keep seasonal templates manual-only through empty keywords. Reuse existing
pricing.json overrides and legacy single-template support. No dependency changes,
remote synchronization or automatic sending.
