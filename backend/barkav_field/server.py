"""Local server for the desktop page (FD-07, desktop part). It listens on 127.0.0.1 only.

    py -3 -m uvicorn barkav_field.server:app --host 127.0.0.1 --port 8765

The data folder is backend/data unless BARKAV_FIELD_DATA_DIR is set (used by tests and demos).
Only the desktop page's own origins may call the API from a browser.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware

from .api import create_app

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
# The desktop page is served by the same app server as the phone page (dev 5173, preview 4173).
DESKTOP_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:4173", "http://localhost:4173"]

app = create_app(Path(os.environ.get("BARKAV_FIELD_DATA_DIR", DEFAULT_DATA_DIR)))
app.add_middleware(CORSMiddleware, allow_origins=DESKTOP_ORIGINS, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
