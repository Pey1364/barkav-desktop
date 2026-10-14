"""تست کوچک‌سازی عکس‌های پیوست گزارش روزانه.

اجرا از داخل پوشه barkav-web-reports:
    python -m unittest discover -s tests -v
"""
import io
import os
import sys
import tempfile
import unittest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

os.environ["BARKAV_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test_photos.db")
os.environ["BARKAV_SECRET_KEY"] = "test-only-secret"

import app as app_module  # noqa: E402
from PIL import Image  # noqa: E402


def make_png_bytes(size=(4000, 3000)):
    """یک عکس بزرگ با گرادیان نرم می‌سازد؛ ابعادش مثل عکس موبایل است."""
    gradient = Image.linear_gradient("L").resize(size)
    img = Image.merge("RGB", (gradient, gradient, gradient))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


class PhotoCompressionTests(unittest.TestCase):
    def setUp(self):
        app_module.APP_PASSWORD = ""  # بدون ورود، فقط برای تست ذخیره پیوست
        app_module.app.config["TESTING"] = True
        self.upload_dir = tempfile.mkdtemp()
        app_module.app.config["UPLOAD_FOLDER"] = self.upload_dir
        self.client = app_module.app.test_client()

    def test_large_photo_is_resized_and_saved_as_jpeg(self):
        png = make_png_bytes()
        data = {
            "report_date": "1405/07/01",
            "work_summary": "تست فشرده‌سازی عکس",
            "photos": (io.BytesIO(png), "site.png"),
            "photo_captions": "عکس تست",
        }
        resp = self.client.post("/api/reports", data=data, content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["success"])

        saved = os.listdir(self.upload_dir)
        self.assertEqual(len(saved), 1)
        path = os.path.join(self.upload_dir, saved[0])
        self.assertTrue(saved[0].endswith(".jpg"))
        self.assertLess(os.path.getsize(path), 500 * 1024)

        with Image.open(path) as out:
            self.assertLessEqual(max(out.size), app_module.PHOTO_MAX_SIDE)
            self.assertEqual(out.format, "JPEG")

    def test_non_image_file_is_kept_unchanged(self):
        content = b"%PDF-1.4 fake pdf body for test"
        data = {
            "report_date": "1405/07/01",
            "work_summary": "تست فایل غیرعکس",
            "photos": (io.BytesIO(content), "report.pdf"),
            "photo_captions": "سند",
        }
        resp = self.client.post("/api/reports", data=data, content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 200)

        saved = os.listdir(self.upload_dir)
        self.assertEqual(len(saved), 1)
        self.assertTrue(saved[0].endswith(".pdf"))
        with open(os.path.join(self.upload_dir, saved[0]), "rb") as f:
            self.assertEqual(f.read(), content)


if __name__ == "__main__":
    unittest.main()
