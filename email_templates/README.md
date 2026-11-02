# Local industry and seasonal outreach

## Add or edit templates without rebuilding

1. In **Contacts & Outreach**, click **Open Templates Folder**.
2. Copy your `.html` file into that folder (or duplicate an existing template).
3. Open `templates.json` in a text editor and add an entry to its `templates` list:

```json
{
  "id": "my_new_template",
  "name": "My New Template",
  "file": "my-offer.html",
  "keywords": ["my business category"],
  "accent": "#60a5fa"
}
```

4. Save valid JSON, then click **Reload Templates**. Your new template appears in
   the selector. Preview it before sending.

Keep the existing entries you still want; removing an entry hides that template.
Each `id` must be unique, lowercase, and start with a letter; numbers and
underscores are allowed. `file` is an HTML filename directly in this folder;
it can differ from the ID. `name` is the label shown in the application.
The catalog's outer structure is `{"version": 1, "templates": [...]}`.
JSON entries need commas between them, with no trailing comma after the last.

- `keywords` is optional; omit it or use `[]` for manual-only templates.
- Matching checks category before business name. Optional `priority` defaults
  to `100`; higher-priority matching groups beat lower ones. Within a group,
  more keyword hits win, then catalog order breaks ties. Broad built-ins use `0`.
- `accent` is optional metadata; edit the HTML's styles to change its colors.
- Optional `default_pricing` accepts `launchpad`, `launchpad_sale`, `attribution`,
  `professional`, and `enterprise` as display strings. Existing `pricing.json`
  overrides take precedence. Prices refer to website packages.
- HTML edits are read for the next preview/email. Catalog edits are read on use;
  **Reload Templates** refreshes the dropdown and preserves the selected ID.
- Invalid catalogs or missing listed HTML files report an error; correcting
  them and reloading restores operation. A missing catalog uses legacy defaults.
- Keep `general.html` as the fallback for unmatched businesses. The shipped
  catalog includes every current template, including the four seasonal variants.

Optional HTML placeholders supported by the renderer:
`{{BUSINESS_NAME}}`, `{{CATEGORY}}`, `{{LOCATION}}`, `{{ADDRESS}}`,
`{{CURRENT_WEBSITE_NOTE}}`, `{{RATING_INFO}}`, `{{CONTACT_INFO}}`,
`{{FROM_EMAIL}}`, `{{HERO_IMAGE}}`, `{{LAUNCHPAD_PRICE}}`,
`{{LAUNCHPAD_SALE_PRICE}}`, `{{ATTRIBUTION_PRICE}}`,
`{{PROFESSIONAL_PRICE}}`, and `{{ENTERPRISE_PRICE}}`.
The note, rating and contact placeholders insert HTML fragments.

From source, edit this repository's `email_templates` folder. Installed Windows
apps use `%LOCALAPPDATA%/LocalLeadScraperPro/email_templates`; use the folder
button to find the exact location on any platform. Updates preserve existing
HTML and catalog edits. This feature requires one application rebuild/install;
afterward, template updates require only the HTML files and catalog changes.

These emails pitch Jlang.dev website services to local businesses. Select a
specific template under **Contacts & Outreach → Email Template**, preview it,
and adjust pricing before using it. Auto matches specific services before broad
industry groups. Seasonal campaigns must be selected explicitly; dates never
switch campaigns automatically. Every file remains editable standalone HTML.

## New industry templates

| Industry | File |
| --- | --- |
| Lawncare & Landscaping | lawncare.html |
| Tree Removal & Arborists | tree_removal.html |
| Roofing Contractors | roofing.html |
| Gutter Installation & Cleaning | gutters.html |
| HVAC & Heating | hvac.html |
| Plumbing & Drain Services | plumbing.html |
| Electrical Contractors | electrical.html |
| Excavation & Site Work | excavation.html |
| Septic Services | septic.html |
| Concrete & Masonry | concrete_masonry.html |
| Fencing & Decks | fencing_decks.html |
| Painting Contractors | painting.html |
| Flooring Installation | flooring.html |
| Pressure Washing | pressure_washing.html |
| Residential Cleaning | residential_cleaning.html |
| Junk Removal & Cleanouts | junk_removal.html |
| Pest Control | pest_control.html |
| Towing & Roadside Assistance | towing.html |
| Pet Grooming | pet_grooming.html |
| Farm Equipment Repair | farm_equipment_repair.html |

## Insurance providers

| Specialty | File |
| --- | --- |
| Home Insurance | insurance_home.html |
| Auto Insurance | insurance_auto.html |
| Renters & Rental Property Insurance | insurance_renters.html |
| Boat & Marine Insurance | insurance_boat.html |
| Health Insurance | insurance_health.html |

Insurance templates pitch agency websites, with tailored service pages,
callback requests and links to the agency's approved quoting/enrollment system.
Generic insurance agencies retain the Professional Services template; choose a
specialty manually for agencies offering multiple lines.

## Seasonal campaigns

| Campaign | File | Focus |
| --- | --- | --- |
| Winter Snow Removal | seasonal_snow_removal.html | Plowing, salting and winter routes |
| Spring & Summer Mowing | seasonal_mowing.html | Recurring mowing and route planning |
| Fall Leaves & Tree Trimming | seasonal_leaves_tree_trimming.html | Leaf collection, cleanup and pruning |
| Spring Flooding & Water Mitigation | seasonal_flood_water_mitigation.html | Extraction, drying and moisture assessment |

Local copy references Zanesville and Muskingum County; business details still
use the existing personalization tokens. Pricing is for website packages.
Packaged upgrades copy missing HTML files into the editable template folder
without replacing existing user edits. The catalog-enabled application loads future template additions directly from
this folder, without rebuilding.
