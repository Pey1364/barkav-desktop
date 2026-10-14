BARKAV / Peymaan 18.4 FINAL
===========================
Base: 18.3
Scope: Only the targeted 18.4 corrections requested after 18.3. Save As item 12 is intentionally deferred.

PRIMARY START
  BARKAV_18.4.bat

WINDOWS SETUP
  1) Extract this ZIP to a new folder.
  2) Copy your active/live data into this folder as instructed by data/COPY_LIVE_DATA_HERE.txt.
  3) Copy your local secrets.local.json into this folder. Never share that file.
  4) Run INSTALL_REQUIREMENTS.bat if dependencies are missing.
  5) Run CREATE_SHORTCUT.bat. It creates BARKAV 18.4.lnk with assets/BARKAV_18_4.ico.
  6) Launch BARKAV_18.4.bat.

18.4 HIGHLIGHTS
- Updated Persian numbers/fonts in Transaction/Sales/Report table views.
- USD rate controls centralized in Settings.
- RTL Project Units.
- Unified transaction double-click editor routing.
- Quick sun/moon theme toggle.
- Faint table column dividers + row-selection checkboxes.
- Project Center New/Open .barkav shortcuts, real counter, closeable tabs, Persian IDs.
- Larger BARKAV tagline and Project Center branding.
- Rebuilt Windows shortcut icon with a unique 18.4 icon filename.
- Requested Transactions tab ordering.
- Brighter Data Entry transaction-row colors.
- Chat-history attachment/view support in Data Entry.

DEFERRED
- Save As / named project-copy feature (request 12) is reserved for future development.

DATABASE / BUSINESS LOGIC
- Schema remains v13.
- Core V18.3 finance/database/AI Python modules were checksum-audited and not changed.

TESTS
- Default full suite: 190 passed, 28 GUI-gated skipped.
- Full GUI suite: 218/218 passed.
