from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import unittest

from audiobook_ops.runtime import build_runtime


BUNDLE = Path(__file__).resolve().parents[1]


class ProductionAssetTests(unittest.TestCase):
    def test_compose_requires_an_immutable_app_image_and_separate_secret_files(self) -> None:
        compose = (BUNDLE / "docker-compose.yml").read_text()

        self.assertIn("${AUDIOBOOK_OPS_IMAGE:?", compose)
        for image in re.findall(r"^\s+image:\s+(\S+)", compose, re.MULTILINE):
            self.assertTrue("@sha256:" in image or image.startswith("${AUDIOBOOK_OPS_IMAGE:"))
        for name in (
            "abs-api-token",
            "mcp-bearer",
            "prowlarr-api-key",
            "transmission-password",
        ):
            self.assertIn(f"/{name}", compose)
        self.assertNotRegex(
            compose,
            r"(?im)(token|password):[ \t]+[^$/{\n][^\n]*",
        )

    def test_systemd_assets_are_neutral_hardened_and_restart_ordered(self) -> None:
        systemd = BUNDLE / "systemd"
        expected = {
            "audiobook-ops-backup.service",
            "audiobook-ops-backup.timer",
            "audiobook-ops-cleanup.service",
            "audiobook-ops-cleanup.timer",
            "audiobook-ops-compose.service",
            "audiobook-ops-healthcheck.service",
            "audiobook-ops-healthcheck.timer",
            "audiobook-ops-policy.service",
            "audiobook-ops-policy.timer",
            "audiobook-ops-publisher.service",
            "audiobook-ops-publisher.timer",
            "audiobook-ops-worker.service",
            "audiobook-ops-worker.timer",
        }
        self.assertEqual({path.name for path in systemd.iterdir()}, expected)
        serialized = "\n".join(path.read_text().casefold() for path in systemd.iterdir())
        self.assertNotIn("rmab", serialized)
        self.assertNotIn("postgres", serialized)
        self.assertNotIn("redis", serialized)
        for service in systemd.glob("*.service"):
            body = service.read_text()
            self.assertIn("NoNewPrivileges=true", body, service.name)
            self.assertIn("ProtectSystem=strict", body, service.name)
            self.assertIn("TimeoutStartSec=", body, service.name)
            if service.name != "audiobook-ops-compose.service":
                self.assertIn(
                    "Requires=audiobook-ops-compose.service", body, service.name
                )
        compose = (systemd / "audiobook-ops-compose.service").read_text()
        self.assertIn("After=docker.service network-online.target tailscaled.service", compose)
        self.assertIn("Restart=on-failure", compose)
        self.assertIn(
            "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK", compose
        )
        policy = (systemd / "audiobook-ops-policy.service").read_text()
        self.assertIn(
            "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK", policy
        )
        serialized = {
            "audiobook-ops-backup.service",
            "audiobook-ops-cleanup.service",
            "audiobook-ops-healthcheck.service",
            "audiobook-ops-policy.service",
            "audiobook-ops-publisher.service",
            "audiobook-ops-worker.service",
        }
        lock = "/usr/bin/flock --exclusive --timeout 300 /run/audiobook-ops/operations.lock"
        for name in serialized:
            self.assertIn(lock, (systemd / name).read_text(), name)
        for name in (
            "audiobook-ops-worker.service",
            "audiobook-ops-cleanup.service",
        ):
            body = (systemd / name).read_text()
            self.assertIn(
                "/usr/bin/docker exec --user 1000:1000 audiobook-ops",
                body,
                name,
            )
            self.assertIn(
                "--config /run/audiobook-ops-runtime/config.json",
                body,
                name,
            )
        healthcheck = (systemd / "audiobook-ops-healthcheck.service").read_text()
        self.assertIn(
            "ReadWritePaths=/home/nik/services/audiobook-ops", healthcheck
        )
        tmpfiles = (BUNDLE / "tmpfiles/audiobook-ops.conf").read_text()
        self.assertIn("/run/audiobook-ops/operations.lock 0660 nik nik", tmpfiles)
        checklist = BUNDLE / "scripts/verify-startup.sh"
        self.assertTrue(checklist.stat().st_mode & 0o111)
        checklist_text = checklist.read_text()
        for name in expected:
            if name.endswith(".timer") or name == "audiobook-ops-compose.service":
                self.assertIn(name, checklist_text)

    def test_logs_are_structured_bounded_and_retained_for_thirty_days(self) -> None:
        compose = (BUNDLE / "docker-compose.yml").read_text()
        rotation = (BUNDLE / "logrotate/audiobook-ops").read_text()

        self.assertIn("max-size: 50m", compose)
        self.assertIn('max-file: "3"', compose)
        self.assertIn("rotate 30", rotation)
        self.assertIn("daily", rotation)
        self.assertIn("maxsize 50M", rotation)
        self.assertIn("compress", rotation)
        tmpfiles = (BUNDLE / "tmpfiles/audiobook-ops.conf").read_text()
        self.assertIn("/var/log/audiobook-ops", tmpfiles)
        self.assertIn("30d", tmpfiles)
        for service in (BUNDLE / "systemd").glob("*.service"):
            if service.name == "audiobook-ops-compose.service":
                continue
            self.assertIn(".jsonl", service.read_text(), service.name)

    def test_runtime_configs_name_limits_and_never_embed_credentials(self) -> None:
        configs = list((BUNDLE / "config").glob("*.example.json"))
        serialized = "\n".join(path.read_text() for path in configs)
        for path in configs:
            json.loads(path.read_text())
        for secret_name in (
            "abs-api-token",
            "mcp-bearer",
            "prowlarr-api-key",
            "publisher-ssh-key",
            "transmission-password",
        ):
            self.assertIn(secret_name, serialized)
        self.assertNotIn("REPLACE_WITH", serialized)
        self.assertNotIn("example-secret", serialized)
        runtime = json.loads(
            (BUNDLE / "config/audiobook-ops.example.json").read_text()
        )
        self.assertEqual(
            runtime["backup_evidence_file"],
            "/var/lib/audiobook-ops/backup-health.json",
        )
        self.assertNotIn("backup_root", runtime)
        backup = json.loads((BUNDLE / "config/backup.example.json").read_text())
        self.assertEqual(
            set(backup["operator_files"]),
            {
                "audiobook-ops.json",
                "backup.json",
                "compose.env",
                "health.json",
                "policy.json",
                "publisher.json",
            },
        )
        self.assertEqual(
            set(backup["secret_files"]),
            {
                "abs-api-token",
                "mcp-bearer",
                "prowlarr-api-key",
                "publisher-ssh-key",
                "transmission-password",
            },
        )
        self.assertEqual(
            set(backup["retained_state"]),
            {"flaresolverr", "prowlarr", "transmission"},
        )

    def test_owner_gated_scripts_default_to_read_only_preview(self) -> None:
        for name in ("backup.py", "restore-rehearsal.py", "policy.py", "worker.py"):
            body = (BUNDLE / "scripts" / name).read_text()
            self.assertIn("--execute", body, name)
        preflight = (BUNDLE / "scripts/preflight.sh").read_text()
        self.assertNotIn("sudo", preflight)
        self.assertNotIn("docker compose up", preflight)
        self.assertNotIn("systemctl start", preflight)
        self.assertIn("installed bundle root-owned and immutable", preflight)
        self.assertIn("operator config root-owned and service-readable", preflight)

    def test_preflight_permission_masks_group_arithmetic_before_comparison(self) -> None:
        preflight = (BUNDLE / "scripts/preflight.sh").read_text()
        self.assertIn("(( (8#$mode & 8#022) == 0 ))", preflight)
        self.assertIn("(( (8#$mode & 8#200) != 0 ))", preflight)
        self.assertIn("operator config readable by service group", preflight)
        self.assertIn("operator config root-owned and service-readable", preflight)
        self.assertIn("$gid == 1000 && $mode == 640", preflight)

    def test_runbook_makes_operator_config_readable_by_service_group(self) -> None:
        runbook = (BUNDLE / "PRODUCTION-RUNBOOK.md").read_text()
        self.assertIn(
            "install -d -o root -g nik -m 0750 /etc/audiobook-ops/config",
            runbook,
        )
        self.assertIn(
            "cd /home/nik/.local/share/nix-config-services/readmeabook",
            runbook,
        )
        self.assertIn("`root:nik` mode `0640`", runbook)

    def test_runtime_secret_values_do_not_enter_sqlite_or_tool_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secrets = root / "secrets"
            backups = root / "backups"
            secrets.mkdir()
            backups.mkdir()
            values = {
                "abs": "sentinel-abs-4cab8d2d",
                "mcp": "sentinel-mcp-4cab8d2d",
                "prowlarr": "sentinel-prowlarr-4cab8d2d",
                "transmission": "sentinel-transmission-4cab8d2d",
            }
            paths: dict[str, Path] = {}
            for name, value in values.items():
                path = secrets / name
                path.write_text(value)
                paths[name] = path
            config = root / "runtime.json"
            database = root / "state.sqlite3"
            config.write_text(
                json.dumps(
                    {
                        "abs_api_token_file": str(paths["abs"]),
                        "abs_url": "http://127.0.0.1:1",
                        "backup_evidence_file": str(root / "backup-health.json"),
                        "database_path": str(database),
                        "mcp_bearer_file": str(paths["mcp"]),
                        "prowlarr_api_key_file": str(paths["prowlarr"]),
                        "prowlarr_url": "http://127.0.0.1:2",
                        "transmission_password_file": str(paths["transmission"]),
                        "transmission_url": "http://127.0.0.1:3/transmission/rpc",
                        "vless_evidence_file": str(root / "vless.json"),
                        "vless_route_health_url": "http://127.0.0.1:4/health",
                    }
                )
            )
            runtime = build_runtime(config)
            try:
                result = runtime.adapter.call("task_list", {})
            finally:
                runtime.close()
            persisted = b"".join(
                path.read_bytes()
                for path in root.iterdir()
                if path.is_file() and path.name.startswith("state.sqlite3")
            )
            exposed = json.dumps(result, sort_keys=True)

        for secret in values.values():
            self.assertNotIn(secret.encode(), persisted)
            self.assertNotIn(secret, exposed)


if __name__ == "__main__":
    unittest.main()
