from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parents[1]

class NetworkPatchTests(unittest.TestCase):
    def test_stage9_uses_resilience_constants(self):
        s=(BASE/'telegram_stage9.py').read_text(encoding='utf-8')
        self.assertIn('GET_UPDATES_READ_TIMEOUT', s)
        self.assertIn('bootstrap_retries=-1', s)
        self.assertIn('get_updates_http_version("1.1")', s)
        self.assertIn('configure_telegram_network_logging()', s)

    def test_resilience_module_has_rate_limited_filter(self):
        s=(BASE/'telegram_resilience.py').read_text(encoding='utf-8')
        self.assertIn('_notice_interval = 60.0', s)
        self.assertIn('Telegram network timeout; automatic retry is active.', s)

if __name__ == '__main__':
    unittest.main()
