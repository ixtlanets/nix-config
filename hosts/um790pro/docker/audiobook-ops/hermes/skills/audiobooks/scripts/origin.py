#!/usr/bin/env python3
"""Print the current Hermes Telegram target without accepting caller input."""

from __future__ import annotations

import os
import re


CHAT_ID = re.compile(r"^-?[1-9][0-9]*$")
THREAD_ID = re.compile(r"^[1-9][0-9]*$")


def current_origin() -> str:
    platform = os.environ.get("HERMES_SESSION_PLATFORM", "").strip().lower()
    chat_id = os.environ.get("HERMES_SESSION_CHAT_ID", "").strip()
    thread_id = os.environ.get("HERMES_SESSION_THREAD_ID", "").strip()
    if platform != "telegram" or not CHAT_ID.fullmatch(chat_id):
        raise ValueError("a supported Telegram session origin is required")
    if thread_id and not THREAD_ID.fullmatch(thread_id):
        raise ValueError("Telegram thread ID is invalid")
    return f"telegram:{chat_id}" + (f":{thread_id}" if thread_id else "")


def main() -> int:
    try:
        print(current_origin())
    except ValueError as error:
        print(f"origin unavailable: {error}", file=__import__("sys").stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
