#!/usr/bin/env python3
"""Validate owner and Goar team VLESS links and QR files against the DR bundle."""

import json
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

root = Path(__file__).resolve().parents[1]
bundle = root / "secrets/proxy/goar-team"
profiles = root / "secrets/vless"
people = (
    "nik-ios",
    "nik-android",
    "goar-ios",
    "goar-mother-ios",
    "goar-nanny-android",
    "goar-driver-android",
    "goar-housekeeper-android",
)

config = dict(
    line.split("=", 1)
    for line in (bundle / "config").read_text().splitlines()
    if line and not line.startswith("#") and "=" in line
)
engine = json.loads((bundle / "engine.conf").read_text())
users = {user["name"]: user["uuid"] for user in engine["inbounds"][1]["users"]}
assert len(users) == len(engine["inbounds"][1]["users"])
assert len(set(users.values())) == len(users)

for name in people:
    link = (profiles / f"{name}.vless.txt").read_text().strip()
    url = urlparse(link)
    query = parse_qs(url.query)
    assert url.scheme == "vless" and url.username == users[name], name
    assert url.hostname == config["server"] and url.port == int(config["port"]), name
    assert unquote(url.fragment) == name, name
    assert query["security"] == ["reality"] and query["encryption"] == ["none"], name
    assert query["sni"] == [config["domain"].split(":", 1)[0]], name
    assert query["pbk"] == [config["public_key"]], name
    assert query["sid"] == [config["short_id"]], name
    assert query["flow"] == ["xtls-rprx-vision"], name
    decoded = subprocess.run(
        ["zbarimg", "--raw", "--quiet", str(profiles / f"{name}.qr.png")],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert decoded == link, name

print("PASS: two owner and five team links and QR codes match distinct server users")
