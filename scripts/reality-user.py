#!/usr/bin/env python3

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


DEFAULT_BASE = Path("/opt/reality-ezpz")
DEFAULT_IMAGE = "gzxhwq/sing-box:1.8.14"
VALID_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def fail(message: str) -> "NoReturn":
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def now_suffix() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        fail(f"missing file: {path}")
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {path}: {exc}")


def load_kv(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                fail(f"invalid line in {path}: {line}")
            key, value = line.split("=", 1)
            data[key] = value
    except FileNotFoundError:
        fail(f"missing file: {path}")
    return data


def save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n")


def save_users(path: Path, users: list[dict]) -> None:
    lines = [f"{user['name']}={user['uuid']}" for user in sorted(users, key=lambda item: item["name"].casefold())]
    path.write_text("\n".join(lines) + "\n")


def backup_file(path: Path) -> Path:
    backup = path.with_name(f"{path.name}.bak.{now_suffix()}")
    shutil.copy2(path, backup)
    return backup


def detect_image(compose_path: Path) -> str:
    try:
        for line in compose_path.read_text().splitlines():
            match = re.match(r"\s*image:\s*(\S+)\s*$", line)
            if match:
                return match.group(1)
    except FileNotFoundError:
        pass
    return DEFAULT_IMAGE


def engine_users(engine: dict) -> list[dict]:
    try:
        users = engine["inbounds"][1]["users"]
    except (KeyError, IndexError, TypeError):
        fail("could not find VLESS user list at engine.conf inbounds[1].users")
    if not isinstance(users, list):
        fail("engine user list is not an array")
    return users


def find_user(users: list[dict], name: str) -> dict | None:
    for user in users:
        if user.get("name") == name:
            return user
    return None


def validate_name(name: str) -> None:
    if not VALID_NAME_RE.fullmatch(name):
        fail("invalid user name; allowed chars: A-Z a-z 0-9 . _ -")


def build_share_url(config: dict[str, str], user: dict) -> str:
    transport = config.get("transport", "tcp")
    security = config.get("security", "reality")
    server = config.get("server")
    port = config.get("port")
    domain = config.get("domain", server or "")
    public_key = config.get("public_key")
    short_id = config.get("short_id")
    service_path = config.get("service_path", "")

    if not server or not port:
        fail("config is missing server or port")
    if security != "reality":
        fail(f"unsupported security for share URL: {security}")
    if transport not in {"tcp", "http", "ws", "grpc"}:
        fail(f"unsupported transport for share URL: {transport}")
    if not public_key or not short_id:
        fail("config is missing public_key or short_id")

    query: list[tuple[str, str]] = [
        ("security", "reality"),
        ("encryption", "none"),
        ("alpn", "http/1.1" if transport == "ws" else "h2,http/1.1"),
        ("headerType", "none"),
        ("fp", "chrome"),
        ("type", "xhttp" if transport == "http" else transport),
        ("sni", domain.split(":", 1)[0]),
        ("pbk", public_key),
        ("sid", short_id),
    ]

    flow = user.get("flow")
    if flow:
        query.append(("flow", flow))
    if transport in {"ws", "http"}:
        query.append(("host", server))
        query.append(("path", f"/{service_path}"))
    if transport == "grpc":
        query.append(("mode", "gun"))
        query.append(("serviceName", service_path))

    query_string = "&".join(f"{quote(key)}={quote(str(value), safe=',/') }" for key, value in query)
    return f"vless://{user['uuid']}@{server}:{port}?{query_string}#{quote(user['name'])}"


def render_qr(text: str) -> None:
    if not shutil.which("qrencode"):
        fail("qrencode not installed")
    subprocess.run(["qrencode", "-t", "ansiutf8", text], check=True)


def validate_engine(engine_path: Path, image: str, skip_check: bool) -> None:
    if skip_check:
        return
    command = [
        "docker",
        "run",
        "--rm",
        "-e",
        "ENABLE_DEPRECATED_LEGACY_DNS_SERVERS=true",
        "-e",
        "ENABLE_DEPRECATED_MISSING_DOMAIN_RESOLVER=true",
        "-v",
        f"{engine_path}:/tmp/config.json:ro",
        image,
        "check",
        "-c",
        "/tmp/config.json",
    ]
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        fail("docker not found; rerun with --skip-check only if you know config is valid")
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or "sing-box check failed"
        fail(message)


def sync_users_file(users_path: Path, users: list[dict]) -> None:
    save_users(users_path, users)


def cmd_list(args: argparse.Namespace) -> None:
    users = engine_users(load_json(args.engine))
    for user in sorted(users, key=lambda item: item.get("name", "").casefold()):
        print(f"{user.get('name')}\t{user.get('uuid')}")


def cmd_show(args: argparse.Namespace) -> None:
    engine = load_json(args.engine)
    config = load_kv(args.config)
    user = find_user(engine_users(engine), args.name)
    if user is None:
        fail(f"unknown user: {args.name}")
    share_url = build_share_url(config, user)
    print(share_url)
    if args.qr:
        print()
        render_qr(share_url)


def cmd_add(args: argparse.Namespace) -> None:
    validate_name(args.name)
    engine = load_json(args.engine)
    config = load_kv(args.config)
    users = engine_users(engine)
    if find_user(users, args.name) is not None:
        fail(f"user already exists: {args.name}")

    new_user = {
        "uuid": str(uuid.uuid4()),
        "name": args.name,
    }

    sample_user = users[0] if users else None
    if sample_user and sample_user.get("flow"):
        new_user["flow"] = sample_user["flow"]
    elif config.get("transport", "tcp") == "tcp":
        new_user["flow"] = "xtls-rprx-vision"

    engine_backup = backup_file(args.engine)
    users_backup = backup_file(args.users) if args.users.exists() else None

    try:
        users.append(new_user)
        users.sort(key=lambda item: item.get("name", "").casefold())
        save_json(args.engine, engine)
        sync_users_file(args.users, users)
        validate_engine(args.engine, detect_image(args.compose), args.skip_check)
    except BaseException:
        shutil.copy2(engine_backup, args.engine)
        if users_backup is not None:
            shutil.copy2(users_backup, args.users)
        raise

    print(f"added {args.name}\t{new_user['uuid']}")
    print()
    print(build_share_url(config, new_user))
    if args.qr:
        print()
        render_qr(build_share_url(config, new_user))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage VLESS users without regenerating engine.conf")
    parser.set_defaults(base=DEFAULT_BASE)
    parser.add_argument("--engine", type=Path, default=DEFAULT_BASE / "engine.conf", help="path to engine.conf")
    parser.add_argument("--config", type=Path, default=DEFAULT_BASE / "config", help="path to reality-ezpz config")
    parser.add_argument("--users", type=Path, default=DEFAULT_BASE / "users", help="path to users file")
    parser.add_argument("--compose", type=Path, default=DEFAULT_BASE / "docker-compose.yml", help="path to docker-compose.yml")
    parser.add_argument("--skip-check", action="store_true", help="skip sing-box config validation after add")

    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="list existing users")
    list_parser.set_defaults(func=cmd_list)

    add_parser = subparsers.add_parser("add", help="add new user")
    add_parser.add_argument("name", help="user name")
    add_parser.add_argument("--qr", action="store_true", help="print terminal QR code after adding")
    add_parser.set_defaults(func=cmd_add)

    show_parser = subparsers.add_parser("show", help="show VLESS share URL for user")
    show_parser.add_argument("name", help="user name")
    show_parser.add_argument("--qr", action="store_true", help="print terminal QR code")
    show_parser.set_defaults(func=cmd_show)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
