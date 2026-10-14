# Changelog

## Unreleased

- Web receipt intake on branch `feature/web-receipts`: a local HTTPS page sends photos and captions to an inbox, and a manual command moves them into the review queue (WR-01 to WR-09, DB-01, DB-02). See `app/docs/architecture/MODULE_REGISTRY.md`.
- Database: `pending_items` gains `source` and `external_ref` columns (ADR-0001). Existing rows are unchanged.
- Architecture notes, module IDs and the receipt inbox contract are in `app/docs/`.

## 19.1.1 — first public release

- Starts the public history from the 19.1.1 line of BARKAV. Earlier commits and
  development history are not included.
- Adds MIT license, contributor and security guidance, and issue and pull request
  templates.
- Known failing tests on a clean checkout are listed in the README.
