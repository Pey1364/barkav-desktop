# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's private
reporting: **Security → Report a vulnerability** on this repository. Include the
steps to reproduce and the version or commit you tested.

You can expect a first reply within a week. BARKAV has a single maintainer, so
fixes are made on a best-effort basis.

## What counts

BARKAV is a local desktop application that stores financial data in SQLite and
can talk to Telegram, Google and AI providers with the user's own keys. Reports
about the following are in scope:

- a way to post, change or delete financial data without the approval step
- secrets (bot token, API keys, Google credentials) written to logs, exports or
  the repository
- Telegram or AI input that changes accounting data before a person approves it
- path handling that lets an attachment or import write outside its project
  folder

## Handling secrets and data

- `secrets.local.json`, databases (`*.sqlite3`), project shortcuts (`*.brk`) and
  receipt archives are listed in `.gitignore`. Never commit them.
- If you find a real key or personal record in this repository or its history,
  report it privately as above so it can be revoked and removed.
