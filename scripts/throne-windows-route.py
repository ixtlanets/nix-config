#!/usr/bin/env python3
"""Install a macOS-like Windows route profile into Throne's SQLite config."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path


PROFILE_NAME = "Windows macOS-like"


def default_db_path() -> Path:
    return Path("/mnt/c/Users/nik/AppData/Roaming/Throne/config/throne.db")


def windows_throne_running() -> bool:
    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "Get-Process Throne,ThroneCore -ErrorAction SilentlyContinue | Select-Object -First 1",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return False
    return bool(result.stdout.strip())


def backup_database(db_path: Path) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = db_path.parent / f"backup-throne-route-{timestamp}"
    backup_dir.mkdir()
    for suffix in ["", "-wal", "-shm"]:
        source = Path(str(db_path) + suffix)
        if source.exists():
            shutil.copy2(source, backup_dir / source.name)
    return backup_dir


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def insert_rule(conn: sqlite3.Connection, columns: list[str], values: dict[str, object]) -> None:
    row = {
        "route_profile_id": values["route_profile_id"],
        "rule_order": values["rule_order"],
        "name": values.get("name", ""),
        "type": 0,
        "ip_version": "",
        "network": "",
        "protocol": "",
        "inbound_json": "[]",
        "domain_json": "[]",
        "domain_suffix_json": "[]",
        "domain_keyword_json": "[]",
        "domain_regex_json": "[]",
        "source_ip_cidr_json": "[]",
        "source_ip_is_private": 0,
        "ip_cidr_json": "[]",
        "ip_is_private": 0,
        "source_port_json": "[]",
        "source_port_range_json": "[]",
        "port_json": "[]",
        "port_range_json": "[]",
        "process_name_json": "[]",
        "process_path_json": "[]",
        "process_path_regex_json": "[]",
        "rule_set_json": "[]",
        "invert": 0,
        "outbound_id": -2,
        "action": values.get("action", "route"),
        "reject_method": "",
        "no_drop": 0,
        "override_address": "",
        "override_port": "",
        "sniffers_json": "[]",
        "sniff_override_dest": 0,
        "strategy": "",
        "wifi_ssid_json": "[]",
        "wifi_bssid_json": "[]",
    }
    row.update(values)
    insert_columns = [column for column in columns if column in row]
    placeholders = ", ".join("?" for _ in insert_columns)
    conn.execute(
        f"INSERT INTO route_rules ({', '.join(insert_columns)}) VALUES ({placeholders})",
        [row[column] for column in insert_columns],
    )


def install_route_profile(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        existing = conn.execute(
            "SELECT id FROM route_profiles WHERE name = ?", (PROFILE_NAME,)
        ).fetchone()
        if existing:
            route_id = int(existing[0])
        else:
            row = conn.execute(
                "UPDATE entity_ids SET route_profile_last_id = route_profile_last_id + 1 "
                "RETURNING route_profile_last_id"
            ).fetchone()
            route_id = int(row[0])
            conn.execute(
                "INSERT INTO route_profiles (id, name, default_outbound_id) VALUES (?, ?, ?)",
                (route_id, PROFILE_NAME, -1),
            )

        conn.execute(
            "UPDATE route_profiles SET name = ?, default_outbound_id = ?, "
            "updated_at = strftime('%s', 'now') WHERE id = ?",
            (PROFILE_NAME, -1, route_id),
        )
        conn.execute("DELETE FROM route_rules WHERE route_profile_id = ?", (route_id,))

        columns = table_columns(conn, "route_rules")
        rules = [
            {
                "name": "Sniff mixed and TUN",
                "action": "sniff",
                "inbound_json": json.dumps(["mixed-in", "tun-in"]),
            },
            {
                "name": "Route DNS",
                "action": "hijack-dns",
                "protocol": "dns",
            },
            {
                "name": "Private IP direct",
                "action": "route",
                "ip_is_private": 1,
                "outbound_id": -2,
            },
            {
                "name": "Russian IP direct",
                "action": "route",
                "rule_set_json": json.dumps(["geoip-ru"]),
                "outbound_id": -2,
            },
            {
                "name": "Block QUIC",
                "action": "reject",
                "network": "udp",
                "port_json": json.dumps([443]),
            },
        ]
        for index, rule in enumerate(rules):
            insert_rule(conn, columns, {"route_profile_id": route_id, "rule_order": index, **rule})

        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("current_route_id", str(route_id)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("active_routing", PROFILE_NAME),
        )
        conn.commit()
        print(f"Installed route profile {PROFILE_NAME!r} with id {route_id}.")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install the Windows/macOS-like Throne route profile."
    )
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--force", action="store_true", help="write even if Throne is running")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"Throne database not found: {args.db}", file=sys.stderr)
        return 1
    if windows_throne_running() and not args.force:
        print("Throne is running. Close Throne and run this script again.", file=sys.stderr)
        return 2

    backup_dir = backup_database(args.db)
    print(f"Backup written to {backup_dir}")
    install_route_profile(args.db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
