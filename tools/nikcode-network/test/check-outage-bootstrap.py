#!/usr/bin/env python3
"""Opt-in live check of DIRECT HTTPS while both synthetic proxy nodes are down.

Run directly; this is not part of the default unit tests. Requires Node, curl,
and sing-box >= 1.14. Example:
  python test/check-outage-bootstrap.py --sing-box /path/to/sing-box --interface wlo1

Uses the real Worker renderer, public HTTPS, and fake loopback nodes. It never
reads personal state, installs a TUN, or changes remote services.
"""

import argparse
import copy
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_URL = "https://config.nikcode.xyz/"
FIXTURE = """
import { singBoxPilot, validPilot } from './src/worker.js';
const nodes = ['a', 'b'].map((id, index) => ({
  id: 'node-' + id, enabled: true, host: '127.0.0.' + (index + 1),
  port: 9, protocol: 'vless', server_name: 'www.example.com',
  public_key: 'A'.repeat(43), short_id: '0123456789abcdef',
}));
const device = {
  id: 'outage-test', hash: 'a'.repeat(64), enabled: true, tailscale: false,
  credentials: {
    'node-a': { uuid: '11111111-1111-4111-8111-111111111111' },
    'node-b': { uuid: '22222222-2222-4222-8222-222222222222' },
  },
};
const config = { schema: 1, nodes, devices: [device] };
if (!validPilot(config)) throw new Error('Invalid synthetic fixture');
console.log(JSON.stringify(singBoxPilot(config, device)));
"""


def fetch(interface=None, socks_port=None):
    command = [
        "curl", "--disable", "--fail", "--silent", "--show-error",
        "--connect-timeout", "4", "--max-time", "12",
        "--write-out", "\n%{http_code}",
    ]
    if socks_port is None:
        command += ["--proxy", "", "--noproxy", "*"]
        if interface:
            command += ["--interface", interface]
    else:
        command += ["--noproxy", "", "--socks5-hostname", f"127.0.0.1:{socks_port}"]
    response = subprocess.run(command + [PUBLIC_URL], capture_output=True, text=True)
    body, _, status = response.stdout.rpartition("\n")
    return response.returncode, status, body, response.stderr.strip()


def run_profile(binary, profile, directory, label):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    profile = copy.deepcopy(profile)
    profile["inbounds"][0]["listen_port"] = port
    config_path = directory / f"{label}.json"
    config_path.write_text(json.dumps(profile))
    config_path.chmod(0o600)
    check = subprocess.run(
        [binary, "check", "-c", str(config_path)],
        cwd=directory, capture_output=True, text=True,
    )
    if check.returncode:
        raise RuntimeError(f"{label}: sing-box check failed: {check.stderr.strip()}")
    log_path = directory / f"{label}.log"
    with log_path.open("w") as log:
        process = subprocess.Popen(
            [binary, "run", "-c", str(config_path)],
            cwd=directory, stdout=log, stderr=log,
        )
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError(f"{label}: sing-box exited before listening")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    time.sleep(0.05)
            else:
                raise RuntimeError(f"{label}: SOCKS listener did not start")
            return fetch(socks_port=port)
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sing-box", default=shutil.which("sing-box"))
    parser.add_argument("--interface", help="Bind outer connections to this physical interface")
    args = parser.parse_args()
    if not args.sing_box:
        parser.error("sing-box was not found; provide --sing-box")
    binary = str(Path(args.sing_box).resolve())
    for dependency in ("node", "curl"):
        if not shutil.which(dependency):
            parser.error(f"{dependency} was not found")

    control = fetch(interface=args.interface)
    if control[0] or control[1] != "200":
        raise RuntimeError(f"Physical HTTPS control failed: curl={control[0]}, HTTP={control[1]} {control[3]}")
    rendered = subprocess.run(
        ["node", "--input-type=module", "-e", FIXTURE],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    profile = json.loads(rendered.stdout)
    profile["log"] = {"disabled": True}
    profile["inbounds"] = [{"type": "mixed", "tag": "local", "listen": "127.0.0.1"}]
    profile["experimental"]["cache_file"]["enabled"] = False
    for rule in profile["route"]["rules"]:
        if rule.get("inbound") == ["tun-in"]:
            rule["inbound"] = ["local"]
    if args.interface:
        for outbound in profile["outbounds"]:
            if outbound["type"] != "urltest":
                outbound["bind_interface"] = args.interface

    # /tmp keeps generated config, logs and any runtime files outside the repo.
    with tempfile.TemporaryDirectory(prefix="nikcode-outage-", dir="/tmp") as temp:
        directory = Path(temp)
        directory.chmod(0o700)
        positive = run_profile(binary, profile, directory, "issued-renderer")
        if positive[0] or positive[1] != "200" or positive[2] != control[2]:
            raise RuntimeError(f"DIRECT refresh failed with dead nodes: curl={positive[0]}, HTTP={positive[1]} {positive[3]}")
        negative_profile = copy.deepcopy(profile)
        direct = next(outbound for outbound in negative_profile["outbounds"] if outbound["tag"] == "direct")
        direct.pop("domain_resolver", None)
        negative = run_profile(binary, negative_profile, directory, "inherited-resolver-control")
        if negative[0] == 0:
            raise RuntimeError("Negative control unexpectedly succeeded; the regression seam was not exercised")

    print(f"PASS: real renderer + two dead nodes -> public subscription host HTTP {positive[1]}")
    print(f"PASS: removing only DIRECT domain_resolver reproduces failure (curl {negative[0]})")
    print("No personal state, TUN, live proxy nodes or remote services were used.")


if __name__ == "__main__":
    main()
