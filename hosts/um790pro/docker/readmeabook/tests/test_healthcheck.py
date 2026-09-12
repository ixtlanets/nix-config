#!/usr/bin/env python3

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


BUNDLE_DIR = Path(__file__).resolve().parents[1]
HEALTHCHECK = BUNDLE_DIR / "scripts" / "healthcheck.sh"


class HealthcheckTest(unittest.TestCase):
    def test_transient_unhealthy_container_is_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_docker = root / "docker"
            attempt_file = root / "attempt"
            fake_docker.write_text(
                "#!/bin/sh\n"
                "case \"$*\" in\n"
                "  *readmeabook-transmission) printf '%s\\n' 'true|' ;;\n"
                "  *readmeabook)\n"
                "    attempt=0\n"
                "    if [ -e \"$READMABOOK_TEST_ATTEMPT_FILE\" ]; then\n"
                "      attempt=$(cat \"$READMABOOK_TEST_ATTEMPT_FILE\")\n"
                "    fi\n"
                "    attempt=$((attempt + 1))\n"
                "    printf '%s\\n' \"$attempt\" > \"$READMABOOK_TEST_ATTEMPT_FILE\"\n"
                "    if [ \"$attempt\" -lt 12 ]; then\n"
                "      printf '%s\\n' 'true|unhealthy'\n"
                "    else\n"
                "      printf '%s\\n' 'true|healthy'\n"
                "    fi\n"
                "    ;;\n"
                "  *) printf '%s\\n' 'true|healthy' ;;\n"
                "esac\n"
            )
            fake_docker.chmod(0o755)
            fake_python = root / "python"
            fake_python.write_text(
                "#!/bin/sh\n"
                "case \"$*\" in\n"
                "  *publisher.py*) printf '%s\\n' '{\"blocked\":false}' ;;\n"
                "  *torrent-policy.py*) printf '%s\\n' '{\"capacity_blocked\":false,\"active_downloads\":0}' ;;\n"
                "  *) exec python3 \"$@\" ;;\n"
                "esac\n"
            )
            fake_python.chmod(0o755)
            environment = os.environ.copy()
            environment.update(
                {
                    "READMABOOK_BUNDLE_DIR": str(BUNDLE_DIR),
                    "READMABOOK_DOCKER_BIN": str(fake_docker),
                    "READMABOOK_HEALTH_RETRY_DELAY_SECONDS": "0",
                    "READMABOOK_PUBLISHER_CONFIG": str(root / "publisher.json"),
                    "READMABOOK_PYTHON_BIN": str(fake_python),
                    "READMABOOK_TEST_ATTEMPT_FILE": str(attempt_file),
                    "READMABOOK_TORRENT_POLICY_CONFIG": str(root / "policy.json"),
                }
            )

            result = subprocess.run(
                ["bash", str(HEALTHCHECK)],
                check=False,
                capture_output=True,
                env=environment,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("health checks passed", result.stdout)

    def test_container_without_a_docker_healthcheck_is_accepted_when_running(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_docker = root / "docker"
            docker_log = root / "docker.log"
            fake_docker.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >> \"$READMABOOK_TEST_DOCKER_LOG\"\n"
                "case \"$*\" in\n"
                "  *readmeabook-transmission) printf '%s\\n' 'true|' ;;\n"
                "  *) printf '%s\\n' 'true|healthy' ;;\n"
                "esac\n"
            )
            fake_docker.chmod(0o755)
            fake_python = root / "python"
            fake_python.write_text(
                "#!/bin/sh\n"
                "case \"$*\" in\n"
                "  *publisher.py*) printf '%s\\n' '{\"blocked\":false}' ;;\n"
                "  *torrent-policy.py*) printf '%s\\n' '{\"capacity_blocked\":false,\"active_downloads\":0}' ;;\n"
                "  *) exec python3 \"$@\" ;;\n"
                "esac\n"
            )
            fake_python.chmod(0o755)
            environment = os.environ.copy()
            environment.update(
                {
                    "READMABOOK_BUNDLE_DIR": str(BUNDLE_DIR),
                    "READMABOOK_DOCKER_BIN": str(fake_docker),
                    "READMABOOK_PUBLISHER_CONFIG": str(root / "publisher.json"),
                    "READMABOOK_PYTHON_BIN": str(fake_python),
                    "READMABOOK_TEST_DOCKER_LOG": str(docker_log),
                    "READMABOOK_TORRENT_POLICY_CONFIG": str(root / "policy.json"),
                }
            )

            result = subprocess.run(
                ["bash", str(HEALTHCHECK)],
                check=False,
                capture_output=True,
                env=environment,
                text=True,
            )
            docker_commands = docker_log.read_text()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("health checks passed", result.stdout)
        self.assertIn("readmeabook-flaresolverr", docker_commands)
        self.assertIn("readmeabook-rutracker-gateway", docker_commands)


if __name__ == "__main__":
    unittest.main()
