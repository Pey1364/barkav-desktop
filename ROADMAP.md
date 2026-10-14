# Roadmap

This file lists what the maintainer plans to work on next. Items are grouped by
status. "Planned" means the work is decided and scheduled. "Exploring" means it
is an idea that still needs a feasibility check. Nothing here is a promise of a
date.

Feedback is welcome. Open an issue, or comment on an existing one.

## Planned

### 1. Make the public release easy to try and to verify

- **Demo project with fake data.** A sample project database and sample
  documents, so anyone can run BARKAV without real records. No real names,
  amounts or receipts will ship.
- **Continuous integration.** A GitHub Actions workflow on `windows-latest` that
  runs the tests that do not need a display first, then the Tk tests on a
  virtual display where possible.
- **Full test run and known failures.** Run the whole suite on a clean clone,
  fix the failures listed in the README, and keep the list up to date.
- **Locked dependencies.** Pin exact versions for the runtime and development
  requirements, so a fresh install behaves the same way every time.
- **Portable build on GitHub Releases.** Use the existing `build_portable.py`
  to publish a Windows build with each tagged release.
- **English setup and architecture docs.** The current design notes are in
  Persian. Setup, configuration and the financial rules will also be written in
  English.

### 2. Safer handling of secrets

- Stop storing the Telegram token, Gemini key and Google credentials in plain
  `secrets.local.json`. Read them from the Windows Credential Manager, and keep
  the JSON file only as a fallback for development.

### 3. Receipts from a phone

- A small mobile companion app to photograph a receipt and add a caption.
- It sends items into the same pending-approval queue the Telegram bot uses
  today. A phone capture never posts a financial row by itself; a person still
  approves it in the desktop app.

## Exploring

### 4. Quantities from drawings for estimating

- The goal is to read quantities from a drawing and feed them into the phase
  estimate as JSON.
- AutoCAD's DWG format is proprietary. The realistic path is to export DXF
  from the drawing software and read it with an open-source library such as
  `ezdxf`, then write a JSON file with the layers, blocks and measured
  quantities.
- An AI model may suggest how to map layers to estimate items. It does not
  decide the quantities, and the person confirms every mapping before it is used.

### 5. Web version: backend and frontend

- A `webui/` experiment already exists: a small Python bridge that serves a
  page inside a desktop window.
- The next step is to decide between two options: a Python backend (for example
  FastAPI) with a separate web frontend, or keeping the desktop shell and moving
  only the screens. The decision will be made after the demo project and CI are
  in place, so the choice can be checked against working tests.
- The desktop app stays the reference. Both versions must produce the same
  financial results on the same data.

### 6. Excel and CSV round trips

- Import and export of the estimate and the transaction lists in a format an
  accountant can edit, with a preview before anything is written to the
  database.

## Limits on the engineering features

BARKAV records, phases and tracks construction work. It is not a structural or
architectural calculation tool, and it will not present its output as one.

- Any structural calculation that affects safety must be carried out and signed
  by a licensed engineer. BARKAV can store the documents and the approvals.
- Architectural and structural modules will focus on drawings, approvals,
  phases and cost links, not on load or design calculations.

## Smaller improvements, when there is time

- Use the BARKAV project name as configuration, so the company name in reports
  is not fixed in the code.
- Add a linter and a type checker to the CI workflow.
- Reduce the number of legacy `stage` modules. This is a large change and will
  only happen with the full test suite passing before and after each step.
