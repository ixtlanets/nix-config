#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ManualRequestError(RuntimeError):
    pass


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ManualRequestError("configuration must be a JSON object")
    return value


def read_secret(path: str) -> str:
    expanded = os.path.expandvars(path)
    value = Path(expanded).read_text(encoding="utf-8").strip()
    if not value:
        raise ManualRequestError(f"empty secret file: {expanded}")
    return value


def post_json(url: str, token: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as response:
            value = json.load(response)
    except HTTPError as error:
        try:
            message = json.loads(error.read()).get("message")
        except (json.JSONDecodeError, AttributeError):
            message = None
        raise ManualRequestError(message or f"ReadMeABook returned HTTP {error.code}") from error
    except URLError as error:
        raise ManualRequestError(f"cannot reach ReadMeABook: {error.reason}") from error
    if not isinstance(value, dict):
        raise ManualRequestError("ReadMeABook returned an invalid response")
    return value


def get_json(url: str, token: str) -> dict[str, Any]:
    request = Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urlopen(request, timeout=15) as response:
            value = json.load(response)
    except HTTPError as error:
        try:
            message = json.loads(error.read()).get("message")
        except (json.JSONDecodeError, AttributeError):
            message = None
        raise ManualRequestError(message or f"ReadMeABook returned HTTP {error.code}") from error
    except URLError as error:
        raise ManualRequestError(f"cannot reach ReadMeABook: {error.reason}") from error
    if not isinstance(value, dict):
        raise ManualRequestError("ReadMeABook returned an invalid response")
    return value


def login(config: dict[str, Any], username_key: str, password_file_key: str) -> str:
    base_url = config["rmab_url"].rstrip("/")
    password = read_secret(config[password_file_key])
    response = post_json(
        f"{base_url}/api/auth/local/login",
        None,
        {"password": password, "username": config[username_key]},
    )
    token = response.get("accessToken")
    if not isinstance(token, str) or not token:
        raise ManualRequestError(f"login for {config[username_key]} returned no access token")
    return token


def require_manual_approval(config: dict[str, Any], requester_token: str) -> None:
    base_url = config["rmab_url"].rstrip("/")

    identity = get_json(f"{base_url}/api/auth/me", requester_token).get("user")
    if not isinstance(identity, dict) or identity.get("role") != "user":
        raise ManualRequestError("requester token is not bound to a user-role account")
    user_id = identity.get("id")
    if not isinstance(user_id, str) or not user_id:
        raise ManualRequestError("requester identity has no user ID")

    admin_token = login(config, "admin_username", "admin_password_file")

    global_settings = get_json(
        f"{base_url}/api/admin/settings/auto-approve", admin_token
    )
    users_response = get_json(f"{base_url}/api/admin/users", admin_token)
    users = users_response.get("users")
    if not isinstance(users, list):
        raise ManualRequestError("admin user list returned an invalid response")
    matches = [user for user in users if isinstance(user, dict) and user.get("id") == user_id]
    if len(matches) != 1:
        raise ManualRequestError("requester identity did not match exactly one configured user")

    user_auto_approve = matches[0].get("autoApproveRequests")
    global_auto_approve = global_settings.get("autoApproveRequests") is True
    effective_auto_approve = (
        user_auto_approve is True
        or (user_auto_approve is None and global_auto_approve)
    )
    if effective_auto_approve:
        raise ManualRequestError("auto-approval is enabled for the requester")


def topic_id(result: dict[str, Any]) -> str | None:
    info_url = result.get("infoUrl")
    if not isinstance(info_url, str):
        return None
    match = re.search(r"(?:[?&])t=(\d+)(?:$|[&#])", info_url)
    return match.group(1) if match else None


def search(
    config: dict[str, Any], token: str, title: str, author: str
) -> list[dict[str, Any]]:
    response = post_json(
        f"{config['rmab_url'].rstrip('/')}/api/audiobooks/search-torrents",
        token,
        {"author": author, "title": title},
    )
    results = response.get("results")
    if not isinstance(results, list):
        raise ManualRequestError("torrent search returned an invalid result list")
    return [result for result in results if isinstance(result, dict)]


def safe_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": result.get("format"),
        "indexer": result.get("indexer"),
        "leechers": result.get("leechers"),
        "protocol": result.get("protocol"),
        "rank": result.get("rank"),
        "score": result.get("finalScore"),
        "seeders": result.get("seeders"),
        "size_bytes": result.get("size"),
        "title": result.get("title"),
        "topic_id": topic_id(result),
    }


def select_topic(results: list[dict[str, Any]], wanted_topic_id: str) -> dict[str, Any]:
    matches = [result for result in results if topic_id(result) == wanted_topic_id]
    if len(matches) != 1:
        raise ManualRequestError(
            f"topic ID {wanted_topic_id} matched {len(matches)} releases; expected exactly one"
        )
    return matches[0]


def request_plan(
    title: str, author: str, wanted_topic_id: str, result: dict[str, Any]
) -> dict[str, Any]:
    return {
        "action": "would-request",
        "author": author,
        "manual_id": f"manual:rutracker:{wanted_topic_id}",
        "release": safe_result(result),
        "title": title,
    }


def create_request(
    config: dict[str, Any], token: str, title: str, author: str, manual_id: str, result: dict[str, Any]
) -> dict[str, Any]:
    response = post_json(
        f"{config['rmab_url'].rstrip('/')}/api/audiobooks/request-with-torrent",
        token,
        {
            "audiobook": {"asin": manual_id, "author": author, "title": title},
            "torrent": result,
        },
    )
    request = response.get("request")
    if not isinstance(request, dict):
        raise ManualRequestError("request creation returned no request")
    if request.get("status") != "awaiting_approval":
        raise ManualRequestError(
            f"request entered unsafe status {request.get('status')!r}; expected 'awaiting_approval'"
        )
    request_id = request.get("id")
    if not isinstance(request_id, str) or not request_id:
        raise ManualRequestError("request creation returned no request ID")
    return {
        "action": "requested",
        "manual_id": manual_id,
        "request_id": request_id,
        "status": "awaiting_approval",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create guarded manual ReadMeABook requests")
    parser.add_argument("--config", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    search_command = commands.add_parser("search", help="search configured indexers")
    search_command.add_argument("--title", required=True)
    search_command.add_argument("--author", required=True)
    search_command.add_argument("--json", action="store_true", dest="as_json")
    request_command = commands.add_parser("request", help="select one release and create a manual request")
    request_command.add_argument("--title", required=True)
    request_command.add_argument("--author", required=True)
    request_command.add_argument("--topic-id", required=True)
    request_command.add_argument("--json", action="store_true", dest="as_json")
    request_command.add_argument("--execute", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = load_config(args.config)
        requester_token = login(
            config, "requester_username", "requester_password_file"
        )
        if args.command == "search":
            results = [
                safe_result(result)
                for result in search(config, requester_token, args.title, args.author)
            ]
            if args.as_json:
                print(json.dumps({"results": results}, ensure_ascii=False, sort_keys=True))
            else:
                for result in results:
                    print(
                        f"{result['rank']}: topic={result['topic_id'] or '-'} "
                        f"size={result['size_bytes']} seeders={result['seeders']} "
                        f"{result['title']}"
                    )
            return 0
        if args.command == "request":
            if not re.fullmatch(r"\d+", args.topic_id):
                raise ManualRequestError("topic ID must contain only decimal digits")
            if args.execute:
                require_manual_approval(config, requester_token)
            selected = select_topic(
                search(config, requester_token, args.title, args.author), args.topic_id
            )
            plan = request_plan(args.title, args.author, args.topic_id, selected)
            if args.execute:
                plan = create_request(
                    config,
                    requester_token,
                    args.title,
                    args.author,
                    plan["manual_id"],
                    selected,
                )
            if args.as_json:
                print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
            else:
                print(f"action: {plan['action']}")
                print(f"manual_id: {plan['manual_id']}")
                if args.execute:
                    print(f"request_id: {plan['request_id']}")
                    print(f"status: {plan['status']}")
                else:
                    print(f"release: {plan['release']['title']}")
            return 0
    except (KeyError, OSError, ValueError, ManualRequestError) as error:
        print(f"manual request error: {error}", file=sys.stderr)
        return 1
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
