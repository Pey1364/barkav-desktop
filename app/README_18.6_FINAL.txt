BARKAV — Engineering & Construction — Version 18.6
GUI Focus / Stabilization Candidate

RUN
1. Close every BARKAV and Telegram-bot process.
2. Back up the active live data folder.
3. Replace the placeholder data folder in 18.6 with the complete active data folder.
4. Copy secrets.local.json beside BARKAV_18.6.bat.
5. Run BARKAV_18.6.bat.

MAIN 18.6 CHANGES
- Reference-aligned compact Dark/Light shell and five-card dashboard.
- 18.4 brand artwork with BARKAV larger than Engineering & Construction.
- Two-column floors/units, permanent roof storage row and four-column project team.
- Faint table separators, lighter transaction bands and framed Telegram/Gemini state.
- Visible calculation button under Financial Indicator parameters.
- Display-only Toman/Rial/Dollar conversion and filter-aware table totals.
- Manager account values forced from the authoritative DB snapshot.

DATA SAFETY
- Database schema remains v13.
- SQLite monetary values remain Toman; changing display currency does not rewrite amounts.
- Telegram/chat imports remain Pending-first and have no final financial effect before approval.
- The release ZIP does not include live DBs, secrets, logs or user attachments.

VERIFICATION
- Dedicated 18.6 regression: 16 passed.
- Windows GUI: 2 passed.
- Full default suite: 224 passed, 34 skipped, 0 failed.
- Live Telegram/Gemini/TGJU and printer/PDF still require acceptance with copied live data.
