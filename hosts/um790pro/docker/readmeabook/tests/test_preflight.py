#!/usr/bin/env python3

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


BUNDLE_DIR = Path(__file__).resolve().parents[1]
PREFLIGHT = BUNDLE_DIR / "scripts" / "preflight.sh"


class PreflightTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.state_root = self.root / "state"
        self.state_root.mkdir()
        self.state_root.chmod(0o700)
        self.secrets_root = self.root / "secrets"
        self.secrets_root.mkdir()
        for name in (
            "abs-api-token",
            "publisher-ssh-key",
            "rmab-config-encryption-key",
            "rmab-api-token",
            "rmab-jwt-refresh-secret",
            "rmab-jwt-secret",
            "rmab-postgres-password",
            "transmission-password",
        ):
            path = self.secrets_root / name
            path.write_text("test-secret")
            path.chmod(0o600)
        self.publisher_config = self.root / "publisher.json"
        self.publisher_config.write_text(json.dumps({"state_dir": "/tmp/state"}))
        self.remote_incoming = self.root / "incoming"
        self.remote_final = self.root / "final"
        self.remote_incoming.mkdir()
        self.remote_final.mkdir()
        self.remote_incoming.chmod(0o700)
        self.remote_final.chmod(0o2775)
        self.write_fake("docker", "exit 0")
        self.write_fake("tailscale", "printf '%s\\n' \"$READMABOOK_TEST_TAILSCALE_IP\"")
        self.write_fake("ssh", "printf '%s\\n' '{\"free_bytes\":999999999999}'")
        self.write_fake("systemctl", "exit 0")
        self.write_fake("curl", "exit 0")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write_fake(self, name: str, body: str) -> None:
        path = self.bin_dir / name
        path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        path.chmod(0o755)

    def environment(self, tailscale_ip: str) -> dict[str, str]:
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{self.bin_dir}:{environment['PATH']}",
                "READMABOOK_EXPECTED_ARCH": os.uname().machine,
                "READMABOOK_EXPECTED_TAILSCALE_IP": tailscale_ip,
                "READMABOOK_FINAL_ROOT": str(self.remote_final),
                "READMABOOK_INCOMING_ROOT": str(self.remote_incoming),
                "READMABOOK_MIN_LOCAL_FREE_GIB": "0",
                "READMABOOK_MIN_REMOTE_FREE_GIB": "0",
                "READMABOOK_PUBLISHER_CONFIG": str(self.publisher_config),
                "READMABOOK_REMOTE_WRAPPER": str(BUNDLE_DIR / "scripts/remote-wrapper.py"),
                "READMABOOK_REMOTE_UID": str(os.getuid()),
                "READMABOOK_SECRETS_ROOT": str(self.secrets_root),
                "READMABOOK_SECRETS_UID": str(os.getuid()),
                "READMABOOK_STATE_ROOT": str(self.state_root),
                "READMABOOK_STATE_UID": str(os.getuid()),
                "READMABOOK_TEST_TAILSCALE_IP": tailscale_ip,
            }
        )
        return environment

    def run_preflight(self, host: str, tailscale_ip: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(PREFLIGHT), "--host", host],
            check=False,
            capture_output=True,
            env=self.environment(tailscale_ip),
            text=True,
        )

    def test_um790pro_preflight_validates_without_writing_state(self) -> None:
        before = sorted(path.relative_to(self.root) for path in self.root.rglob("*"))

        result = self.run_preflight("um790pro", "100.95.213.117")

        after = sorted(path.relative_to(self.root) for path in self.root.rglob("*"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)
        self.assertIn("remote publisher capacity", result.stdout)
        self.assertEqual(before, after)

    def test_moscow_preflight_checks_confined_roots_and_existing_services(self) -> None:
        result = self.run_preflight("moscow", "100.81.67.47")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("same filesystem", result.stdout)
        self.assertIn("Audiobookshelf", result.stdout)
        self.assertIn("system Transmission", result.stdout)

    def test_moscow_owner_default_follows_the_operator_account(self) -> None:
        source = PREFLIGHT.read_text()

        self.assertIn('local remote_uid=${READMABOOK_REMOTE_UID:-$(id -u)}', source)

    def test_preflight_fails_closed_for_an_insecure_secret(self) -> None:
        (self.secrets_root / "abs-api-token").chmod(0o644)

        result = self.run_preflight("um790pro", "100.95.213.117")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("abs-api-token permissions", result.stdout)
        self.assertIn("FAIL", result.stdout)


if __name__ == "__main__":
    unittest.main()
