#!/usr/bin/env python3

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


BUNDLE_DIR = Path(__file__).resolve().parents[1]
ENTRYPOINT = BUNDLE_DIR / "scripts" / "transmission-entrypoint.sh"


class TransmissionEntrypointTest(unittest.TestCase):
    def test_secret_becomes_pass_without_file_prefix_reprocessing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            secret = root / "transmission-password"
            expected = "special/+&$password"
            secret.write_text(expected + "\n", encoding="utf-8")
            fake_init = root / "init"
            fake_init.write_text(
                "#!/bin/sh\n"
                "printf 'PASS=%s\\n' \"$PASS\"\n"
                "if env | grep -q '^FILE__PASS='; then echo FILE_PREFIX=set; else echo FILE_PREFIX=unset; fi\n",
                encoding="utf-8",
            )
            fake_init.chmod(0o755)
            environment = os.environ.copy()
            environment.update(
                {
                    "FILE__PASS": str(secret),
                    "READMABOOK_TRANSMISSION_INIT": str(fake_init),
                    "READMABOOK_TRANSMISSION_PASSWORD_FILE": str(secret),
                }
            )

            result = subprocess.run(
                ["bash", str(ENTRYPOINT)],
                check=False,
                capture_output=True,
                env=environment,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [f"PASS={expected}", "FILE_PREFIX=unset"])


if __name__ == "__main__":
    unittest.main()
