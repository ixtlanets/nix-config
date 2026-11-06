"""Run on zenbook. Secrets are read from pass and never printed."""
import argparse
import hashlib
import http.client
import ipaddress
import json
import os
import pathlib
import secrets
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.request

ACCOUNT = "f0c7f9cf224597d95a2989164bfce907"
ZONE = "815edebe16f70d535787e951ac38d7eb"
WORKER = "nikcode-subscriptions"
HOST = "config.nikcode.xyz"
STATE_ENTRY = "nikcode.xyz/config/service-state"
ROOT = pathlib.Path(__file__).resolve().parents[1]
FORMATS = ["sing-box", "sing-box-macos", "sing-box-linux", "sing-box-android", "sing-box-ios", "sing-box-ios-legacy", "outbounds", "throne", "hiddify", "incy", "happ"]
PRESETS = {"linux": "sing-box", "macos": "sing-box", "windows": "throne", "ios": "incy", "android": "hiddify"}


def read_pass(entry):
    r = subprocess.run(["pass", "show", entry], capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise RuntimeError("Cannot read required pass entry: " + entry)
    return r.stdout


def write_pass(entry, value):
    r = subprocess.run(["pass", "insert", "-f", "-m", entry], input=value + "\n", capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise RuntimeError("Cannot save pass entry: " + entry)


def api(path, method="GET", data=None, raw=None, content_type=None):
    token = read_pass("api/cloudflare.com/snikulin@gmail.com/full").splitlines()[0].strip()
    headers = {"Authorization": "Bearer " + token}
    if data is not None:
        raw, content_type = json.dumps(data).encode(), "application/json"
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request("https://api.cloudflare.com/client/v4/" + path, headers=headers, data=raw, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        try:
            codes = [e.get("code") for e in json.loads(error.read()).get("errors", [])]
        except Exception:
            codes = []
        raise RuntimeError(f"Cloudflare {method} {path}: HTTP {error.code}, error codes {codes}") from None
    if not result.get("success"):
        raise RuntimeError("Cloudflare API failed: " + path)
    return result.get("result")


def load_state():
    return json.loads(read_pass(STATE_ENTRY))


def bootstrap():
    store = pathlib.Path.home() / ".password-store" / (STATE_ENTRY + ".gpg")
    if store.exists():
        print("Existing encrypted subscription state retained")
        return load_state()
    base = pathlib.Path.home() / ".local/state/warsaw-pilot-20261101"
    naive = json.loads((base / "naive/access.json").read_text())
    config = json.loads((base / "client-443.json").read_text())
    vless = next(x for x in config["outbounds"] if x["type"] == "vless")
    state = {
        "schema": 1,
        "entry": {
            "host": "notes.nikcode.xyz", "port": 443,
            "naive": {"username": naive["username"], "password": naive["password"]},
            "vless": {"uuid": vless["uuid"], "server_name": vless["tls"]["server_name"],
                      "public_key": vless["tls"]["reality"]["public_key"], "short_id": vless["tls"]["reality"]["short_id"]},
        },
        "subscriptions": [],
    }
    for label, fmt in PRESETS.items():
        token = secrets.token_urlsafe(32)
        state["subscriptions"].append({"label": label, "token": token, "hash": hashlib.sha256(token.encode()).hexdigest(), "format": fmt, "formats": FORMATS, "enabled": True})
        write_pass("nikcode.xyz/config/" + label, f"https://{HOST}/s/{token}\nclient: {label}\nformat: {fmt}\n")
    write_pass(STATE_ENTRY, json.dumps(state))
    print("Five subscription links and service state saved encrypted in pass")
    return state


def worker_state(state):
    # Labels are operator metadata and are never used by the Worker.  Leaving
    # them out keeps the encrypted binding below Cloudflare's per-secret size
    # limit without changing subscription tokens or rendered profiles.
    private_keys = {"token", "label"}
    return {
        **state,
        "subscriptions": [
            {k: v for k, v in subscription.items() if k not in private_keys}
            for subscription in state["subscriptions"]
        ],
    }


def verify_identity():
    account = api("accounts/" + ACCOUNT)
    zone = api("zones/" + ZONE)
    if account["id"] != ACCOUNT or zone["name"] != "nikcode.xyz" or zone["account"]["id"] != ACCOUNT:
        raise RuntimeError("Cloudflare account/zone mismatch")


def ensure_client_rule():
    phase = "http_config_settings"
    rulesets = api("zones/" + ZONE + "/rulesets")
    existing = next((r for r in rulesets if r["phase"] == phase and r["kind"] == "zone"), None)
    rule = {"ref": "nikcode_subscription_clients", "description": "Allow non-browser subscription clients on config hostname", "expression": '(http.host eq "config.nikcode.xyz")', "action": "set_config", "action_parameters": {"bic": False}, "enabled": True}
    if existing:
        ruleset = api("zones/" + ZONE + "/rulesets/" + existing["id"])
        old = next((r for r in ruleset.get("rules", []) if r.get("ref") == rule["ref"]), None)
        if not old:
            api("zones/" + ZONE + "/rulesets/" + existing["id"] + "/rules", "POST", data=rule)
        elif old.get("expression") != rule["expression"] or old.get("action_parameters", {}).get("bic") is not False:
            raise RuntimeError("Existing subscription configuration rule differs; review before changing")
    else:
        api("zones/" + ZONE + "/rulesets", "POST", data={"name": "Configuration settings", "kind": "zone", "phase": phase, "rules": [rule]})
    print("Non-browser clients permitted on config hostname only")


def deploy(state, code_only=False):
    verify_identity()
    domains = api("accounts/" + ACCOUNT + "/workers/domains")
    existing = [d for d in domains if d["hostname"] == HOST]
    records = api("zones/" + ZONE + "/dns_records?name=" + HOST)
    if existing and any(d["service"] != WORKER for d in existing):
        raise RuntimeError("Custom domain belongs to another Worker")
    if records and not existing:
        raise RuntimeError("DNS hostname already exists; refusing to overwrite")
    boundary = "nikcode" + secrets.token_hex(16)
    metadata = {"main_module": "worker.js", "compatibility_date": "2026-11-01", "keep_bindings": ["secret_text"], "observability": {"enabled": False}, "logpush": False}
    parts = []
    for name, filename, kind, body in [
        ("metadata", None, "application/json", json.dumps(metadata).encode()),
        ("worker.js", "worker.js", "application/javascript+module", (ROOT / "src/worker.js").read_bytes()),
    ]:
        disposition = f'Content-Disposition: form-data; name="{name}"'
        if filename:
            disposition += f'; filename="{filename}"'
        parts.append((f"--{boundary}\r\n{disposition}\r\nContent-Type: {kind}\r\n\r\n").encode() + body + b"\r\n")
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    result = api("accounts/" + ACCOUNT + "/workers/scripts/" + WORKER, "PUT", raw=body, content_type="multipart/form-data; boundary=" + boundary)
    if code_only:
        print(json.dumps({"worker": result.get("id"), "action": "code updated; existing secret bindings retained"}))
        return
    api("accounts/" + ACCOUNT + "/workers/scripts/" + WORKER + "/secrets", "PUT", data={"name": "SERVICE_CONFIG", "type": "secret_text", "text": json.dumps(worker_state(state))})
    domain = api("accounts/" + ACCOUNT + "/workers/domains", "PUT", data={"hostname": HOST, "service": WORKER, "enabled": True, "zone_id": ZONE, "zone_name": "nikcode.xyz"})
    api("accounts/" + ACCOUNT + "/workers/scripts/" + WORKER + "/subdomain", "POST", data={"enabled": False, "previews_enabled": False})
    ensure_client_rule()
    print(json.dumps({"worker": result.get("id"), "domain": domain.get("hostname"), "domain_id": domain.get("id"), "secrets": "encrypted binding", "workers_dev": False}))
    notes = api("zones/" + ZONE + "/dns_records?name=notes.nikcode.xyz")
    records = [x for x in notes if x["type"] == "A"]
    if len(records) != 1 or records[0].get("proxied") or not ipaddress.IPv4Address(records[0]["content"]).is_global:
        raise RuntimeError("Unexpected entry DNS; did not alter it")
    api("zones/" + ZONE + "/dns_records/" + records[0]["id"], "PATCH", data={"ttl": 60})
    print("Entry hostname retained; DNS-only TTL set to 60; IP unchanged")


class DirectHTTPS(http.client.HTTPSConnection):
    def connect(self):
        addresses = socket.getaddrinfo(self.host, self.port, socket.AF_INET, socket.SOCK_STREAM)
        failure = None
        for _, _, _, _, address in addresses:
            raw = socket.socket()
            raw.settimeout(self.timeout)
            raw.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, b"wlo1\0")
            try:
                raw.connect(address)
                self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
                return
            except OSError as error:
                raw.close()
                failure = error
        raise failure or OSError("No addresses")


def fetch(path, direct=False):
    if direct:
        connection = DirectHTTPS(HOST, timeout=15, context=ssl.create_default_context())
        connection.request("GET", path)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result
    request = urllib.request.Request("https://" + HOST + path)
    try:
        response = urllib.request.urlopen(request, timeout=20)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, dict(response.headers), response.read()


def verify(state, direct=False):
    for path, expected in [("/", 200), ("/healthz", 200), ("/s/" + "x" * 43, 404)]:
        status, _, _ = fetch(path, direct)
        assert status == expected, ("Public endpoint", status, expected)
    for record in state["subscriptions"]:
        status, headers, body = fetch("/s/" + record["token"], direct)
        expected = 200 if record["enabled"] else 404
        assert status == expected, (record["label"], status, expected)
        if expected == 200:
            assert "no-store" in next(v for k, v in headers.items() if k.lower() == "cache-control")
            assert b"notes.nikcode.xyz" in body
            assert b"148.253.212.96" not in body
            if record["format"] in ("sing-box", "sing-box-macos", "sing-box-linux", "sing-box-ios-legacy", "hiddify"):
                json.loads(body)
            if record["format"] in ("incy", "happ"):
                assert body.startswith(b"vless://") and b"naive" not in body
        print(json.dumps({"subscription": record["label"], "format": record["format"], "status": status, "direct_wlo1": direct}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["bootstrap", "deploy", "publish", "verify", "export", "revoke"])
    parser.add_argument("--direct", action="store_true")
    parser.add_argument("--label")
    args = parser.parse_args()
    if args.action == "bootstrap":
        bootstrap()
        return
    state = load_state()
    if args.label and not any(s["label"] == args.label for s in state["subscriptions"]):
        parser.error("Unknown subscription label")
    if args.action == "deploy":
        deploy(state)
    elif args.action == "publish":
        deploy(state, code_only=True)
    elif args.action == "verify":
        if args.direct and os.geteuid() != 0:
            code = "import sys,json;sys.path.insert(0," + repr(str(ROOT / "scripts")) + ");from manage import verify;verify(json.load(sys.stdin),True)"
            subprocess.run(["sudo", "-n", sys.executable, "-c", code], input=json.dumps(state), text=True, check=True)
        else:
            verify(state, args.direct)
    elif args.action == "export":
        if not args.label:
            parser.error("export requires --label")
        record = next(s for s in state["subscriptions"] if s["label"] == args.label)
        if not record["enabled"]:
            raise RuntimeError("Subscription is disabled")
        status, _, body = fetch("/s/" + record["token"])
        if status != 200:
            raise RuntimeError("Cannot download subscription")
        folder = pathlib.Path.home() / ".local/state/nikcode-network/profiles"
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        extension = ".json" if record["format"] in ["sing-box", "sing-box-macos", "sing-box-linux", "sing-box-android", "sing-box-ios", "sing-box-ios-legacy", "hiddify"] else ".txt"
        output = folder / (args.label + extension)
        output.write_bytes(body)
        output.chmod(0o600)
        print("Downloaded to staging only: " + str(output))
    elif args.action == "revoke":
        if not args.label:
            parser.error("revoke requires --label")
        for record in state["subscriptions"]:
            if record["label"] == args.label:
                record["enabled"] = False
        write_pass(STATE_ENTRY, json.dumps(state))
        api("accounts/" + ACCOUNT + "/workers/scripts/" + WORKER + "/secrets", "PUT", data={"name": "SERVICE_CONFIG", "type": "secret_text", "text": json.dumps(worker_state(state))})
        print("Subscription fetch access revoked; previously downloaded VPN credentials are unchanged")


if __name__ == "__main__":
    main()
