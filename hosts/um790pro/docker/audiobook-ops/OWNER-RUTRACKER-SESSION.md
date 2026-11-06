# Owner-only RuTracker session refresh

## Current Docker29 correction — parent acceptance pending

The local launcher now distinguishes the pinned OCI image-manifest digest
`sha256:258523d25e4e07028c3a206f0e03ae807b26a50a201dd320f09a18464ecf86fa`
from its config digest
`sha256:894893ed4d4557764df3e74d27c5bc1b3944e5a33ed410e62ab7c744b348f415`.
The retained nonsecret Docker 29.9.2/containerd projection reports the manifest
digest in both container `Image` and image-inspect `Id`. The old launcher required
the config digest there and refused this valid image before bootstrap.

Admission now requires an offline lookup of the exact pinned reference on the
fixed local daemon, matching the actual container image ID, exact pinned
`RepoDigests` membership and linux/amd64. The manifest-ID branch additionally
requires the pinned OCI image-manifest Descriptor digest, media type and size
2572. OCI indexes are refused. Classic config-ID stores remain supported when
the exact pinned-reference lookup independently resolves to the expected config
ID; Descriptor is optional there and must match if supplied. The query uses
missing-key-safe Go-template map `index` access for this optional field. Parent
read-only CLI probes on a cached modern image establish missing-key lookup
semantics; the classic-ID daemon responses in these tests are synthetic. No
actual classic daemon has been exercised for this correction. The raw public
manifest's verified SHA256 establishes its config.digest relationship. Docker's
Descriptor does **not** provide config.digest. All evidence is rechecked before
input/publication; no tag, pull, alternate daemon or owner selector is accepted.

The source pair exists **only in the local zenbook checkout** at the absolute
paths below; no remote transfer, installation or launch has been performed.
Current launcher SHA256:
`5e28284831dfac1439129041216c70d8601e35d5c4638983448e2299b5180cbd`.
Unchanged helper SHA256:
`3793099c1f16d624d80b3f83373d5b825f81e9f9505da79f1f8f004591d40887`.
This correction consumes **additional cycle 3 / aggregate cycle 5**, leaving
**2 additional cycles**. Further corrections require the parent's instruction.

The unchanged Docker29 boundary assertion was observed RED before launcher edits
and GREEN afterward. The author's 25 focused identity/transport tests and a 104-test socket-free
dedicated selection pass.
Wider author subsets selected 108 dedicated / 302 ordinary tests but returned
exit 1 with 8 / 41 socket-creation `EPERM` errors respectively, and no assertion
failures. They omit launcher-main tests and, in the ordinary subset, real Docker
Compose calls under the writer's restrictions. These are setup-limited subsets,
not full-suite acceptance. Parent execution and fresh independent Standards/Spec
reviews of the frozen candidate remain **pending**. Current evidence:
[CHECKPOINT.md](/home/nik/.hermes/task-evidence/rutracker-session-refresh-20261104/docker29-identity/CHECKPOINT.md).
Planned current parent acceptance record (parent to create/finalize):
[docker29-identity/ACCEPTANCE.md](/home/nik/.hermes/task-evidence/rutracker-session-refresh-20261104/docker29-identity/ACCEPTANCE.md).
No live login, captcha, cookie reuse, gateway recreation or search gate is closed
by this correction.

This owner-only engineering deliverable is for the owner `nik` on
`um790pro`. Agents must not install it, run its privileged commands, provide
credentials, or perform the separate gateway reload. No production login or
search restoration has been verified by the development tests.

The launcher starts a separate private Python/browser process inside the exact
existing `audiobook-ops-flaresolverr` container. It uses the container's network
namespace, never the shared FlareSolverr HTTP credential API. It creates a fresh
browser and keeps that browser through login, captcha, direct index verification,
and cookie collection. It does not restart FlareSolverr or add services or ports.
The fixed in-container root supervisor creates one private directory on existing
executable tmpfs under `/dev`. Its browser child drops supplementary groups and
its user/group IDs to `flaresolverr` before browser imports. The supervisor only
handles the bounded private protocol, owned-process supervision, and cleanup.
It does not mount filesystems or change the running service. An unavailable or
unsafe executable tmpfs is a refusal before credentials.

## Historical acceptance before Docker29 correction

The earlier candidate received independent Standards and Spec **PASS** reviews.
Its historical results were **288 ordinary tests including 87 dedicated tests**,
**20 exact-image browser synthetic scenarios**, and **2 actual generated-bootstrap
startup cases PASS**. This is local engineering acceptance only, not deployment
or guaranteed live readiness. Real provider/TLS/login/captcha compatibility,
production cookie reuse, gateway reload, and search repair remain **UNVERIFIED**
and owner-gated. These results are historical, byte-identical helper evidence;
the browser and generated-bootstrap checks were not rerun for this follow-up.

The historical root-private directory correction received independent
[Standards PASS](/home/nik/.hermes/task-evidence/rutracker-session-refresh-20261104/root0700/reviews/standards.md)
and [Spec source-conformance PASS](/home/nik/.hermes/task-evidence/rutracker-session-refresh-20261104/root0700/reviews/spec.md)
reviews. The Spec review left parent execution gates open; subsequent hash-bound
parent receipts closed those historical gates: **97 dedicated tests PASS**,
**298 ordinary tests PASS**, no skips, and **3 actual privilege scenarios PASS**.
They do not close the current Docker29 acceptance gates.

The observed owner diagnostic was `owner-refresh: privacy`. A verified
incompatibility was the launcher's obsolete `0750 root:nik` requirement for
secrets. Production preflight checks root UID 0 and mode `0700`, without enforcing
GID 0; runbook installation and the corrected launcher additionally require
`root:root`. This correction honors that existing contract; it does not establish
that the mismatch was the sole cause of the observed diagnostic or that live
login is ready. That historical documentation correction was additional cycle 2, aggregate
cycle 4, leaving 3 additional cycles at that time. The current Docker29 correction
accounting above supersedes that remaining allowance.

Historical root0700 acceptance record:
[root0700/ACCEPTANCE.md](/home/nik/.hermes/task-evidence/rutracker-session-refresh-20261104/root0700/ACCEPTANCE.md).
Historical acceptance:
[earlier ACCEPTANCE.md](/home/nik/.hermes/task-evidence/rutracker-session-refresh-20261104/ACCEPTANCE.md).
The reproduction commands below remain independent of historical task directories.

## Before installation

Use a real, unrecorded terminal on the target host. Disable terminal recording,
screen sharing, agent capture, and automatic uploads. A local GUI or an
owner-managed private image viewer on that host is required. The tool stages a
login screenshot even when no captcha is present. SSH alone does not provide
that viewer. Do not upload a captcha,
screenshot, username, password, or cookie to chat. If private image access is
unavailable, abort before entering credentials.

The fixed image is
`ghcr.io/flaresolverr/flaresolverr@sha256:258523d25e4e07028c3a206f0e03ae807b26a50a201dd320f09a18464ecf86fa`.
The launcher must refuse container/image/source/driver drift, unsupported proxy
configuration, unsafe file permissions, and captured or noninteractive input.
The expected topology is the private/default PID namespace and bridge network
`audiobook-ops-backend`, with exactly the retained writable, privately propagated
`/home/nik/services/readmeabook/flaresolverr:/config` bind. The launcher compares
actual local network/PID namespace inodes against the host and rechecks container
identity before input and publication. Alternate retained roots or namespace
sharing require a new reviewed configuration; they are refused.
It does not repair these conditions. Do not relax a refusal by editing hashes,
changing flags, or selecting another container or route.

`/etc/audiobook-ops/secrets` must already be a real directory owned by
`root:root` with exactly mode `0700`; its ancestors must be root controlled,
without symlinks or group/world write permission. Keep the production installation
contract unchanged; do not chmod the secrets directory to work around a refusal.
The final secret is
`/etc/audiobook-ops/secrets/gateway-session-cookie`, root:`nik`, mode `0640`.
The launcher requires nik's primary GID to be `1000`, matching the actual Compose
gateway `user: "1000:1000"`; matching sudo metadata alone is insufficient if this
GID has drifted. Repository user configuration does not explicitly pin that GID,
so the launcher refuses a mismatch before authentication rather than publishing
an unreadable file. Existing directory/file inode and ownership checks remain.
The existing secret is not needed for authentication. A replacement preserves
the previous file privately for manual rollback.

The gateway receives the individual file at
`/run/secrets/gateway_session_cookie`, not the host secrets directory. The
privileged container runtime resolves that file mount; service UID/GID 1000
checks its `0640 root:1000` file permissions without traversing the host `0700`
directory. The unchanged gateway loader reads the flat JSON object at this
service-visible path. This does not grant nik access through the host directory.

## Install the matching files after parent review

The matching source pair currently exists on zenbook under
`/home/nik/nix-config/hosts/um790pro/docker/audiobook-ops/scripts/`. No transfer
or installation was performed. After current parent acceptance, the OWNER must transfer the matching pair
into the shown checkout on `um790pro` and verify it using the commands below.
The target checkout scripts directory must already exist; do not assume it
contains the current candidate. No remote credentials or cookie files need to enter
chat. Verify these exact source SHA256s before installation:

```text
5e28284831dfac1439129041216c70d8601e35d5c4638983448e2299b5180cbd  owner_rutracker_refresh.py
3793099c1f16d624d80b3f83373d5b825f81e9f9505da79f1f8f004591d40887  owner_rutracker_helper.py
```

After the current parent acceptance is complete, run the transfer manually from
zenbook as `nik` in a private, unrecorded terminal. These absolute source paths
are the local candidate; no agent runs this command:

```sh
/usr/bin/scp /home/nik/nix-config/hosts/um790pro/docker/audiobook-ops/scripts/owner_rutracker_refresh.py /home/nik/nix-config/hosts/um790pro/docker/audiobook-ops/scripts/owner_rutracker_helper.py nik@um790pro:/home/nik/nix-config/hosts/um790pro/docker/audiobook-ops/scripts/
```

Then, on `um790pro` in nik's private, unrecorded terminal, read back and verify
the transferred bytes. Both lines must report `OK`; stop on any mismatch:

```sh
/usr/bin/sha256sum --check <<'SHA256'
5e28284831dfac1439129041216c70d8601e35d5c4638983448e2299b5180cbd  /home/nik/nix-config/hosts/um790pro/docker/audiobook-ops/scripts/owner_rutracker_refresh.py
3793099c1f16d624d80b3f83373d5b825f81e9f9505da79f1f8f004591d40887  /home/nik/nix-config/hosts/um790pro/docker/audiobook-ops/scripts/owner_rutracker_helper.py
SHA256
```

Run these commands manually on `um790pro`, using the accepted checkout at the
literal path shown. This installs only the two reviewed scripts. It does not
deploy the bundle or reload a service.

```sh
/usr/bin/sudo /usr/bin/install -d -o root -g root -m 0700 /usr/local/libexec/audiobook-ops
/usr/bin/sudo /usr/bin/install -o root -g root -m 0700 /home/nik/nix-config/hosts/um790pro/docker/audiobook-ops/scripts/owner_rutracker_helper.py /usr/local/libexec/audiobook-ops/owner_rutracker_helper.py
/usr/bin/sudo /usr/bin/install -o root -g root -m 0700 /home/nik/nix-config/hosts/um790pro/docker/audiobook-ops/scripts/owner_rutracker_refresh.py /usr/local/libexec/audiobook-ops/owner_rutracker_refresh.py
```

Read back the installed root-private files through sudo and verify the exact
same bytes before launching. Both lines must report `OK`:

```sh
/usr/bin/sudo /usr/bin/sha256sum --check <<'SHA256'
5e28284831dfac1439129041216c70d8601e35d5c4638983448e2299b5180cbd  /usr/local/libexec/audiobook-ops/owner_rutracker_refresh.py
3793099c1f16d624d80b3f83373d5b825f81e9f9505da79f1f8f004591d40887  /usr/local/libexec/audiobook-ops/owner_rutracker_helper.py
SHA256
```

The files and their installation directory must remain root controlled. Install
the matching pair together: the launcher pins the companion bytes. No command
line parameters, environment overrides, selected scripts, arbitrary Docker
arguments, or alternative destinations are supported.

## Run from the owner's terminal

```sh
/usr/bin/sudo /usr/bin/python3 -I /usr/local/libexec/audiobook-ops/owner_rutracker_refresh.py
```

Run this as `nik` through `sudo`; a direct root shell is not the invoking-owner
boundary. Do not pipe input or output. The launcher requires the controlling
`/dev/tty` and refuses captured standard streams. Captcha, username, and password
are entered without terminal echo. They are transported over anonymous pipes,
never command line arguments or environment variables.

If a captcha is required, the tool writes a bounded PNG at a private path under
`/run/audiobook-ops-owner-session/`. Only the invoking owner can view it. Open
that local PNG in a private viewer on the target host, then answer in the
launcher's terminal. Do not open remote URLs or save upstream HTML. Confirm
private image access before entering credentials; abort if the image cannot be
read or the challenge is unclear. There is no automatic captcha solver.
The helper loads the captcha in the same rendered login document, preserving
that document's challenge fields even if another login-page visit would rotate
them.

The tool accepts authentication only after a fresh direct visit to the fixed
upstream index URL and one active canonical `logged-in-username` element matching
the entered principal. A submitted form, a cookie alone, a gateway compatibility
marker, or FlareSolverr's synthetic status `200` is insufficient. The structural
contract and real provider behavior still need owner validation; synthetic tests
cannot establish that the current live page follows that contract. Cookie
rotations are collected after the verification visit.
Only static native HTML forms with genuine HTML `INPUT` controls are supported.
The named login control must be `INPUT type=submit` with value `вход`; all
`BUTTON` controls used as the login control are refused, including buttons with
interactive link descendants. Username, password, captcha, hidden SID and redirect
must also be native inputs owned by the one canonical native form and present in
its actual `form.elements` collection. Attribute-spoofed anchors and custom
elements are unsupported. The helper validates this complete shape before
providing a screenshot or requesting credentials, again before typing, and again
before the native submit click. Page JavaScript is disabled
by an acknowledged CDP command before the first navigation and remains disabled
through login and verification. The helper's fixed trusted DOM queries and image
retry still execute. Inline event handlers and page scripts cannot mutate the
form or open another context. The form must submit POST with URL-encoded fields
in the same single window. Submit overrides, explicit control associations,
base targets, frames and embedded browsing contexts cause refusal before browser
input. A live login that needs JavaScript is unsupported; abort without entering
credentials. This restriction may prevent login on the live provider and requires
owner validation before use.

Unexpected navigation is blocked. The adapter permits only its fixed login and
index requests plus one constrained same-origin captcha resource parsed from
the form. It does not solve general anti-bot challenges. A live page requiring
unsupported scripts, CDN resources, or a different captcha structure must stop
before credentials; the owner must not bypass that refusal.

On success, publication atomically replaces the fixed cookie file. Private
browser/profile/cache/driver and PNG staging are cleaned up. A previous cookie,
if present, is retained as a root-only
`.gateway-session-cookie.rollback-<32hex>` file in the secrets directory. Never
print or attach either file's contents. Retain the backup until the separately
approved service check succeeds; rollback itself is a separate owner action.
New cookies remain in memory until publication. The atomic installer briefly
uses a private root-only `0700` directory on the destination filesystem, then
renames its complete cookie file into place and removes that directory. This
keeps the publication rename on one filesystem without exposing a temporary
cookie file to the owner group.

A root-private persistent `refresh.lock` in the fixed runtime directory serializes
the entire operation before browser startup or credential input, through
publication, cleanup and terminal closure. A concurrent invocation returns the
fixed `busy` diagnostic without starting transport or prompting for credentials.
The zero-length lock file is retained; do not delete it while a refresh may run.
It contains no session data.

WebDriver private-use action characters U+E000 through U+E0FF are unsupported in
credentials or captcha answers and are refused without normalization before
browser input. Ordinary supported text is passed literally to the native fields.

A failure before publication preserves the prior secret. A failure after atomic
rename is an **unknown publication state**: the new file may already be visible.
Do not infer that retrying is safe or overwrite a backup blindly. Inspect only
file metadata and follow the separately reviewed rollback procedure. Diagnostic
output is restricted to fixed codes; do not enable tracebacks or browser logs.

`privacy` is deliberately shared by several refusals. Other conditions supported
by the current code include missing/mismatched sudo identity or GID, nonisolated
or wrongly installed scripts, unsafe or replaced directory/file metadata,
non-tmpfs runtime storage, an unsafe runtime base or lock inode, a captured or
nonforeground controlling terminal, refusal of private image access, invalid
input characters, interruption, and helper bootstrap privilege/tmpfs checks.
Unexpected host exceptions are also sanitized to this code. These are possible
conditions, not additional diagnoses of the owner invocation. Diagnose only
through separately authorized checks; never attach secret files or logs.

The helper has bounded operation/lifetime limits. EOF, cancellation, timeout,
or cleanup failure must prevent a success claim. Do not kill shared browser or
FlareSolverr processes to clean up this operation. Temporary-file deletion does
not guarantee secure erasure, and the design cannot hide memory from root or
the same trusted UID.

## Reload and acceptance remain separate

The launcher does not recreate the gateway. Existing gateway processes or
bind-mounted file secrets can keep using the previous inode after atomic
replacement. Publication therefore does not prove the gateway loaded the cookie
or that search works.

Follow the separately owner-gated recovery section of
[PRODUCTION-RUNBOOK.md](PRODUCTION-RUNBOOK.md). That runbook currently supplies no
exact drift-guarded gateway recreation command. Establish and approve that
command against the installed reviewed bundle and current Compose inputs before
any recreation. Do not improvise a Compose invocation or restart FlareSolverr.

## Synthetic reproduction and historical development evidence

The root-private follow-up adds mandatory portable regressions in
`tests/test_owner_root_private.py`: the actual `_owner_run` construction and safe
publication seam, strict directory denials, inode replacement, cleanup and
before/after-rename outcomes. Production contract tests execute only the exact
extracted `check_root_private_directory` function body on synthetic paths, bind
it to the um790pro secrets call, and statically check runbook/Compose contracts.
Portable tests map root ownership to the test UID/GID; they are not privilege
proof. A separate inspected `tests/root_private_privilege_harness.py` requires
a user namespace mapping both 0 and 1000 plus a private PID namespace. It checks
real DAC and metadata, service denial through the host directory, the actual
gateway JSON loader through an opened file descriptor, retained old/new inode
views, rollback privacy and failures before/after replacement. This fd-opened
view is equivalent for the traversal check; it is not an actual Docker mount.

Historical root0700 evidence is under
`/home/nik/.hermes/task-evidence/rutracker-session-refresh-20261104/root0700/`.
These earlier results cover the prior launcher only; the helper is byte-identical.
The [parent dedicated receipt](/home/nik/.hermes/task-evidence/rutracker-session-refresh-20261104/root0700/parent-dedicated.receipt.json)
records exit 0 and its hash-bound log reports 97 tests PASS. The
[parent ordinary receipt](/home/nik/.hermes/task-evidence/rutracker-session-refresh-20261104/root0700/parent-ordinary.receipt.json)
records exit 0 and 298 tests PASS, with no skips. That run used a source-only
snapshot, minimal environment, nonexistent config/socket paths and an owned
PID/proc namespace with an inaccessible external process-group witness. Its
`suite_bootstrap.py` supplements only missing `TMPDIR` in explicit child
environments: the actual passing parent log records 19 additions. The earlier
sandbox count of 11, socket denials and newuidmap setup failures remain historical.

The [parent privilege receipt](/home/nik/.hermes/task-evidence/rutracker-session-refresh-20261104/root0700/parent-privilege.receipt.json)
records exit 0 with three PASS scenarios: normal publication, failure before
rename and failure after rename. Actual mapped root and service UID/GID 1000
exercise DAC denial through the host directory and the actual gateway loader
reopening the fd-visible file. This proves the synthetic fd-visible case, not
an actual Docker mount. These historical parent runs bind to the then-reviewed 80-file
[reviewed manifest](/home/nik/.hermes/task-evidence/rutracker-session-refresh-20261104/root0700/FINAL-MANIFEST.json);
The later root0700 documentation follow-up changed only this owner document;
those historical receipts do not cover the current Docker29 launcher edit.

The historical author mode/GID RED/GREEN receipts remain the primary test-first
evidence for that root-private correction. The parent also ran the frozen pre-fix launcher through the same actual
privilege harness: the
[prior-launcher receipt](/home/nik/.hermes/task-evidence/rutracker-session-refresh-20261104/root0700/parent-prior-privilege-red.receipt.json)
records the expected exit 1 at the first normal-publication assertion. This is
additional regression confirmation. No fresh browser, container-runtime, provider,
generated-bootstrap or production verification was performed.

The new `tests/test_owner_image_identity.py` exercises actual DockerTransport
admission with injected local-command responses and a deliberate stop at the
bootstrap factory. Portable raw fixtures and SHA256 validation are under
`tests/fixtures/owner-image-identity/`; the narrow production identity fields are
composed with explicitly synthetic topology/Env. They are not a full production
inspect or a new production capture. Negative controls cover substituted IDs,
wrong references, absent/mismatched Descriptor/RepoDigests, index media types,
platform mismatch, malformed/duplicate/nonfinite/oversized JSON, command failures
and image drift across rechecks. These tests require no private task history.

Prepared independent parent runners (fresh labels; no output overwrites):

```sh
/usr/bin/python3 -B /home/nik/.hermes/task-evidence/rutracker-session-refresh-20261104/docker29-identity/run_ordinary.py parent-dedicated-1 dedicated
/usr/bin/python3 -B /home/nik/.hermes/task-evidence/rutracker-session-refresh-20261104/docker29-identity/run_ordinary.py parent-ordinary-1 ordinary
```

The ordinary parent mode preserves actual discovery, including offline Docker
Compose client rendering. Both modes use a source-only scratch snapshot, private
PID/proc namespace and inaccessible external-group witness, minimal environment
and nonexistent config/socket, and supplement only a missing child TMPDIR.
They remain pending. The writer's author modes explicitly omit restricted tests.

The dedicated tests use synthetic credentials, pages, cookies, and private
fixtures. `test_owner_rutracker_integration` binds only an ephemeral IPv4 loopback
listener. The owner boundary also needs the dedicated pseudoterminal tests.
Run explicit synthetic modules in an owned PID namespace with a minimal
environment and a nonexistent config path:

```sh
cd /home/nik/nix-config/hosts/um790pro/docker/audiobook-ops
(umask 077
 test_scratch=$(/usr/bin/mktemp -d /home/nik/.hermes/cache/scratch/owner-rutracker-tests.XXXXXXXXXX) || exit 1
 trap '/usr/bin/rm -rf -- "$test_scratch"' EXIT HUP INT TERM
 # The scratch parent stays private; fixture mkdir modes assume a normal umask.
 umask 022
 env -i PATH=/usr/bin:/bin LANG=C.UTF-8 HOME="$test_scratch" TMPDIR="$test_scratch" AUDIOBOOK_OPS_CONFIG="$test_scratch/nonexistent.json" DOCKER_CONFIG="$test_scratch/nonexistent-docker-config" DOCKER_HOST="unix://$test_scratch/nonexistent.sock" PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/tests:$PWD/src" /usr/bin/unshare --user --map-current-user --pid --fork --mount-proc /usr/bin/python3 -B -m unittest -v test_owner_rutracker_helper test_owner_rutracker_refresh test_owner_rutracker_integration test_owner_root_private test_owner_image_identity
)
```

Separate privilege reproduction (synthetic scratch only; no sudo, Docker,
production mounts, credentials, provider or listener). Failure to establish the
two-ID mapping is a setup failure, not a skipped or passed test:

```sh
env -i PATH=/usr/bin:/bin LANG=C.UTF-8 HOME=/nonexistent TMPDIR=/home/nik/.hermes/cache/scratch PYTHONDONTWRITEBYTECODE=1 /usr/bin/unshare --user --map-auto --map-root-user --setgroups allow --pid --fork --mount-proc /usr/bin/python3 -I -B /home/nik/nix-config/hosts/um790pro/docker/audiobook-ops/tests/root_private_privilege_harness.py
```

Historical phase evidence: [earlier CHECKPOINT.md](/home/nik/.hermes/task-evidence/rutracker-session-refresh-20261104/CHECKPOINT.md) records
the exact slice commands,
RED/GREEN logs, socket-denial setup failure, parent-run frozen loopback receipts,
and offline pinned-browser capability receipts. Offline browser startup and
synthetic adapters are distinct from a successful real-provider authentication.
The prior exact-helper offline browser fixture passed eight synthetic scenarios,
including rotating challenges, native form submission, cookie continuity,
verification, privilege drop and cleanup. Its responses are fulfilled through a
trusted test CDP adapter; it does not establish real HTTPS/TLS or provider
compatibility. Historical frozen listener checks and independent reviews have
parent acceptance for that earlier engineering candidate only. An earlier browser setup failure remains
retained with unknown cause; a later passing run does not diagnose it.
Historical correction-1 changes the privacy boundary to static JS-disabled forms and adds
namespace/mount checks, documented install validation and a whole-operation lock.
Its hash-bound browser controls and installed-launcher/generated-bootstrap
startup fixture have final parent receipts recorded in the historical acceptance
linked above. The startup fixture exercises safe precredential EOF, rather than
claiming full authentication
through the installed launcher. Parent review and final local engineering
acceptance of the historical candidate are recorded in that historical acceptance.
They do not cover this changed launcher or establish fresh live readiness.
