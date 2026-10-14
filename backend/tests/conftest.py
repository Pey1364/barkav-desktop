"""Make the backend package importable when pytest runs from the backend folder."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
