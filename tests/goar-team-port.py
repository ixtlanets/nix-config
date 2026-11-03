#!/usr/bin/env python3
"""Offline alternate-port contract; no Docker daemon or network access."""

from pathlib import Path

root = Path(__file__).resolve().parents[1]
compose = (root / "secrets/proxy/goar-team/docker-compose.yml").read_text()
config = (root / "secrets/proxy/goar-team/config").read_text().splitlines()
assert compose.count('    - "24443:8443"') == 1, "missing quoted alternate mapping"
assert compose.count("    - 443:8443") == 1, "old mapping must remain"
assert config.count("port=24443") == 1, "helper links must use alternate port"
print("PASS: additive port mapping and helper port")
