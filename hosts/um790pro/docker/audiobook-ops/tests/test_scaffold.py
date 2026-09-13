from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


BUNDLE = Path(__file__).resolve().parents[1]


class AudiobookOpsScaffoldTests(unittest.TestCase):
    def render_compose(self) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            retained = root / "retained"
            state = root / "state"
            secrets = root / "secrets"
            for directory in (retained, state, secrets):
                directory.mkdir()
            environment = os.environ.copy()
            environment.update(
                {
                    "AUDIOBOOK_OPS_CONFIG_FILE": str(
                        BUNDLE / "config" / "audiobook-ops.example.json"
                    ),
                    "AUDIOBOOK_OPS_RETAINED_STATE_ROOT": str(retained),
                    "AUDIOBOOK_OPS_SECRETS_ROOT": str(secrets),
                    "AUDIOBOOK_OPS_STATE_ROOT": str(state),
                    "AUDIOBOOK_OPS_TAILSCALE_IP": "100.64.0.42",
                }
            )
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(BUNDLE / "docker-compose.yml"),
                    "config",
                    "--format",
                    "json",
                ],
                check=True,
                cwd=BUNDLE,
                env=environment,
                text=True,
                capture_output=True,
            )
        return json.loads(result.stdout)

    def test_compose_renders_the_target_topology_without_public_ingress(self) -> None:
        rendered = self.render_compose()
        services = rendered["services"]

        self.assertEqual(
            set(services),
            {
                "audiobook-ops",
                "flaresolverr",
                "prowlarr",
                "rutracker-gateway",
                "transmission",
            },
        )
        self.assertEqual(
            services["audiobook-ops"]["ports"],
            [
                {
                    "host_ip": "100.64.0.42",
                    "mode": "ingress",
                    "protocol": "tcp",
                    "published": "8300",
                    "target": 8000,
                }
            ],
        )
        self.assertEqual(
            services["prowlarr"]["ports"][0]["host_ip"], "127.0.0.1"
        )
        for internal_service in ("flaresolverr", "rutracker-gateway", "transmission"):
            self.assertNotIn("ports", services[internal_service])

    def test_compose_preserves_retained_state_and_uses_a_neutral_control_root(self) -> None:
        rendered = self.render_compose()
        services = rendered["services"]
        retained_root = Path(
            os.path.commonpath(
                volume["source"]
                for name in ("prowlarr", "transmission")
                for volume in services[name]["volumes"]
                if volume["target"] in {"/config", "/downloads"}
            )
        )

        self.assertEqual(retained_root.name, "retained")
        ops_volumes = {
            volume["target"]: volume["source"]
            for volume in services["audiobook-ops"]["volumes"]
        }
        self.assertTrue(ops_volumes["/var/lib/audiobook-ops"].endswith("/state"))
        self.assertTrue(ops_volumes["/downloads"].endswith("/retained/downloads"))
        self.assertTrue(ops_volumes["/staging"].endswith("/state/staging"))

    def test_all_upstream_images_and_the_python_base_are_digest_pinned(self) -> None:
        rendered = self.render_compose()
        for name, service in rendered["services"].items():
            if name == "audiobook-ops":
                self.assertEqual(service["image"], "localhost/audiobook-ops:0.1.0")
                continue
            self.assertRegex(service["image"], r"@sha256:[0-9a-f]{64}$")

        dockerfile = (BUNDLE / "Dockerfile").read_text()
        self.assertRegex(
            dockerfile,
            r"(?m)^FROM python:3\.13\.7-slim-bookworm@sha256:[0-9a-f]{64}$",
        )
        self.assertNotIn(":latest", dockerfile)
        self.assertRegex(dockerfile, r"apt-get install[^\n]*ffmpeg")

    def test_secrets_are_file_mounted_and_absent_from_environment(self) -> None:
        rendered = self.render_compose()
        ops = rendered["services"]["audiobook-ops"]
        self.assertEqual(
            {secret["source"] for secret in ops["secrets"]},
            {
                "abs_api_token",
                "mcp_bearer",
                "prowlarr_api_key",
                "transmission_password",
            },
        )
        serialized_environment = json.dumps(ops.get("environment", {})).lower()
        for sensitive_name in ("bearer", "password", "token", "api_key"):
            self.assertNotIn(sensitive_name, serialized_environment)

        secret_files = {
            Path(value["file"]).name for value in rendered["secrets"].values()
        }
        self.assertEqual(
            secret_files,
            {
                "abs-api-token",
                "mcp-bearer",
                "prowlarr-api-key",
                "transmission-password",
            },
        )

    def test_package_entrypoint_reports_distinct_scaffold_health(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(BUNDLE / "src")

        def health(component: str) -> tuple[int, dict[str, str]]:
            result = subprocess.run(
                [sys.executable, "-m", "audiobook_ops", "health", component],
                cwd=BUNDLE,
                env=environment,
                text=True,
                capture_output=True,
            )
            return result.returncode, json.loads(result.stdout)

        self.assertEqual(health("core"), (0, {"component": "core", "status": "ok"}))
        self.assertEqual(
            health("catalog"),
            (1, {"component": "catalog", "status": "unconfigured"}),
        )
        self.assertEqual(
            health("external-search"),
            (1, {"component": "external-search", "status": "unconfigured"}),
        )

    def test_new_bundle_has_no_readmeabook_application_dependency(self) -> None:
        rendered = self.render_compose()
        self.assertNotIn("readmeabook", rendered["services"])
        self.assertNotIn("postgres", rendered["services"])
        self.assertNotIn("redis", rendered["services"])

        source_text = "\n".join(
            path.read_text(errors="replace")
            for path in BUNDLE.rglob("*")
            if path.is_file() and ".pyc" not in path.name
        )
        self.assertIsNone(re.search(r"rmab[_-](api|request|job)", source_text, re.I))


if __name__ == "__main__":
    unittest.main()
