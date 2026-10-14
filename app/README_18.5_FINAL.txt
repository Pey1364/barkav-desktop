BARKAV — Engineering & Construction — 18.5 Feature Freeze / Release Candidate
Date: 2026-08-20

START
1. Make a verified backup of the currently active BARKAV data folder and secrets.local.json.
2. Copy the active data folder into this 18.5 directory.
3. Copy secrets.local.json beside BARKAV_18.5.bat.
4. Run BARKAV_18.5.bat. The launcher validates dependencies, JSON structure and project data without logging secret values.

ACTIVE ENTRY POINTS
- BARKAV_18.5.bat
- launcher_stage18_5.py
- project_center_stage18_5.py
- project_runner_stage18_5.py
- dashboard_stage18_5.py
- ui_stage18_5.py

18.5 SCOPE
- Hang/flicker stabilization: event-driven table grids, cached receipt preview and one runner/bot per project.
- Reference-aligned Dark/Light shell, larger BARKAV wordmark, stable framed clock and fixed service-status badge widths.
- Startup TGJU USD refresh is asynchronous and persists only a successful rate.
- Project Details uses Persian digits, exact area parsing, total/parking/negative floor counts and a bottom-to-top editable structure for units, usage, areas, storage and supplied parking.
- Added Administrative Follow-up Responsible: name, company and phone.
- Data Entry imports Telegram Desktop JSON/ZIP backups into Pending; the two 18.4 attachment-only chat controls are not shown.
- Wizard-to-full-editor focus is raised after the Wizard closes; receipt preview no longer decodes the same image on repeated selection events.
- Financial Parameters and Indicators are side by side in an adjustable horizontal pane.
- System-visible version and all active launch paths are 18.5.

DATA / PRIVACY
- No live SQLite database, secrets.local.json, receipt/chat attachment, runtime log or user export is included.
- No finance schema change is made; schema stays v13.
- Imported chat history creates reviewable Pending records and has no financial effect before human approval.

VERIFICATION
- Full default suite: 209 passed, 30 GUI-gated skipped, 0 failed.
- Dedicated 18.5 regression: 19 passed.
- Forced GUI test attempt was blocked before app construction because both available Python runtimes lack Tcl/Tk init.tcl.
- Required target-machine checks: Windows UI/DPI/font, live Telegram/Gemini, TGJU, real project copy, backup/restore, Explorer shortcut icon and Printer/PDF.

This is the 18.5 feature-freeze candidate. Do not add features before the Step-1 stabilization gate passes.
