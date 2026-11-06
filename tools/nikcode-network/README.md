# Nik Code subscription source

Reviewed source snapshot from `zenbook:~/.local/share/nikcode-network` as of
2026-11-06. The live workspace remains at that path; committing this directory
does not deploy it or change running clients.

- `src/worker.js` renders profiles and authenticates subscription fetch tokens.
- `scripts/manage.py` reads encrypted state from pass and manages the Worker.
- `scripts/t14s_client.py` is the installed t14s subscription adapter source.
- `test/` covers the renderer and the secret-binding projection.

Secrets, private state, exported profiles, QR codes and certificate archives stay
outside Git. The catalog remains in `pass nikcode.xyz/config/service-state` on
zenbook. Never put its decrypted JSON into this directory.

From this directory:

```sh
node --test test/worker.test.js
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s test -p 'test_*.py'
```

Only deploy from a reviewed workspace with the current pass state. `publish`
updates code while preserving bindings; `deploy` has broader infrastructure
effects. See [the operational runbook](../../docs/nikcode-network.md).

The t14s DNS guard and bounded policy installer are maintained separately under
[`scripts/t14s-vpn-dns.py`](../../scripts/t14s-vpn-dns.py) and
[`scripts/t14s-public-ipv4.py`](../../scripts/t14s-public-ipv4.py) at repository root.
Do not rerun the one-off installer against an already accepted backup directory.
