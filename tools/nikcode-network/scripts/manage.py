"""Run on zenbook. Secrets are read from pass and never printed."""
import argparse
import hashlib
import http.client
import ipaddress
import json
import os
import pathlib
import re
import secrets
import socket
import ssl
import subprocess
import sys
import uuid
import urllib.error
import urllib.request

ACCOUNT = "f0c7f9cf224597d95a2989164bfce907"
ZONE = "815edebe16f70d535787e951ac38d7eb"
WORKER = "nikcode-subscriptions"
HOST = "config.nikcode.xyz"
STATE_ENTRY = "nikcode.xyz/config/service-state"
PILOT_STATE_ENTRY = "nikcode.xyz/config/pilot-state"
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


def pilot_projection(state):
    """Only renderer inputs enter the separate PILOT_CONFIG secret binding."""
    result = {key: state[key] for key in ("schema", "magic_dns_suffix", "ru_domains", "ru_rules", "subscription_hosts", "rules_url") if key in state}
    result["nodes"] = [
        {key: node[key] for key in ("id", "enabled", "protocol", "host", "port", "server_name", "public_key", "short_id")}
        for node in state["nodes"]
    ]
    result["devices"] = [
        {**{key: device[key] for key in ("id", "hash", "enabled", "tailscale", "credentials")},
         **({"rule_set_mode": device["rule_set_mode"]} if "rule_set_mode" in device else {})}
        for device in state["devices"]
    ]
    return result


def validate_pilot(state, private=True):
    projection = pilot_projection(state)
    raw = json.dumps(projection, separators=(",", ":"))
    if len(raw.encode()) > 5000:
        raise ValueError("PILOT_CONFIG exceeds the 5000-byte budget; do not deploy")
    script = "import {validPilot} from './src/worker.js';let s='';for await(const c of process.stdin)s+=c;process.exit(validPilot(JSON.parse(s))?0:1);"
    check = subprocess.run(["node", "--input-type=module", "-e", script], input=raw,
                           cwd=ROOT, text=True, capture_output=True, timeout=15)
    if check.returncode:
        raise ValueError("Invalid pilot renderer configuration")
    if private:
        tokens = []
        for device in state["devices"]:
            token = device.get("token", "")
            if not re.fullmatch(r"p_[A-Za-z0-9_-]{43}", token):
                raise ValueError("Invalid pilot fetch token")
            if hashlib.sha256(token.encode()).hexdigest() != device["hash"]:
                raise ValueError("Pilot token/hash mismatch")
            tokens.append(token)
        if len(set(tokens)) != len(tokens):
            raise ValueError("Duplicate pilot token")
    return projection


def new_pilot(spec):
    """Generate locally; server installation and Worker deployment are separate."""
    allowed_node_keys = ("id", "enabled", "protocol", "host", "port", "server_name", "public_key", "short_id")
    state = {"schema": 1, "nodes": [{key: node[key] for key in allowed_node_keys} for node in spec["nodes"]],
             "magic_dns_suffix": spec["magic_dns_suffix"], "devices": []}
    for key in ("ru_domains", "ru_rules", "subscription_hosts", "rules_url"):
        if key in spec:
            state[key] = spec[key]
    for device_id in ("nik-iphone-primary", "nik-iphone-spare"):
        token = "p_" + secrets.token_urlsafe(32)
        state["devices"].append({
            "id": device_id, "token": token, "hash": hashlib.sha256(token.encode()).hexdigest(),
            "enabled": True, "tailscale": True,
            "credentials": {node["id"]: {"uuid": str(uuid.uuid4())} for node in state["nodes"]},
            "server_revocation": {node["id"]: "not-requested" for node in state["nodes"]},
        })
    validate_pilot(state)
    return state


def revoke_pilot(state, device_id):
    device = next((d for d in state["devices"] if d["id"] == device_id), None)
    if device is None:
        raise ValueError("Unknown pilot device")
    device["enabled"] = False
    # Fetch revocation is effective only after publishing the projected binding.
    # Existing clients retain credentials until every server removes its user.
    device["server_revocation"] = {node["id"]: "pending-removal" for node in state["nodes"]}
    validate_pilot(state)
    return state


def write_private_output(path, value):
    output = pathlib.Path(path).expanduser().resolve()
    git_root = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=ROOT, capture_output=True, text=True)
    protected = [ROOT.resolve(), (pathlib.Path.home() / "nix-config").resolve()]
    if git_root.returncode == 0:
        protected.append(pathlib.Path(git_root.stdout.strip()).resolve())
    if any(output == repo or repo in output.parents for repo in protected):
        raise ValueError("Private pilot output must stay outside the Git repository")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(value)


def pilot_action(args):
    if not args.input:
        raise ValueError("Pilot actions require --input pointing to private JSON")
    state = json.loads(pathlib.Path(args.input).expanduser().read_text())
    if args.action == "pilot-init":
        result = new_pilot(state)
    else:
        validate_pilot(state)
        if args.action == "pilot-validate":
            print("Pilot validated; no network or encrypted state changed")
            return
        if args.action == "pilot-project":
            result = pilot_projection(state)
        elif args.action == "pilot-revoke":
            if not args.label:
                raise ValueError("pilot-revoke requires --label device-id")
            result = revoke_pilot(state, args.label)
        elif args.action == "pilot-users":
            if not args.node or args.node not in {node["id"] for node in state["nodes"]}:
                raise ValueError("pilot-users requires a configured --node")
            result = [{"name": d["id"], "uuid": d["credentials"][args.node]["uuid"], "flow": "xtls-rprx-vision"}
                      for d in state["devices"] if d["enabled"]]
        elif args.action == "pilot-export":
            device = next((d for d in state["devices"] if d["id"] == args.label and d["enabled"]), None)
            if device is None:
                raise ValueError("pilot-export requires an enabled --label device-id")
            if args.node:
                if not any(n["id"] == args.node and n["enabled"] for n in state["nodes"]):
                    raise ValueError("Unknown or disabled fallback --node")
                for node in state["nodes"]:
                    node["enabled"] = node["id"] == args.node
            script = ("import {singBoxPilot} from './src/worker.js';let s='';for await(const c of process.stdin)s+=c;"
                      "const p=JSON.parse(s);process.stdout.write(JSON.stringify(singBoxPilot(p.config,p.device),null,2)+'\\n');")
            rendered = subprocess.run(["node", "--input-type=module", "-e", script],
                                      input=json.dumps({"config": pilot_projection(state), "device": {**device, "rule_set_mode": "inline"}}),
                                      cwd=ROOT, text=True, capture_output=True, timeout=15, check=True)
            if not args.output:
                raise ValueError("pilot-export requires --output outside the repository")
            write_private_output(args.output, rendered.stdout)
            print("Private Local profile exported; no server or Worker was changed")
            return
        else:
            raise ValueError("Unknown pilot action")
    if not args.output:
        raise ValueError("Pilot output requires --output outside the repository")
    serialized = json.dumps(result, separators=(",", ":")) if args.action == "pilot-project" else json.dumps(result, indent=2)
    write_private_output(args.output, serialized + "\n")
    print("Private pilot output prepared; no server or Worker was changed")


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
        ("geoip-ru.js", "geoip-ru.js", "application/javascript+module", (ROOT / "src/geoip-ru.js").read_bytes()),
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
    parser.add_argument("action", choices=["bootstrap", "deploy", "publish", "verify", "export", "revoke",
                        "pilot-init", "pilot-validate", "pilot-project", "pilot-revoke", "pilot-users", "pilot-export"])
    parser.add_argument("--direct", action="store_true")
    parser.add_argument("--label")
    parser.add_argument("--input")
    parser.add_argument("--output")
    parser.add_argument("--node")
    args = parser.parse_args()
    if args.action.startswith("pilot-"):
        try:
            pilot_action(args)
        except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
            # Never include parsed state or subprocess output in diagnostics.
            parser.exit(1, "Pilot action failed (" + type(error).__name__ + "); inspect private inputs and output permissions\n")
        return
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
