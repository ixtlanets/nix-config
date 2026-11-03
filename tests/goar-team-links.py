#!/usr/bin/env python3
"""Offline Goar artifact contract. Diagnostics deliberately exclude credentials."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

SERVER = "148.253.210.41"
PORT = 24443
SERVICE = "RealityEZPZ"
BASELINE = json.loads(Path(__file__).with_name("goar-team-baseline.json").read_text())


class ContractError(Exception):
    """A credential-free contract diagnostic."""


def require(ok, message):
    if not ok:
        raise ContractError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate(root):
    bundle = root / "secrets/proxy/goar-team"
    profiles = root / "secrets/vless"
    config = dict(line.split("=", 1) for line in (bundle / "config").read_text().splitlines()
                  if line and not line.startswith("#") and "=" in line)
    require(config["server"] == SERVER and config["port"] == str(PORT), "node/config port")
    engine = json.loads((bundle / "engine.conf").read_text())
    inbounds = [i for i in engine["inbounds"] if i["type"] == "vless"]
    require(len(inbounds) == 1, "one VLESS inbound required")
    rows = inbounds[0]["users"]
    users = {u["name"]: u["uuid"] for u in rows}
    require(len(users) == len(rows), "duplicate engine names")
    require(len(set(users.values())) == len(users), "duplicate engine credentials")
    names = set(users) - {SERVICE}
    require(names == set(BASELINE["names"]) and SERVICE in users, "named engine inventory")
    user_lines = [line.split("=", 1) for line in (bundle / "users").read_text().splitlines() if line]
    require(len(user_lines) == len(dict(user_lines)), "duplicate helper users")
    require(dict(user_lines) == users, "helper/engine users parity")

    jsons = {}
    for path in profiles.glob("*.json"):
        data = json.loads(path.read_text())
        outbounds = [o for o in data.get("outbounds", []) if o.get("server") == SERVER]
        if not outbounds:
            continue
        require(len(outbounds) == 1 and outbounds[0]["type"] == "vless", path.name + ": duplicate/non-VLESS target")
        require(path.stem in names, path.name + ": extra JSON identity")
        jsons[path.stem] = outbounds[0]
    require({name + ".json" for name in jsons} == set(BASELINE["json_original_sha256"]), "JSON inventory missing/extra")

    links = {}
    for path in profiles.glob("*.vless.txt"):
        raw = path.read_bytes()
        url = urlsplit(raw.decode().strip())
        if url.hostname != SERVER:
            continue
        name = path.name.removesuffix(".vless.txt")
        require(name in names, path.name + ": extra/service link")
        require(unquote(url.fragment) == name, path.name + ": label mismatch/duplicate")
        require(url.scheme == "vless" and url.username == users[name], name + ": authority mismatch")
        require(url.port == PORT and url.password is None, name + ": link endpoint")
        query = parse_qs(url.query, keep_blank_values=True)
        expected = {"security": ["reality"], "encryption": ["none"], "type": ["tcp"],
                    "headerType": ["none"], "sni": [config["domain"].split(":", 1)[0]],
                    "pbk": [config["public_key"]], "sid": [config["short_id"]],
                    "flow": ["xtls-rprx-vision"], "alpn": ["h2,http/1.1"]}
        require(set(query) == set(expected) | {"fp"}, name + ": query inventory")
        require(all(query.get(k) == v for k, v in expected.items()), name + ": link TLS/flow parameters")
        require(len(query["fp"]) == 1 and query["fp"][0] in {"chrome", "firefox"}, name + ": fingerprint")
        if name in jsons:
            o = jsons[name]
            tls = o["tls"]
            require(o["server_port"] == PORT and o["uuid"] == users[name], name + ": JSON authority/port")
            require(tls["enabled"] and tls["reality"]["enabled"] and tls["utls"]["enabled"], name + ": JSON TLS disabled")
            parity = {"sni": tls["server_name"], "pbk": tls["reality"]["public_key"],
                      "sid": tls["reality"]["short_id"], "flow": o["flow"],
                      "alpn": ",".join(tls["alpn"]), "fp": tls["utls"]["fingerprint"]}
            require(all(query.get(k) == [v] for k, v in parity.items()), name + ": JSON/link parity")
        qr = profiles / (name + ".qr.png")
        require(qr.is_file(), name + ": missing QR")
        result = subprocess.run(["zbarimg", "--raw", "--quiet", str(qr)], capture_output=True)
        require(result.returncode == 0 and result.stdout == raw.rstrip(b"\n") + b"\n", name + ": QR byte roundtrip")
        original = BASELINE["link_original_sha256"].get(path.name)
        if original:
            require(digest(raw.replace(b":24443?", b":443?")) == original, name + ": link changed beyond port")
        links[name] = url.username
    require(set(links) == names, "link inventory missing/extra")
    require(len(set(links.values())) == len(names), "duplicate link credentials")
    for name in names:
        require((profiles / (name + ".qr.png")).is_file(), name + ": missing QR")
    # Orphan QRs cannot identify their server from a filename: decode and discover dynamically.
    for path in profiles.glob("*.qr.png"):
        if path.name.removesuffix(".qr.png") in names:
            continue
        result = subprocess.run(["zbarimg", "--raw", "--quiet", str(path)], capture_output=True)
        require(result.returncode == 0, path.name + ": undecodable orphan QR")
        if urlsplit(result.stdout.decode().strip()).hostname == SERVER:
            raise ContractError(path.name + ": extra/service QR")
    for filename, expected in BASELINE["json_original_sha256"].items():
        raw = (profiles / filename).read_bytes()
        require(digest(raw.replace(b'"server_port": 24443', b'"server_port": 443')) == expected,
                filename + ": JSON changed beyond port")
    for filename, expected in BASELINE["bundle_original_sha256"].items():
        raw = (bundle / filename).read_bytes()
        if filename == "config":
            raw = raw.replace(b"\nport=24443\n", b"\nport=443\n")
        elif filename == "docker-compose.yml":
            require(raw.count(b'    - "24443:8443"\n') == 1, "quoted alternate mapping")
            require(raw.count(b"    - 443:8443\n") == 1, "retained 443 mapping")
            raw = raw.replace(b'    - "24443:8443"\n', b"")
        require(digest(raw) == expected, filename + ": original server identity/config changed")
    return len(names), len(jsons), len(links)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        counts = validate(args.root)
    except Exception as error:
        # Parser/subprocess exceptions can embed input; print only our credential-free diagnostics.
        print("FAIL: " + (str(error) if isinstance(error, ContractError) else type(error).__name__))
        raise SystemExit(1)
    print("PASS: %d named identities, %d JSON profiles, %d links and 13 QR byte roundtrips; baseline preserved" % counts)
