BARKAV / Peymaan 18.3 FINAL
===========================
Base: 18.2 FINAL
Scope: Exactly the 24 corrections requested on 2026-08-19. No unrelated accounting/database/receipt rules were intentionally changed.

PRIMARY START
  BARKAV_18.3.bat

WINDOWS ACCEPTANCE SETUP
  1) Extract this ZIP to a new folder.
  2) Copy the active/live data folder from your current installation into this folder.
  3) Copy your local secrets.local.json into this folder. Never share that file.
  4) Run INSTALL_REQUIREMENTS.bat if dependencies are missing.
  5) Run CREATE_SHORTCUT.bat to create the Desktop shortcut with the new B icon.
  6) Launch BARKAV_18.3.bat.

V18.3 RELEASE CHARACTER
- Persistent tabbed Project Center.
- Material Dark/Light visual redesign based on supplied reference screenshots.
- RTL subtabs and stronger grid hierarchy.
- Persian numeric display/input in the explicitly requested areas.
- Sales Contract/Deed document support.
- Project Team discipline filters + All + scrolling.
- Unified Print/Excel/PDF selectors.
- TGJU dollar-rate refresh with editable/manual fallback.
- Automatic settings UI recreation when required.

DATABASE
- Schema remains v13.
- 18.3 introduces no finance schema migration.

TEST MAPPING
See:
  BARKAV_V18.3_24_POINT_CHECKLIST_COMPLETED_2026-08-19.txt
  TEST_RESULTS_18.3_FINAL.txt
