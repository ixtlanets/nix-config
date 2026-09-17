# Hermes audiobook integration

These steps mutate the live general Hermes profile. They are owner-gated and
must be run only after the audiobook backend is healthy at its private Tailscale
address. The accepted v1 isolation limitation is that audiobook tools share the
existing broad profile; `trust: untrusted`, exact tool selection, and native
approval provide the mutation boundary.

Set these non-secret paths from the repository checkout:

```bash
bundle="$PWD/hosts/um790pro/docker/audiobook-ops/hermes"
profile="${HERMES_HOME:-$HOME/.hermes}"
hermes send --list telegram
owner_target='telegram:REPLACE_WITH_LISTED_CHAT_ID'
[[ "$owner_target" =~ ^telegram:-?[1-9][0-9]*(:[1-9][0-9]*)?$ ]] || { echo 'invalid Telegram owner target' >&2; exit 1; }
```

Replace the placeholder with the one owner chat printed by the list command;
do not copy a bot token or any credential into `owner_target`.

## Install

Before touching the profile, the bundle can be checked against the installed
Hermes MCP client and trust classifier with a loopback-only disposable server:

```bash
PYTHONPATH="$PWD/hosts/um790pro/docker/audiobook-ops/src" \
  ~/.hermes/hermes-agent/venv/bin/python \
  "$PWD/hosts/um790pro/docker/audiobook-ops/tests/rehearsal_hermes.py" \
  --hermes-source ~/.hermes/hermes-agent
```

Expected: 16 registered tools, 11 read-only tools without a prompt, 5 write
tools routed to the native prompt, and `live_profile_changed` is false.
The current zenbook installation requires local Hermes compatibility commit
`0a292a8303` (SDK `read_only_hint` support); an upstream equivalent is also
acceptable. The gateway restart below is what loads that code.

1. Add the private MCP and enter the production bearer only at the hidden CLI
   prompt. Accept all 16 discovered tools initially; the next step replaces the
   entry with the reviewed exact allowlist.

   ```bash
   hermes mcp add audiobook-ops --url http://100.95.213.117:8300/mcp --auth header
   ```

   Expected: the token is stored as `MCP_AUDIOBOOK_OPS_API_KEY` in the active
   profile `.env`, the server reports 16 tools, and no token appears in config or
   terminal output.

2. Merge only `mcp_servers.audiobook-ops` from `mcp/audiobook-ops.json` into
   `$profile/config.yaml`. Preserve every unrelated profile key and MCP server.
   The reviewed entry must remain `trust: untrusted`,
   `strict_redirect_headers: true`, and contain the exact include list.

   ```bash
   hermes config set --force mcp_servers.audiobook-ops "$(jq -c '.mcp_servers[\"audiobook-ops\"]' "$bundle/mcp/audiobook-ops.json")"
   ```

3. Install the repo-managed skill directories and poller without modifying
   unrelated skills:

   ```bash
   test ! -e "$profile/skills/audiobooks" && test ! -e "$profile/skills/audiobook-admin"
   install -d -m 700 "$profile/skills/audiobooks/scripts" "$profile/skills/audiobook-admin" "$profile/scripts" "$profile/state"
   install -m 600 "$bundle/skills/audiobooks/SKILL.md" "$profile/skills/audiobooks/SKILL.md"
   install -m 700 "$bundle/skills/audiobooks/scripts/origin.py" "$profile/skills/audiobooks/scripts/origin.py"
   install -m 600 "$bundle/skills/audiobook-admin/SKILL.md" "$profile/skills/audiobook-admin/SKILL.md"
   install -m 700 "$bundle/scripts/audiobook_notifications.py" "$profile/scripts/audiobook_notifications.py"
   jq --arg origin "$owner_target" '.allowed_origins = [$origin]' \
     "$bundle/config/notifications.example.json" > "$profile/audiobook-notifications.json"
   chmod 600 "$profile/audiobook-notifications.json"
   ```

4. Restart and probe the profile:

   ```bash
   hermes gateway restart
   hermes mcp test audiobook-ops
   hermes mcp list
   ```

   Expected: the probe succeeds through `100.95.213.117`, and only the 16
   allowlisted audiobook tools are enabled. The backend remains bound only to
   the private path.

5. Create one silent no-agent polling job:

   ```bash
   hermes cron create '*/2 * * * *' --name audiobook-notifications --no-agent --script audiobook_notifications.py --workdir "$profile" --deliver "$owner_target"
   hermes cron list
   ```

   Expected: exactly one enabled `audiobook-notifications` job is listed. Empty
   polls produce no message; durable outcomes are sent by the script to their
   allowlisted originating conversation.

## Approval verification

In a fresh Telegram conversation, ask Hermes in Russian to search the library
and create an acquisition plan. `library_search`, `release_search`, inspection,
status, audit, and plan calls must not show a mutation approval. Ask it to apply
the reviewed plan, then stop before the native prompt and inspect that the prompt
names `audiobook-ops.request_apply`. Accept or deny only as the owner directs.
Repeat the prompt check for one applicable cancel/retry or metadata undo during
acceptance; no write-capable tool may execute before acceptance.

## Rollback

Identify the job ID with `hermes cron list`, then remove only this integration:

```bash
hermes cron remove JOB_ID
hermes mcp remove audiobook-ops
rm -r "$profile/skills/audiobooks" "$profile/skills/audiobook-admin"
rm "$profile/scripts/audiobook_notifications.py" "$profile/audiobook-notifications.json"
hermes gateway restart
```

Keep `$profile/state/audiobook-notifications.cursor` for audit/reinstall, or
remove it only after durable backend events have been reconciled. Expected:
Hermes starts normally, lists no `audiobook-ops` MCP, and all unrelated profile
configuration and cron jobs remain unchanged.
