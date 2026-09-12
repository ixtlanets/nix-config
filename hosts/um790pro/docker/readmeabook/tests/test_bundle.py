#!/usr/bin/env python3

import os
import json
import subprocess
import unittest
from pathlib import Path


BUNDLE_DIR = Path(__file__).resolve().parents[1]


class ComposeBundleTest(unittest.TestCase):
    def test_compose_is_pinned_and_only_exposes_private_operator_ports(self) -> None:
        environment = os.environ.copy()
        environment.update(
            {
                "READMABOOK_SECRETS_ROOT": "/run/readmeabook-test-secrets",
                "READMABOOK_STATE_ROOT": "/srv/readmeabook-test",
            }
        )
        result = subprocess.run(
            ["docker", "compose", "-f", str(BUNDLE_DIR / "docker-compose.yml"), "config"],
            check=False,
            capture_output=True,
            env=environment,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        rendered = result.stdout
        self.assertIn(
            "localhost/readmeabook:1.2.2-transmission-tracker-fix-1",
            rendered,
        )
        readmeabook_dockerfile = (BUNDLE_DIR / "Dockerfile.readmeabook").read_text()
        self.assertIn(
            "ghcr.io/kikootwo/readmeabook@sha256:91fb3ee1943678003cd9c86990430c6268428f52c6ea3fb8a57e179f84855d45",
            readmeabook_dockerfile,
        )
        self.assertIn("patch-readmeabook-transmission.js", readmeabook_dockerfile)
        self.assertIn(
            "lscr.io/linuxserver/prowlarr@sha256:c7502a75b021d964481c129c84590b9cbc40f83aadd4e553f173871bc0deaa3c",
            rendered,
        )
        self.assertIn(
            "lscr.io/linuxserver/transmission@sha256:fc3b07f2f571c0392edd4dd386067138a0fe157d2158a976769409a292e43936",
            rendered,
        )
        self.assertIn(
            "ghcr.io/flaresolverr/flaresolverr@sha256:258523d25e4e07028c3a206f0e03ae807b26a50a201dd320f09a18464ecf86fa",
            rendered,
        )
        self.assertIn("host_ip: 100.95.213.117", rendered)
        self.assertIn('published: "3030"', rendered)
        self.assertIn("host_ip: 127.0.0.1", rendered)
        self.assertIn('published: "9696"', rendered)
        self.assertNotIn('published: "9091"', rendered)
        self.assertNotIn('published: "51413"', rendered)
        self.assertNotIn('published: "8191"', rendered)
        self.assertIn("source: /srv/readmeabook-test/downloads", rendered)
        self.assertIn("target: /downloads", rendered)
        self.assertIn("source: /srv/readmeabook-test/staging", rendered)
        self.assertIn("target: /media", rendered)
        self.assertIn("target: rmab-jwt-secret", rendered)
        self.assertIn("target: rmab-postgres-password", rendered)
        self.assertIn("- /readmeabook/container-entrypoint.sh", rendered)
        self.assertNotIn("latest", rendered)

        rendered_json = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(BUNDLE_DIR / "docker-compose.yml"),
                "config",
                "--format",
                "json",
            ],
            check=False,
            capture_output=True,
            env=environment,
            text=True,
        )
        self.assertEqual(rendered_json.returncode, 0, rendered_json.stderr)
        compose = json.loads(rendered_json.stdout)
        self.assertEqual(
            compose["services"]["readmeabook"]["build"]["dockerfile"],
            "Dockerfile.readmeabook",
        )
        self.assertEqual(
            compose["services"]["readmeabook"]["command"],
            ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"],
        )
        self.assertEqual(compose["services"]["flaresolverr"]["networks"], {"backend": None})
        self.assertNotIn("ports", compose["services"]["flaresolverr"])
        self.assertEqual(
            compose["services"]["flaresolverr"]["environment"]["LOG_LEVEL"],
            "warning",
        )
        gateway = compose["services"]["rutracker-gateway"]
        self.assertEqual(gateway["networks"], {"backend": None})
        self.assertNotIn("ports", gateway)
        self.assertTrue(gateway["read_only"])
        self.assertEqual(gateway["cap_drop"], ["ALL"])
        self.assertIn("no-new-privileges:true", gateway["security_opt"])
        self.assertIn("/gateway/rutracker_gateway.py", gateway["command"])
        transmission = compose["services"]["transmission"]
        self.assertEqual(
            transmission["entrypoint"],
            ["/readmeabook/transmission-entrypoint.sh"],
        )
        self.assertNotIn("FILE__PASS", transmission["environment"])
        self.assertTrue(
            any(
                mount["target"] == "/readmeabook/transmission-entrypoint.sh"
                and mount["read_only"]
                for mount in transmission["volumes"]
            )
        )

    def test_default_secret_source_survives_host_reboots(self) -> None:
        result = subprocess.run(
            ["docker", "compose", "-f", str(BUNDLE_DIR / "docker-compose.yml"), "config"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("file: /etc/readmeabook/secrets/rmab-jwt-secret", result.stdout)
        self.assertNotIn("file: /run/secrets/readmeabook", result.stdout)

    def test_publisher_example_encodes_the_approved_safety_limits(self) -> None:
        config = json.loads((BUNDLE_DIR / "publisher.example.json").read_text())

        self.assertEqual(config["rmab_url"], "http://100.95.213.117:3030")
        self.assertEqual(config["rmab_media_root"], "/media")
        self.assertEqual(config["abs_url"], "http://100.81.67.47:13378")
        self.assertEqual(config["remote_host"], "nik@100.81.67.47")
        self.assertEqual(config["known_hosts_file"], "/home/nik/.ssh/known_hosts")
        self.assertEqual(config["max_release_gib"], 20)
        self.assertEqual(config["min_local_free_gib"], 100)
        self.assertEqual(config["min_remote_free_gib"], 200)
        self.assertEqual(config["stability_seconds"], 30)
        self.assertEqual(config["staging_retention_hours"], 24)
        self.assertEqual(config["allowed_extensions"], [".m4b", ".m4a", ".mp3", ".flac"])
        self.assertEqual(config["rmab_token_file"], "${CREDENTIALS_DIRECTORY}/rmab-api-token")
        self.assertEqual(config["abs_token_file"], "${CREDENTIALS_DIRECTORY}/abs-api-token")
        self.assertFalse(
            [key for key in config if ("token" in key or "password" in key) and not key.endswith("_file")]
        )

    def test_manual_request_example_uses_only_credential_files(self) -> None:
        config = json.loads((BUNDLE_DIR / "manual-request.example.json").read_text())

        self.assertEqual(config["rmab_url"], "http://100.95.213.117:3030")
        self.assertEqual(
            config["requester_password_file"],
            "${READMABOOK_REQUESTER_PASSWORD_FILE}",
        )
        self.assertEqual(config["requester_username"], "nik-requester")
        self.assertEqual(
            config["admin_password_file"],
            "${READMABOOK_ADMIN_PASSWORD_FILE}",
        )
        self.assertEqual(config["admin_username"], "nik")
        self.assertFalse(
            [
                key
                for key in config
                if ("token" in key or "password" in key)
                and not key.endswith("_file")
            ]
        )

    def test_systemd_templates_call_guarded_public_interfaces(self) -> None:
        systemd_dir = BUNDLE_DIR / "systemd"
        publisher_service = (systemd_dir / "readmeabook-publisher.service").read_text()
        unpublish_service = (systemd_dir / "readmeabook-unpublish@.service").read_text()
        publisher_timer = (systemd_dir / "readmeabook-publisher.timer").read_text()
        cleanup_service = (systemd_dir / "readmeabook-cleanup.service").read_text()
        backup_service = (systemd_dir / "readmeabook-backup.service").read_text()
        policy_service = (systemd_dir / "readmeabook-torrent-policy.service").read_text()
        policy_timer = (systemd_dir / "readmeabook-torrent-policy.timer").read_text()
        health_service = (systemd_dir / "readmeabook-healthcheck.service").read_text()

        self.assertIn("User=nik", publisher_service)
        self.assertIn("LoadCredential=rmab-api-token:", publisher_service)
        self.assertIn("LoadCredential=abs-api-token:", publisher_service)
        self.assertIn("LoadCredential=publisher-ssh-key:", publisher_service)
        self.assertIn("publisher.py", publisher_service)
        self.assertIn("run-once --execute", publisher_service)
        self.assertIn("User=nik", unpublish_service)
        self.assertIn("LoadCredential=publisher-ssh-key:", unpublish_service)
        self.assertIn("unpublish %i --execute", unpublish_service)
        self.assertIn("OnUnitActiveSec=5min", publisher_timer)
        self.assertIn("publisher.py", cleanup_service)
        self.assertIn("cleanup --execute", cleanup_service)
        self.assertIn("backup.sh --execute", backup_service)
        self.assertIn("User=root", backup_service)
        self.assertIn("torrent-policy.py", policy_service)
        self.assertIn("run --execute", policy_service)
        self.assertIn("OnUnitActiveSec=5min", policy_timer)
        self.assertIn("healthcheck.sh", health_service)
        self.assertNotIn("WantedBy=multi-user.target", publisher_service)
        for serialized_service in (
            publisher_service,
            backup_service,
            policy_service,
            health_service,
        ):
            self.assertIn("/etc/readmeabook/secrets/", serialized_service)
            self.assertNotIn("/run/secrets/readmeabook/", serialized_service)
        for serialized_service in (
            publisher_service,
            cleanup_service,
            policy_service,
            backup_service,
        ):
            self.assertIn("/usr/bin/flock", serialized_service)
            self.assertIn("--timeout 1800", serialized_service)
            self.assertNotIn("--nonblock", serialized_service)
            self.assertIn("/home/nik/.local/state/readmeabook-publisher", serialized_service)
        for unit in systemd_dir.iterdir():
            if unit.suffix == ".service":
                self.assertNotIn("/run/current-system/sw/bin", unit.read_text(), unit.name)

    def test_cachyos_runbook_installs_operator_runtime_dependencies(self) -> None:
        runbook = (BUNDLE_DIR / "README.md").read_text()

        self.assertIn("CachyOS", runbook)
        self.assertIn("sudo pacman -S --needed", runbook)
        for package in (
            "curl",
            "docker",
            "docker-compose",
            "ffmpeg",
            "openssh",
            "python",
            "rsync",
            "util-linux",
        ):
            self.assertIn(package, runbook)
        self.assertNotIn("nixos-rebuild", runbook)

    def test_cachyos_examples_use_standard_arch_runtime_paths(self) -> None:
        publisher_config = json.loads(
            (BUNDLE_DIR / "publisher.example.json").read_text()
        )
        policy_config = json.loads(
            (BUNDLE_DIR / "torrent-policy.example.json").read_text()
        )
        healthcheck = (BUNDLE_DIR / "scripts/healthcheck.sh").read_text()

        self.assertEqual(publisher_config["ffprobe_bin"], "/usr/bin/ffprobe")
        self.assertEqual(publisher_config["rsync_bin"], "/usr/bin/rsync")
        self.assertEqual(publisher_config["ssh_bin"], "/usr/bin/ssh")
        self.assertEqual(policy_config["docker_bin"], "/usr/bin/docker")
        self.assertIn("/usr/bin/python3", healthcheck)
        self.assertIn("/usr/bin/docker", healthcheck)
        self.assertNotIn("/run/current-system/sw/bin", healthcheck)

    def test_declared_secret_source_is_covered_by_git_crypt(self) -> None:
        attributes = (BUNDLE_DIR.parents[3] / ".gitattributes").read_text()

        self.assertIn(
            "secrets/readmeabook/** filter=git-crypt diff=git-crypt", attributes
        )

    def test_moscow_override_adds_only_the_new_read_only_sibling_tree(self) -> None:
        moscow_bundle = BUNDLE_DIR.parents[2] / "moscow/ubuntu/audiobookshelf"
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(moscow_bundle / "docker-compose.yml"),
                "-f",
                str(BUNDLE_DIR / "moscow/audiobookshelf-readmeabook.override.yml"),
                "config",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("source: /media/disk1/media/Audiobooks", result.stdout)
        self.assertIn("target: /audiobooks", result.stdout)
        self.assertIn("source: /media/disk1/media/ReadMeABook", result.stdout)
        self.assertIn("target: /readmeabook", result.stdout)
        self.assertIn("read_only: true", result.stdout)

    def test_torrent_policy_example_encodes_capacity_and_seeding_contract(self) -> None:
        config = json.loads((BUNDLE_DIR / "torrent-policy.example.json").read_text())

        self.assertEqual(config["max_working_set_gib"], 50)
        self.assertEqual(config["min_local_free_gib"], 100)
        self.assertEqual(config["seed_ratio"], 1.0)
        self.assertEqual(config["seed_max_days"], 7)
        self.assertEqual(
            config["transmission_password_file"],
            "${CREDENTIALS_DIRECTORY}/transmission-password",
        )


if __name__ == "__main__":
    unittest.main()
