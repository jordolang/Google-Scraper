#!/usr/bin/env python3
"""Build every industry email template from one master layout.

The eleven files in ``email_templates/`` share a single design; only the copy
and the accent colour change by industry. The copy lives in
``scripts/email_template_content.json``, so wording changes are a data edit.
Rebuild after changing either::

    python scripts/build_email_templates.py

The layout is built for the inbox rather than the browser: a light, single
column, table-based, with inline styles, one real ``<img>`` (never a CSS
background, which Outlook and Gmail drop), one call to action, a plain-text
signature, and a footer with an unsubscribe link and the sender's postal
address. Heavy, image-led, price-led HTML is what spam filters score down, so
the prices sit in one compact table rather than three cards.

Runtime tokens (``{{BUSINESS_NAME}}`` and friends) pass through untouched for
:class:`generate_emails.EmailGenerator` to fill. ``<!--IF:NAME-->`` …
``<!--ENDIF:NAME-->`` wraps a block the generator drops when ``NAME`` is empty.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import email_config  # noqa: E402
import industries  # noqa: E402

CONTENT = Path(__file__).with_name("email_template_content.json")
OUT_DIR = ROOT / "email_templates"

#: Bumped when the layout changes, so the desktop app knows a user's copy of
#: the templates predates it (see gui.runtime.refresh_templates).
TEMPLATE_VERSION = 2
VERSION_MARKER = f"<!-- llsp-template: {TEMPLATE_VERSION} -->"

INK = "#111827"
BODY = "#374151"
MUTED = "#6b7280"
FAINT = "#9ca3af"
LINE = "#e5e7eb"
PAGE = "#f3f4f6"
FONT = ("-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,"
        "sans-serif")


def tint(hex_colour: str, amount: float) -> str:
    """Mix a colour toward white: ``amount`` 0 = unchanged, 1 = white."""
    value = hex_colour.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    mix = lambda c: round(c + (255 - c) * amount)  # noqa: E731
    return "#{:02x}{:02x}{:02x}".format(mix(r), mix(g), mix(b))


def shade(hex_colour: str, amount: float) -> str:
    """Mix a colour toward black, for text that has to stay readable."""
    value = hex_colour.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    mix = lambda c: round(c * (1 - amount))  # noqa: E731
    return "#{:02x}{:02x}{:02x}".format(mix(r), mix(g), mix(b))


def text(value: str) -> str:
    """Escape copy for HTML while leaving {{TOKENS}} intact."""
    return html.escape(value, quote=False)


def benefit_rows(benefits, accent: str) -> str:
    rows = []
    for title, body in benefits:
        rows.append(f"""
        <tr>
          <td valign="top" width="22" style="padding:7px 0 7px 0;">
            <div style="width:8px;height:8px;border-radius:4px;background:{accent};margin-top:7px;"></div>
          </td>
          <td style="padding:7px 0;font-size:15px;line-height:1.6;color:{BODY};">
            <strong style="color:{INK};">{text(title)}.</strong> {text(body)}
          </td>
        </tr>""")
    return "".join(rows)


def package_row(name: str, detail: str, price: str, *, last: bool = False,
                strike: str = "", accent: str = INK) -> str:
    border = "" if last else f"border-bottom:1px solid {LINE};"
    was = (f'<span style="color:{FAINT};text-decoration:line-through;'
           f'font-weight:400;">{strike}</span>&nbsp; ') if strike else ""
    return f"""
          <tr>
            <td style="padding:14px 16px;{border}">
              <div style="font-size:15px;font-weight:700;color:{INK};">{name}</div>
              <div style="font-size:13px;line-height:1.5;color:{MUTED};padding-top:2px;">{detail}</div>
            </td>
            <td align="right" valign="top" style="padding:14px 16px;{border}white-space:nowrap;font-size:15px;font-weight:700;color:{accent};">
              {was}{price}
            </td>
          </tr>"""


def render(key: str, copy: dict) -> str:
    accent = copy["accent"]
    accent_ink = shade(accent, 0.18)
    wash = tint(accent, 0.92)
    promo = email_config.PROMO_URL
    site = email_config.WEBSITE_URL
    brand = email_config.BUSINESS_NAME
    intro = "".join(
        f'<p style="margin:0 0 16px 0;font-size:15px;line-height:1.7;color:{BODY};">'
        f"{text(p)}</p>" for p in copy["intro"])
    audience = text(copy["audience"])

    return f"""<!DOCTYPE html>
{VERSION_MARKER}
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>{text(copy["headline"])}</title>
<style>
  body {{ margin:0; padding:0; width:100%; background:{PAGE}; }}
  img {{ border:0; line-height:100%; outline:none; text-decoration:none; -ms-interpolation-mode:bicubic; }}
  table {{ border-collapse:collapse; }}
  a {{ color:{accent_ink}; }}
  @media only screen and (max-width:620px) {{
    .container {{ width:100% !important; }}
    .px {{ padding-left:22px !important; padding-right:22px !important; }}
    .h1 {{ font-size:23px !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:{PAGE};font-family:{FONT};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{PAGE};font-size:1px;line-height:1px;">
  {text(copy["preheader"])}
</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE};">
<tr><td align="center" style="padding:28px 12px;">
<table role="presentation" class="container" width="600" cellpadding="0" cellspacing="0"
  style="width:600px;max-width:600px;background:#ffffff;border:1px solid {LINE};border-radius:12px;overflow:hidden;font-family:{FONT};">

  <!-- Accent bar -->
  <tr><td style="height:4px;line-height:4px;font-size:4px;background:{accent};">&nbsp;</td></tr>

  <!-- Masthead -->
  <tr><td class="px" style="padding:22px 40px 0 40px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="font-size:15px;font-weight:800;color:{INK};letter-spacing:.2px;">{text(brand)}</td>
      <td align="right" style="font-size:12px;font-weight:600;color:{MUTED};text-transform:uppercase;letter-spacing:1px;">{text(copy["kicker"])}</td>
    </tr></table>
  </td></tr>

  <!-- Headline -->
  <tr><td class="px" style="padding:26px 40px 8px 40px;">
    <div class="h1" style="font-size:26px;line-height:1.25;font-weight:800;color:{INK};">{text(copy["headline"])}</div>
    <div style="font-size:16px;line-height:1.6;color:{MUTED};padding-top:10px;">{text(copy["subhead"])}</div>
  </td></tr>

<!--IF:HERO_IMAGE-->
  <!-- Website preview -->
  <tr><td class="px" style="padding:18px 40px 4px 40px;">
    <a href="{promo}" style="text-decoration:none;">
      <img src="{{{{HERO_IMAGE}}}}" width="520" alt="A preview of a new website for {{{{BUSINESS_NAME}}}}"
        style="display:block;width:100%;max-width:520px;height:auto;border:1px solid {LINE};border-radius:8px;">
    </a>
    <div style="font-size:12px;line-height:1.5;color:{FAINT};padding-top:8px;text-align:center;">
      A quick idea of what a new site for {{{{BUSINESS_NAME}}}} could look like.
    </div>
  </td></tr>
<!--ENDIF:HERO_IMAGE-->

  <!-- Intro -->
  <tr><td class="px" style="padding:22px 40px 0 40px;">
    <p style="margin:0 0 16px 0;font-size:15px;line-height:1.7;color:{INK};">Hi {{{{BUSINESS_NAME}}}} team,</p>
    {intro}
  </td></tr>

  <!-- Website status -->
  <tr><td class="px" style="padding:4px 40px 8px 40px;">{{{{CURRENT_WEBSITE_NOTE}}}}</td></tr>

  <!-- What you get -->
  <tr><td class="px" style="padding:18px 40px 4px 40px;">
    <div style="font-size:17px;font-weight:700;color:{INK};padding-bottom:6px;">What I'd build for {audience}</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{benefit_rows(copy["benefits"], accent)}
    </table>
  </td></tr>

  <!-- Offer -->
  <tr><td class="px" style="padding:20px 40px 6px 40px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{wash};border-radius:10px;">
      <tr><td style="padding:20px 22px;">
        <div style="font-size:12px;font-weight:700;color:{accent_ink};text-transform:uppercase;letter-spacing:1px;">Email-only price</div>
        <div style="font-size:15px;line-height:1.6;color:{BODY};padding-top:6px;">
          The <strong style="color:{INK};">Launchpad</strong> site is
          <strong style="color:{INK};font-size:18px;">{{{{LAUNCHPAD_SALE_PRICE}}}}</strong>
          <span style="color:{MUTED};">(normally {{{{LAUNCHPAD_PRICE}}}})</span>
          for businesses I reach out to, or {{{{ATTRIBUTION_PRICE}}}} with a small “Built by {text(brand)}” credit in the footer.
        </div>
      </td></tr>
    </table>
  </td></tr>

  <!-- Packages -->
  <tr><td class="px" style="padding:16px 40px 4px 40px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {LINE};border-radius:10px;">{package_row("Launchpad", "One-page mobile site, contact form and click-to-call, live in 24 hours.", "{{LAUNCHPAD_SALE_PRICE}}", accent=accent_ink)}{package_row("Professional", f"5–25 custom pages, SEO, Google Business setup; scales with {audience}.", "{{PROFESSIONAL_PRICE}}")}{package_row("Enterprise", "Bespoke build, e-commerce, integrations and ongoing management.", "{{ENTERPRISE_PRICE}}", last=True)}
    </table>
  </td></tr>

  <!-- Call to action -->
  <tr><td class="px" align="center" style="padding:28px 40px 6px 40px;">
    <table role="presentation" cellpadding="0" cellspacing="0"><tr>
      <td align="center" bgcolor="{accent_ink}" style="border-radius:8px;background:{accent_ink};">
        <a href="{promo}" style="display:inline-block;padding:13px 28px;font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;border-radius:8px;">See what I'd build for you</a>
      </td>
    </tr></table>
    <div style="font-size:13px;line-height:1.6;color:{MUTED};padding-top:12px;">Or just reply. A free 15-minute call, no pressure.</div>
  </td></tr>

  <!-- Snapshot -->
  <tr><td class="px" style="padding:22px 40px 0 40px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-top:1px solid {LINE};">
      <tr><td style="padding:16px 0 0 0;font-size:13px;line-height:1.7;color:{MUTED};">
        <div style="font-size:11px;font-weight:700;color:{FAINT};text-transform:uppercase;letter-spacing:1px;padding-bottom:4px;">What I found for {{{{BUSINESS_NAME}}}}</div>
        <div>{{{{CATEGORY}}}} · {{{{ADDRESS}}}}</div>
        {{{{RATING_INFO}}}}
        {{{{CONTACT_INFO}}}}
      </td></tr>
    </table>
  </td></tr>

  <!-- Signature -->
  <tr><td class="px" style="padding:22px 40px 28px 40px;font-size:15px;line-height:1.6;color:{BODY};">
    Thanks,<br>
    <strong style="color:{INK};">{{{{SENDER_NAME}}}}</strong><br>
    <span style="color:{MUTED};font-size:14px;">{text(brand)} · Web design &amp; development</span><br>
    <a href="{site}" style="color:{accent_ink};font-size:14px;text-decoration:none;">{site.replace("https://", "")}</a>
    <span style="color:{FAINT};">&nbsp;·&nbsp;</span>
    <a href="mailto:{{{{FROM_EMAIL}}}}" style="color:{accent_ink};font-size:14px;text-decoration:none;">{{{{FROM_EMAIL}}}}</a>
  </td></tr>

  <!-- Footer -->
  <tr><td class="px" style="background:#f9fafb;border-top:1px solid {LINE};padding:18px 40px;font-size:12px;line-height:1.6;color:{FAINT};">
    I'm writing because I think {{{{BUSINESS_NAME}}}} could win more customers online.
    Not interested? <a href="{{{{UNSUBSCRIBE_URL}}}}" style="color:{MUTED};">Unsubscribe</a> and I won't email again.
<!--IF:SENDER_ADDRESS-->
    <br>{text(brand)} · {{{{SENDER_ADDRESS}}}}
<!--ENDIF:SENDER_ADDRESS-->
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>
"""


def main() -> int:
    content = json.loads(CONTENT.read_text(encoding="utf-8"))
    known = {industry.key for industry in industries.all_industries()}
    missing = known - set(content)
    if missing:
        print(f"no copy for: {', '.join(sorted(missing))}", file=sys.stderr)
        return 1
    for key in sorted(known):
        path = OUT_DIR / f"{key}.html"
        path.write_text(render(key, content[key]), encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
