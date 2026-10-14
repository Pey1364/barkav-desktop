from __future__ import annotations

import sqlite3
from pathlib import Path


DATA_ROOT = Path(__file__).resolve().parents[2] / "BARKAV_Peymaan_18.5" / "data"


def main() -> None:
    files = sorted(
        set(DATA_ROOT.rglob("*.sqlite3"))
        | set(DATA_ROOT.rglob("*.sqlite"))
        | set(DATA_ROOT.rglob("*.db"))
    )
    print("DB_COUNT", len(files))
    for index, path in enumerate(files, 1):
        try:
            connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
            names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "expenses" not in names:
                print("DB", index, "NO_EXPENSES")
                connection.close()
                continue
            row = connection.execute(
                """
                SELECT COUNT(*),
                       COALESCE(SUM(final_amount), 0),
                       COALESCE(SUM(CASE WHEN manager_fee_eligible=1 THEN 1 ELSE 0 END), 0),
                       COALESCE(SUM(CASE WHEN manager_fee_eligible=1 THEN final_amount ELSE 0 END), 0)
                  FROM expenses
                 WHERE deleted_at IS NULL
                   AND status IN ('APPROVED','PARTIALLY_PAID','PAID')
                """
            ).fetchone()
            bps = "default"
            if "settings" in names:
                setting = connection.execute(
                    "SELECT value FROM settings WHERE key='manager_fee_bps'"
                ).fetchone()
                if setting:
                    bps = setting[0]
            print(
                "DB", index,
                "EXPENSES", row[0],
                "TOTAL", row[1],
                "ELIGIBLE", row[2],
                "ELIGIBLE_TOTAL", row[3],
                "BPS", bps,
            )
            connection.close()
        except Exception as exc:
            print("DB", index, "READ_ERROR", type(exc).__name__)


if __name__ == "__main__":
    main()
