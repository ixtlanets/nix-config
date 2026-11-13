# Isolated FOUR-NODE pool acceptance (implementation, not live acceptance)

[pool_probe.py](<tools/vpn-node-acceptance/pool_probe.py>) is a Python **3.11+ / Linux**, standard-library CLI, using the
unchanged sibling [probe.py](<tools/vpn-node-acceptance/probe.py>) ownership/process primitives, an already installed
`curl`, and the operator-supplied native sing-box executable. **Nothing has been
run against real nodes by this implementation task.** No deployment, profile
publication, service operation, SSH, browser, provider, pass, firewall, routing,
DNS-system, package or capability change is part of this runner.

## Preconditions and private preparation — operator, later only

* All four nodes must first have independently authenticated, accepted VLESS /
  Reality service and per-device credentials. Staged Poland/Italy units must be
  temporarily started under separate operator authorization before invocation;
  this runner never starts them. Existing services and production profiles remain
  unchanged. Do not publish a staged candidate merely to test this CLI.
* Use an **actual prospective production profile**, privately rendered by the
  existing `singBoxPilot` in [worker.js](<tools/nikcode-network/src/worker.js#L112-L183>), from the exact
  candidate projection/device. No ad-hoc profile generator, per-node fallback
  export, token URL fetch or profile printed to terminal. All four candidate nodes
  must already be enabled in that private candidate, with the correct device UUIDs.
* Choose an existing production-candidate device with `tailscale: false`. Integrated
  Tailscale endpoints are **refused**, not stripped: preserving their state/control
  plane would require private login/state and is outside userspace-only acceptance.
  Do not silently change `tailscale` or the device's `rule_set_mode` to fit the test.
  This cut oracle requires an actual **inline-rule** candidate. Remote-mode input
  fails before interface checks/core start (`foreign_cut_requires_inline_rules`):
  opaque, asynchronously fetched RU contents cannot provide its structural proof.
  One accepted device/mode does not certify the other devices/modes.
* [manage.py](<tools/nikcode-network/scripts/manage.py#L218-L235>) `pilot-export` deliberately forces **inline** rules for Local exports;
  it is **not** an exact production-mode export for a remote-mode device. If the
  private projected `PILOT_CONFIG.json` is already prepared, this recipe invokes the
  real renderer directly without changing its inputs. It is instructions for later,
  not something executed by the implementer:

```sh
# From repository root. PRIVATE is a pre-existing owned 0700 directory OUTSIDE Git.
# The projection is an owned 0600 private file. DEVICE is a non-secret device ID.
# No pass/provider/network operation is needed by this recipe.
umask 077
node --input-type=module - "$PRIVATE/PILOT_CONFIG.json" "$DEVICE" "$PRIVATE/candidate.json" <<'JS'
import fs from 'node:fs';
import {singBoxPilot, validPilot} from './tools/nikcode-network/src/worker.js';
try {
  const config = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const device = config.devices.find(d => d.id === process.argv[3] && d.enabled);
  const ids = config.nodes.filter(n => n.enabled).map(n => n.id).sort();
  if (!validPilot(config) || !device || device.tailscale !== false ||
      JSON.stringify(ids) !== JSON.stringify(['france','frankfurt','italy','poland'])) throw 0;
  const body = JSON.stringify(singBoxPilot(config, device));
  const fd = fs.openSync(process.argv[4], 'wx', 0o600);
  try { fs.writeFileSync(fd, body + '\n'); } finally { fs.closeSync(fd); }
} catch { process.stderr.write('private_preparation_failed\n'); process.exitCode = 1; }
JS
```

Preserve the exact input, including inline/remote RU rules and direct bootstrap,
LAN/private, RU-domain/GeoIP and public-IPv6 policy. Do not edit a production profile
into a synthetic reduced profile. Acquire any private candidate/projection by a
separately authorized process, not by this runner. Never put decrypted state,
profiles, tokens, UUIDs or manifests in the repository or paste them in chat.

Supply a separate owned **0600** manifest in the same kind of private directory:

```json
{
  "binary": "/absolute/path/to/verified/sing-box",
  "nodes": {
    "france": {"server": "<verified numeric public IP>", "server_port": 443, "expected_exit_ipv4": "<verified exit>"},
    "frankfurt": {"server": "<verified numeric public IP>", "server_port": 34443, "expected_exit_ipv4": "<verified exit>"},
    "poland": {"server": "<verified numeric public IP>", "server_port": 443, "expected_exit_ipv4": "<verified exit>"},
    "italy": {"server": "<verified numeric public IP>", "server_port": 443, "expected_exit_ipv4": "<verified exit>"}
  },
  "targets": {
    "api.ipify.org": "<independently verified current foreign A address>",
    "www.wikipedia.org": "<independently verified current foreign A address>"
  }
}
```

The example is deliberately non-usable. Use real verified ports, not the example
ports by assumption. Exactly four distinct server addresses and distinct expected
IPv4 exits are required; this runner does not establish the provenance of that
expected data. Addresses must be public numeric addresses, not DNS names/private
or mapped addresses. Pinned targets must be current certificate-valid foreign,
non-exempt IPv4 HTTPS destinations. Inline RU target collisions and potentially
matching DIRECT/reject/hijack exceptions are rejected before any core starts.
Both the numeric destination and original TLS hostname are checked, before/after
sniffing, against private/IP, exact bootstrap-domain, suffix and inline-RU rules.
The manifest cannot add arbitrary destinations or URLs. The SHA256 is fixed in code:

`1264361b5f8868c8768f7555d3e77e20118bf503c41ac08bb290a0d99056aa3a`

The executable must also identify itself as **sing-box 1.14.4**. A version string
alone is not sufficient. The binary and files are trusted local inputs, not an
untrusted-executable sandbox. Do not replace the executable while running.

* `wlo1` must already exist, be up, have the existing harness's physical-interface
  properties, and permit `SO_BINDTODEVICE` for this UID. The runner tests the bind
  without connecting before starting a core. Permission denial fails cleanly;
  it never tries sudo, capabilities, another interface or an existing VPN detour.
* Preserve unrelated VPNs and protected-service baselines externally before/after;
  stop on regression. The runner cannot certify those service baselines itself.
* No parent path component may be a symlink or `..`; artifact immediate parents must
  already be owned **0700** directories. Inputs must be regular owned **0600** files,
  at most 1 MiB. Absolute paths only. Input/output artifacts inside this repository
  are forbidden. Output must not exist (exclusive **0600** creation, no overwrite).

## Invocation — intentionally NOT executed for this implementation

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/vpn-node-acceptance/pool_probe.py \
  --manifest "$PRIVATE/pool-manifest.json" \
  --profile "$PRIVATE/candidate.json" \
  --output "$PRIVATE/pool-result-unique.json"
```

No dry-run option masquerades as acceptance. Invoking this command performs real
bounded traffic; operator authorization and the preconditions above are required.
Exit 0 means the isolated stages and cleanup passed; exit 1 means failure. Terminal
output is only `status` and a stage count. The whitelisted result has schema/status,
fixed core version/interface/acceptance kind, fixed error code (if any), stage
names/status/attempts/duration/role-only observed exit, a fixed all-down proof kind,
and cleanup booleans. No
addresses, paths, credentials, child errors, core data, HTTP bodies or profile are
reported. Inputs remain; owned temporary files disappear after cleanup.

## Isolation and acceptance contract

**All-down proves a topological cut, not per-flow error attribution.** For the two
fixed numeric foreign HTTPS flows, the actual core configuration must admit only the
four VLESS paths, each detoured through its exact owned gate. No matching DIRECT,
reject or DNS-hijack exception is allowed. All gates are disabled; pending dials and
established upstream streams have been closed; no upstream dial or success may occur
during either fresh request. The owned mixed listener must authenticate before and
after. Both requests must actually fail transport with a completed `000` HTTP status.
The same pins/core must succeed in the immediately preceding stage and again in the
next restoration stage; no restart or configuration/pin substitution intervenes.

These invariants prove there is **no allowed foreign VLESS cut edge**, independently
of which native URLTest or curl stream triggers a denial. A concurrent URLTest
refusal is neither evidence attributed to curl nor grounds for inconclusiveness.
Refusal counts are diagnostic only, not necessary or sufficient for passing. Generic
TLS/empty-response/proxy errors alone, counters alone, a dead/unauthenticated core,
HTTP responses (even error statuses), DNS-only failures and harness timeouts cannot
pass. A curl transport error can coexist with a different client defect; this oracle
does **not** claim that a specific gate refusal uniquely caused that error. It proves
the narrower requested fresh foreign fail-closed property under the validated cut.
Full acceptance still requires all eight actual stages and cleanup to pass.

The runner makes a deep clone of the actual profile. Allowed test-only differences:

1. Replace the one production TUN inbound with an authenticated `127.0.0.1` mixed
   listener, keeping `tun-in` so existing inbound-qualified sniff rules still apply.
   No TUN, system proxy, controller, UI or shared disk cache is started. Core logging
   is disabled; stdout/stderr are discarded. Existing controller/default-mode
   settings must be supported explicitly, not used to force a selection.
2. Retain DNS/rules/rule-set mode and all original VLESS remote addresses, ports,
   UUIDs, SNI, Reality and transport identities. Add a `detour: gate-ROLE` to each
   VLESS outbound; remove only its conflicting `bind_interface`. Gate SOCKS outbounds
   have **no** physical bind so loopback works. Direct exceptions bind to `wlo1`.
   Route interface auto-detection is disabled, not replaced by system route changes.
3. Each independently authenticated loopback SOCKS gate permits only CONNECT to its
   expected numeric node IP:port; domain targets, wrong address/port, UDP/BIND,
   unauthenticated clients and excess concurrent clients are refused. It cannot be
   an open proxy. Only its actual upstream sockets bind `SO_BINDTODEVICE=wlo1`.
   The retained local DNS server uses the OS resolver, outside these data gates:
   its DNS traffic is not proven physically isolated to `wlo1`. DNS rules and
   exceptions are not altered to hide this limit.
4. Gates are disabled locally; their pending handshakes/dials and established streams
   are cancelled/closed. Nothing stops or reconfigures a real node. Other gates and
   unrelated processes/streams are untouched. Restoration only enables owned gates.

The supported production subset deliberately excludes endpoints/Tailscale, services,
extra outbounds/tiers/selectors/DIRECT fallbacks, file-based rule sets, unknown dial
options/certificate files, pooled gRPC/HTTP transports and enabled multiplex. DNS
must have the current bootstrap/remote/local HTTPS scheme; node servers must be
numeric. Unsupported parts fail before starting any core, rather than silently
changing production semantics. The general shape validator/clone retain remote-mode
inputs, but acceptance refuses them before any core starts: the cut verifier only
understands inline RU rules and single destination-matcher families in exception
rules. It conservatively rejects combined/ambiguous matchers rather than mistaking
native OR-groups for AND; harmless unsupported custom rules may therefore fail closed.
All original supported inline exceptions remain unchanged. With cache disabled no
shared rule cache is used. Native `sing-box check` must pass before `run`.
This implementation was not validated against a live real production input.

The **flat four-member URLTest** and `route.final: proxy` are checked strictly:

* URL `https://www.gstatic.com/generate_204`, interval `1m`, tolerance `100`,
  `interrupt_exist_connections: false`. No extra URLTest options, timer shortening,
  forced selections, artificial latency or manual `/delay` probes.
* Every stage observes natural URLTest switching through fresh requests, not a
  fabricated selector state. No Clash API is needed or exposed.

| Stage | Locally available gates | Required observed IPv4 exit |
|---|---|---|
| baseline | all four | any expected node |
| poland_only | Poland | Poland |
| poland_to_italy | Italy | Italy, after Poland worked with France/Frankfurt absent |
| italy_to_poland | Poland | Poland, reverse transition |
| new_nodes_down | France + Frankfurt | France or Frankfurt |
| adminvps_down | Frankfurt | Frankfurt (France/Poland/Italy absent) |
| all_down | none | same successful foreign HTTPS targets must fail closed |
| restored | all four | an expected node, fresh HTTPS works again |

Each stage has a **145-second** monotonic observation deadline and at most 25
attempts; two consecutive complete observations are required. Each attempt is a
fresh curl/TLS process per target, up to 8 seconds each, no retries, redirects,
proxy environment inheritance, unproxied fallback or local target DNS lookup.
`--connect-to` supplies the **same pinned numeric SOCKS destination** at every
stage while the original hostname is used for certificate verification/SNI.
The local integration test inspects real curl SOCKS requests to verify this.
The two targets must both work before outage; ipify must identify an allowed exit.
For each all-down request, the actual cloned topology is revalidated before/after;
all four real gates must remain unavailable with no pending dials or upstream
streams; the owned mixed listener must authenticate before/after; attempted-dial and
connected counters must remain unchanged. Every supported connection traverses one
of these streams: enabled multiplex and pooled transports are refused, and disabling
cancels existing handshakes/dials/streams. Separate curl processes, no HTTP keepalive,
no shared TLS session and no shared core disk cache prevent client reuse. A completed
transport failure with zero HTTP is necessary but never sufficient without this cut.
After two complete rounds, restoration is reached normally; any restoration failure
still makes the entire run fail. Unexpected identified exits abort immediately.
Pins and the owned core remain unchanged across all stages.

Allow roughly **20 minutes** worst case including all eight stage bounds and owned
process cleanup. A stage timeout is failure, not proof of a broken service or a
promise that every sing-box failure mode reconverges within 145 seconds. A failure
aborts subsequent stages, including restoration observation; final cleanup still
closes every owned gate and process. It never changes real service availability.

SIGINT/SIGTERM/SIGHUP request bounded cancellation; cleanup kills only newly owned
process groups (including curl children), closes owned listeners/streams and removes
registered temporary artifacts. Repeated signals do not interrupt cleanup. SIGKILL,
power loss, malicious same-UID file replacement and kernel failures cannot promise
cleanup. If owned process cleanup or artifact identity fails, report failure and
retain the private workspace rather than recursively deleting or touching unknown
resources; owner inspection is required.

## Offline tests and explicit limits

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s tools/vpn-node-acceptance -p 'test_pool_probe.py' -v
```

[test_pool_probe.py](<tools/vpn-node-acceptance/test_pool_probe.py>) exercises the actual
main → run → command → request → observe path through an all-eight positive schedule,
using real loopback Gate objects/cut state. **Fake native execution, HTTP output and
core-health seams are unit tests, not live acceptance.** A separate test uses actual
curl against a local SOCKS server to check the numeric pin. Tests also cover foreign
DIRECT-rule/combined-matcher/opaque-remote rejection, clone/detour/gate tampering,
concurrent unrelated URLTest-like real refusals with/without structural evidence,
zero-owned-stream/pending-dial closure, attempted-dial guards, actual local mixed
authentication, HTTP/success/DNS/malformed-status/timeout rejection, native-check
failure cleanup, SHA+version refusal, private/exclusive output, owned process-group /
descendant timeout cleanup and an actual SIGTERM during a fake-core run.
Existing `singBoxPilot` is called offline with nonsecret fixtures for inline and
remote shapes (requires existing Node.js; otherwise that test skips). No native
binary or real node is started by these tests. Test artifacts are outside Git.
Synthetic successes do not establish native config compatibility or real failover.

**Implementation done does not mean live FOUR-NODE acceptance done.** This is
userspace native-client, fresh-HTTPS, real-exit evidence only when subsequently run.
It does not certify TUN/system/interface-wide leak policy, all apps, DNS leaks,
RU/private/bootstrap exception reachability, cellular/mobile, persistent kill-switch,
seamless existing TCP sessions, long-term reliability, throughput or reboot recovery.
Declared direct exceptions remain intact and are not foreign all-down failure targets.
They need separate reachability acceptance, not a claim that all connectivity must
stop. Preserving `interrupt_exist_connections: false` does not promise seamless TCP:
this runner intentionally closes only its own gate streams to emulate node loss.
