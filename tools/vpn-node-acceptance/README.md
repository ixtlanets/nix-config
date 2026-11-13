# Isolated VPN-node acceptance runner

Python 3.10+ standard-library orchestration for **Linux**, with already-installed
`sing-box` and `curl`. No packages, root, sudo, systemd, server changes or existing
client changes. It runs nodes sequentially (1–8), never touches the default
sing-box configuration, and never changes routes, DNS, firewall or interfaces.
The manifest and executable are trusted private inputs, not an executable sandbox.

**Preserve every existing VPN connection.** The lead must collect authenticated
outbounds privately, verify protected-service/network baselines before/after, and
stop testing on any regression. This runner cannot independently certify that
unrelated services remained healthy. Do not stop any existing VPN to run it.

## Private manifest

Create an owner-only directory (`0700`) outside Git and place a `0600` manifest
there. Both manifest and output parents must already exist, be owned by the
current UID, and have exactly `0700` permissions. No symlink path components or
`..` are accepted. The manifest must be a regular owned `0600` file, at most 1 MiB.
The output must **not exist**: exclusive creation, no overwrites, mode `0600`.

Concrete schema/example (**documentation IPs and fake placeholders; not usable**):

```json
{
  "binary": "/usr/bin/sing-box",
  "nodes": [
    {
      "name": "documentation-vless",
      "expected_exit_ipv4": "198.51.100.20",
      "expected_http_exit_ipv4": ["203.0.113.20"],
      "outbound": {
        "type": "vless",
        "server": "192.0.2.10",
        "server_port": 443,
        "uuid": "00000000-0000-4000-8000-000000000001",
        "flow": "xtls-rprx-vision",
        "tls": {
          "enabled": true,
          "server_name": "replace-with-authenticated-sni.example",
          "utls": {"enabled": true, "fingerprint": "chrome"},
          "reality": {
            "enabled": true,
            "public_key": "REPLACE_WITH_AUTHENTICATED_REALITY_PUBLIC_KEY",
            "short_id": "REPLACE_WITH_AUTHENTICATED_SHORT_ID"
          }
        }
      }
    },
    {
      "name": "documentation-trojan",
      "expected_exit_ipv4": "198.51.100.21",
      "outbound": {
        "type": "trojan",
        "server": "192.0.2.11",
        "server_port": 443,
        "password": "REPLACE_WITH_PRIVATE_AUTHENTICATED_PASSWORD",
        "tls": {"enabled": true, "server_name": "replace.example"}
      }
    }
  ]
}
```

`nodes` is required; `binary` defaults to `/usr/bin/sing-box`. Node names are
unique, 1–64 ASCII alphanumeric/underscore/dot/hyphen characters. Each node needs
`name`, `expected_exit_ipv4`, and one `outbound`. The optional
`expected_http_exit_ipv4` list adds acceptable **Cloudflare trace** IPv4 exits to
the main expected exit; it never relaxes the two ipify identity checks. Record
why any additional exit is legitimate; an allowlist is not proof of independence
from another managed VPN. IPv6 exits do not count as the required IPv4 evidence.

Only VLESS **with authenticated TLS/Reality** and Trojan **with verified TLS**
are accepted. Servers must be numeric IPv4/IPv6, not hostnames, loopback,
link-local, unspecified, multicast or scoped IPv6. Nonempty `detour` is rejected;
empty detours and `routing_mark`, `domain_resolver`, `protect_path` are removed
from a deep copy. The runner forces `tag=node`, the requested `bind_interface`,
an 8-second connect timeout and disabled multiplex; `udp_over_tcp` and
`tcp_multi_path` are removed (no alternate-interface multipath subflows).
Unknown top-level fields fail closed. Only raw transport, WebSocket and
HTTPUpgrade are supported: HTTP/2/gRPC transport pools are deliberately rejected
because they could hide upstream reconnects. TLS certificate/key files, custom
resolvers, insecure TLS and alternative routing dials are not supported. Adapt
unsupported configs privately with lead review; do not weaken encryption.

## Run (lead, later)

```sh
python3 tools/vpn-node-acceptance/probe.py \
  --manifest /absolute/private0700/nodes.json \
  --output /absolute/private0700/results-new.json \
  --interface wlo1 \
  --negative-canary
```

`--negative-canary` is optional. The supplied interface must exist and have a
Linux sysfs physical-device entry (not `lo`, TUN or an automatically chosen
route). Some kernels require an existing capability for sing-box to set
`SO_BINDTODEVICE`; a permission failure is a failed test, **not permission to use
sudo, change capabilities, or omit the binding**. Explicit binding is enforced
by sing-box/kernel, not certified by a packet capture. There is a small free-port
allocation race; readiness fails closed unless `/proc` proves the listener
belongs to the owned process and its SOCKS handshake succeeds.

Each node gets a private `0700` temporary directory with `0600` config/log/body
files, a foreground process in its own session, one loopback mixed inbound and
one encrypted outbound. The TCP and UDP port are reserved together and released
immediately before launch. `sing-box check -c OWN_CONFIG -D OWN_DIRECTORY` must
succeed before launch. No inherited proxy or sing-box environment is used.

Checks, with fresh **separate curl subprocesses** (no pooled upstream transport):

- ipify HTTPS IPv4 identity, repeated again later (at least two connections);
- independent Cloudflare HTTPS trace: retain **only** `ip`, optional `h2`, `tls`;
- `https://example.com/` and `https://www.wikipedia.org/`, 2xx/3xx without following
  redirects, domain targets sent via **SOCKS5h** (remote DNS, never local resolve);
- Cloudflare bounded download: request exactly 1 MiB, require complete 200 response,
  record actual bytes/duration; **not a speed/stress certification**;
- SOCKS5 UDP ASSOCIATE with control TCP kept open, encapsulated DNS query to
  `1.1.1.1:53` for `example.com`, bounded compression/name/RR parsing, transaction
  ID, question, rcode and matching A/CNAME answers checked. Actual Python sockets
  connect/send only to loopback. No local resolver fallback;
- optional negative canary: after stopping **only our process group**, a fresh
  curl through its same loopback port must fail with connection error 7. No
  direct fallback or alteration of existing clients.

Curl uses `--disable` first (no curlrc), explicit `--proxy socks5h://127.0.0.1:PORT`,
`--noproxy ''`, an environment containing no proxy variables, one URL per fresh
process, `--no-keepalive`, no retries, HTTPS-only protocols, 8-second connect and 18-second
operation timeouts. It has `--max-filesize` **and** a 1-MiB child file-size resource
limit, including for chunked responses on older curl versions. HTTP target
responses are capped at 1 MiB each; identity responses are capped at 64 KiB by
curl. Download output never exceeds 1 MiB. Each child also has bounded file
handles, CPU time and disabled core dumps; sing-box gets two Go scheduler threads
and a soft 128-MiB Go memory target (not a hard RSS limit). No parallel stress.

There are at most seven curl operations per successful node with the canary,
each killed after at most 20 seconds; preflight has 8 seconds, readiness 5 seconds,
and the entire SOCKS UDP association has a 4-second deadline (plus a 4-second
loopback TCP connect and 4-second UDP receive). Fixed-size SOCKS reads also have
absolute deadlines, so dribbling bytes cannot extend them. Cleanup uses TERM,
then KILL of only owned process groups with
bounded waits. Total time is bounded by these sequential operations; allow a
conservative **30 minutes for eight failing/slow nodes**, not a stress run.

## Results and cleanup

The private JSON has per-node `pass` / `partial` / `fail`, per-check HTTP codes,
exit IPv4s, byte counts, DNS rcode/answers, durations, isolation checks and cleanup
booleans. UDP unsupported/unavailable is **partial**, never a full pass; malformed
SOCKS/DNS evidence or any required failed check is **fail**. The initial exit
failure short-circuits further node traffic. No status certifies an untested
check. CLI exits: `0` pass, `2` partial, `1` fail. Terminal output is only a small
status/count summary and fixed redacted error code. No credentials, full configs,
raw trace, child stdout/stderr or curl stderr are printed/copied into reports.

SIGINT/SIGTERM/SIGHUP trigger bounded cleanup and a failed/interrupted private
report; repeated signals cannot interrupt cleanup. SIGKILL, host crash and power
loss cannot be handled. Cleanup removes **only tracked files with matching inode,
device, UID and regular-file type**, then its exact empty owned directory. No
recursive deletion, glob kills or service restarts. Cleanup failure overrides a
pass and stops subsequent nodes; `owned_resources` retains the exact run directory,
local port and process-group ID for lead inspection. Do not delete residual
private configs or signal a PID until ownership is independently rechecked.
Live-process files are intentionally retained if termination cannot be confirmed.

**Cannot certify mobile/cellular, TUN routing, DNS/IP leaks, kill-switch, Wi-Fi/
cellular handoff, reboot survival, long-term reliability or throughput.** This is
userspace encrypted transport/egress evidence from the selected physical uplink;
lead baseline checks, real authenticated end-to-end execution, and separate
vantage/client certification remain necessary.

## Tests (no external connections)

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s tools/vpn-node-acceptance -p 'test_*.py' -v
```

The subprocess fixture `fake_process.py` is **not sing-box/curl**: it emits
synthetic HTTPS bodies and serves a local SOCKS5 UDP DNS harness, with every
actual socket on loopback. Tests also mock public curl/process boundaries for
error paths. Test temporary files stay under this directory. Passing tests do
not establish actual VPN authentication, TLS, upstream reconnects or egress.
