from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from receipt_intelligence import LocalOCREngine, extract_amount_candidates


def main():
    ocr = LocalOCREngine()
    print("Peymaan Stage 14 - Receipt Diagnostic")
    print("Local OCR available:", "YES" if ocr.available() else "NO")
    if ocr.available():
        print("OCR language:", ocr.effective_lang())
        try:
            import pytesseract
            print("Tesseract:", pytesseract.get_tesseract_version())
        except Exception as exc:
            print("Tesseract version error:", exc)
    else:
        print("Install Tesseract OCR with Persian (fas) language data, or set PEYMAAN_TESSERACT_CMD.")

    if len(sys.argv) > 1:
        src = Path(sys.argv[1])
        if not src.exists():
            raise SystemExit(f"File not found: {src}")
        with tempfile.TemporaryDirectory() as td:
            dst = Path(td) / "prepared.jpg"
            ocr.preprocess(src, dst)
            result = ocr.extract(dst)
            print("\nProvider:", result.provider)
            print("Available:", result.available)
            if result.error:
                print("Error:", result.error)
            print("\nOCR text (first 4000 chars):\n", result.text[:4000])
            print("\nToman amount candidates:", [f"{x:,}" for x in extract_amount_candidates(result.text)])


if __name__ == "__main__":
    main()
