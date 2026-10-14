BARKAV / Peymaan 18.7 — Word Corrections + Theme Integration
=============================================================

Scope lock
----------
- 18.6 remains the immutable behavior/reference baseline.
- 18.7 contains only items requested in «اصلاحات18.6.docx» and the supplied
  `new theme` package.
- No database schema, accounting rule, Telegram routing rule, or finance
  migration is introduced by this layer.

Implemented in the current working build
----------------------------------------
- Theme 1: exact 18.6 token baseline, Dark and Light.
- Theme 2: independent Dark and Light tokens derived from the 16 references.
- Theme selection in Settings; visual changes restart only the UI process.
- Theme 2 large image navigation icons and top-command icons.
- Large chart detail windows on double click; the donut detail lists every
  phase whose share is greater than 1 percent.
- Dashboard-card header links to related screens; the 30-day card opens the
  large financial calendar.
- Messages beside the clock and startup reminders for upcoming cheques,
  buyer receivables, and loan installments.
- Persian month/day search, previous/next month navigation, and colored event
  types in the financial calendar.
- Previous receipts visible by default through the existing all-status view.
- Project Center tabs close only through the explicit right-side cross zone.
- Telegram ready/inbound/status runtime files isolated per project.
- Main Treeviews receive RTL display ordering in the 18.7 layer.
- Phase-detail selector plus previous/next phase controls.
- Report row checkboxes, right-click price add/edit/delete/copy/paste,
  bottom action bars, price category selector, and full price catalog window.
- Open-estimate-file button; a saved Excel edit can be imported as a new
  dated/versioned estimate when focus returns to BARKAV.

Intentionally reused from completed 18.6 work
---------------------------------------------
- BARKAV 18.4 branding/tagline correction.
- project detail header, roof storage row, two-column unit details, and
  four-column project team.
- currency rendering, manager snapshot metrics, and explicit report calculate
  action.
- existing financial posting services for approved loan receipts, buyer
  receipts, and loan installments.

Local activation
----------------
This clean working copy intentionally excludes `secrets.local.json`, runtime
logs, and live databases. After a verified backup, copy only the local secret
file and the active `data` folder into this 18.7 directory, then run
`BARKAV_18.7.bat`.
