"""تست ورود با رمز برای نسخه وب گزارشات روزانه.

اجرا از داخل پوشه barkav-web-reports:
    python -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import unittest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# دیتابیس موقت و رمز آزمایشی قبل از import برنامه تنظیم می‌شوند
os.environ["BARKAV_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test_auth.db")
os.environ["BARKAV_APP_PASSWORD"] = "رمز-آزمایشی-۱۲۳"
os.environ["BARKAV_SECRET_KEY"] = "test-only-secret"

import app as app_module  # noqa: E402

TEST_PASSWORD = "رمز-آزمایشی-۱۲۳"


class LoginGateTests(unittest.TestCase):
    def setUp(self):
        app_module.APP_PASSWORD = TEST_PASSWORD
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()

    def test_index_redirects_to_login_when_anonymous(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_api_returns_401_when_anonymous(self):
        resp = self.client.post("/api/reports", data={"report_date": "1405/01/01"})
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(resp.get_json()["success"])

    def test_uploads_are_protected(self):
        resp = self.client.get("/uploads/anything.jpg")
        self.assertEqual(resp.status_code, 302)

    def test_login_page_and_static_are_public(self):
        resp = self.client.get("/login")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"barkav_report_512.png", resp.data)
        self.assertEqual(self.client.get("/static/manifest.json").status_code, 200)

    def test_wrong_password_is_rejected(self):
        resp = self.client.post("/login", data={"password": "نادرست"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("رمز ورود اشتباه است.".encode("utf-8"), resp.data)
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_persian_password_logs_in_and_logout_clears_session(self):
        resp = self.client.post("/login", data={"password": TEST_PASSWORD})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.client.get("/").status_code, 200)

        self.client.get("/logout")
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_login_disabled_when_no_password_configured(self):
        app_module.APP_PASSWORD = ""
        self.assertEqual(self.client.get("/").status_code, 200)
        resp = self.client.get("/login")
        self.assertEqual(resp.status_code, 302)


if __name__ == "__main__":
    unittest.main()
