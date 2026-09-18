#!/usr/bin/env python3
"""ADS-B sightings logger.

Polls readsb/tar1090 aircraft.json and records every aircraft observed,
even without a decoded position. Output: JSONL, one line per event.

Events:
  first — aircraft appeared (or returned after >GAP_S of silence)
  seen  — heartbeat while continuously visible (every HEARTBEAT_S)

State (first-seen continuity) survives restarts via /data/state.json.
"""
import json
import os
import time
import urllib.request

URL = os.environ.get("AC_URL", "http://tar1090/data/aircraft.json")
DATA_DIR = os.environ.get("AC_DATA", "/data")
HEARTBEAT_S = int(os.environ.get("AC_HEARTBEAT", "600"))
GAP_S = 120
POLL_S = 10
STATE_TTL = 86400  # prune records unseen longer than this

state = {}


def load_state():
    try:
        with open(os.path.join(DATA_DIR, "state.json")) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state():
    tmp = os.path.join(DATA_DIR, "state.json.tmp")
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, os.path.join(DATA_DIR, "state.json"))


def log(event, now, ac, rec):
    line = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now)),
        "event": event,
        "hex": ac.get("hex"),
        "flight": (ac.get("flight") or "").strip() or None,
        "squawk": ac.get("squawk"),
        "category": ac.get("category"),
        "alt_baro": ac.get("alt_baro"),
        "gs": ac.get("gs"),
        "track": ac.get("track"),
        "lat": ac.get("lat"),
        "lon": ac.get("lon"),
        "messages": ac.get("messages"),
        "rssi": ac.get("rssi"),
        "first_seen": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(rec["first"])),
    }
    path = os.path.join(
        DATA_DIR, "sightings-%s.jsonl" % time.strftime("%Y-%m-%d", time.localtime(now))
    )
    with open(path, "a") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def poll():
    with urllib.request.urlopen(URL, timeout=8) as r:
        return json.load(r)


def main():
    global state
    state = load_state()
    print("sightings logger started, polling", URL, flush=True)
    while True:
        try:
            data = poll()
        except Exception as e:
            print("poll error:", e, flush=True)
            time.sleep(POLL_S)
            continue
        now = time.time()
        for ac in data.get("aircraft", []):
            hexid = ac.get("hex")
            if not hexid:
                continue
            rec = state.get(hexid)
            if rec is None or now - rec.get("last", 0) > GAP_S:
                if rec is None:
                    rec = {"first": now, "hb": 0, "max_alt": None, "calls": []}
                    state[hexid] = rec
                else:
                    rec["first"] = now  # returned after a gap
                    rec["hb"] = 0
                rec["last"] = now
                log("first", now, ac, rec)
                print(
                    "first sighting:",
                    hexid,
                    (ac.get("flight") or "").strip(),
                    ac.get("alt_baro"),
                    flush=True,
                )
            else:
                rec["last"] = now
                alt = ac.get("alt_baro")
                if isinstance(alt, (int, float)):
                    if isinstance(rec["max_alt"], (int, float)):
                        rec["max_alt"] = max(rec["max_alt"], alt)
                    else:
                        rec["max_alt"] = alt
                fl = (ac.get("flight") or "").strip()
                if fl and fl not in rec["calls"]:
                    rec["calls"].append(fl)
                if now - rec.get("hb", 0) >= HEARTBEAT_S:
                    rec["hb"] = now
                    log("seen", now, ac, rec)
        for hexid in list(state):
            if now - state[hexid].get("last", 0) > STATE_TTL:
                del state[hexid]
        save_state()
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
