import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location(
    "manage", Path(__file__).parents[1] / "scripts/manage.py"
)
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


class WorkerStateTests(unittest.TestCase):
    def test_worker_state_omits_operator_only_subscription_fields(self):
        state = {
            "schema": 1,
            "entry": {"host": "notes.nikcode.xyz"},
            "subscriptions": [
                {
                    "label": "private-label",
                    "token": "private-token",
                    "hash": "a" * 64,
                    "format": "sing-box-ios-legacy",
                    "formats": ["sing-box-ios-legacy"],
                    "enabled": True,
                }
            ],
        }

        compact = manage.worker_state(state)

        self.assertEqual(compact["entry"], state["entry"])
        self.assertNotIn("label", compact["subscriptions"][0])
        self.assertNotIn("token", compact["subscriptions"][0])
        self.assertEqual(compact["subscriptions"][0]["hash"], "a" * 64)


if __name__ == "__main__":
    unittest.main()
