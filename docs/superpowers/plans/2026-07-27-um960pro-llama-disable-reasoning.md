# UM960Pro Llama Disable Reasoning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Disable Qwen hidden reasoning on the UM960Pro llama.cpp endpoint used by Odysseus.

**Architecture:** Add llama.cpp's server-wide reasoning controls to the existing standalone Compose command, mirroring the working `m1max` configuration. Recreate only `llama-server`, then verify visible completions and native tool calls through its OpenAI-compatible API.

**Tech Stack:** Docker Compose, llama.cpp server, Qwen3.6 GGUF, OpenAI-compatible HTTP API.

---

### Task 1: Add Reasoning Controls

**Files:**
- Modify: `hosts/um960pro/docker/llama-server/docker-compose.yml:12-33`

- [ ] **Step 1: Verify the current configuration lacks the controls**

Run from `hosts/um960pro/docker/llama-server`:

```bash
docker compose config --format json | python3 -c 'import json,sys; c=json.load(sys.stdin)["services"]["llama-server"]["command"]; assert c[c.index("--reasoning") + 1] == "off"; assert json.loads(c[c.index("--chat-template-kwargs") + 1])["enable_thinking"] is False'
```

Expected: FAIL because `--reasoning` is absent.

- [ ] **Step 2: Add both llama.cpp controls**

Append these entries after `--metrics` in the service command:

```yaml
      - --reasoning
      - "off"
      - --chat-template-kwargs
      - '{"enable_thinking": false}'
```

- [ ] **Step 3: Verify the resolved command**

Run the Step 1 command again.

Expected: exit code 0.

- [ ] **Step 4: Validate Compose and the diff**

Run:

```bash
docker compose config --quiet
git -C /home/nik/nix-config diff --check -- hosts/um960pro/docker/llama-server/docker-compose.yml
git -C /home/nik/nix-config diff -- hosts/um960pro/docker/llama-server/docker-compose.yml
```

Expected: Compose and whitespace checks exit 0; the diff contains only the four command entries.

Commit is intentionally omitted because the user did not request one.

### Task 2: Recreate And Verify Llama Server

**Files:**
- Runtime only: Docker container `llama-server`

- [ ] **Step 1: Recreate only the model server**

Run from `hosts/um960pro/docker/llama-server`:

```bash
docker compose up -d --force-recreate llama-server
```

Expected: `llama-server` is recreated and starts loading the existing cached model.

- [ ] **Step 2: Wait for API readiness**

Run:

```bash
curl --silent --show-error --fail --retry 60 --retry-delay 2 --retry-connrefused --max-time 10 http://127.0.0.1:8080/health
```

Expected: a successful health response after model loading completes.

- [ ] **Step 3: Verify the effective container command**

Run:

```bash
docker inspect --format '{{json .Config.Cmd}}' llama-server
```

Expected: the JSON command contains `"--reasoning","off"` and `"--chat-template-kwargs","{\"enable_thinking\": false}"`.

- [ ] **Step 4: Verify model identity and context size**

Run:

```bash
curl --silent --show-error --fail --max-time 10 http://127.0.0.1:8080/props \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["model_alias"] == "unsloth/Qwen3.6-35B-A3B-MTP-GGUF:UD-Q4_K_M"; assert d["default_generation_settings"]["n_ctx"] == 16384; print(d["model_alias"], d["default_generation_settings"]["n_ctx"])'
```

Expected: the Qwen model ID and `16384` are printed.

- [ ] **Step 5: Verify a visible non-reasoning completion**

Run:

```bash
curl --silent --show-error --fail http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"unsloth/Qwen3.6-35B-A3B-MTP-GGUF:UD-Q4_K_M","messages":[{"role":"user","content":"Reply with exactly: ready"}],"temperature":0.2,"max_tokens":64}' \
  | python3 -c 'import json,sys; m=json.load(sys.stdin)["choices"][0]["message"]; assert m.get("content", "").strip() == "ready"; assert not m.get("reasoning_content"); print(m["content"].strip())'
```

Expected: visible content is printed and `reasoning_content` is absent or empty.

- [ ] **Step 6: Verify native tool calling remains functional**

Run:

```bash
curl --silent --show-error --fail http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"unsloth/Qwen3.6-35B-A3B-MTP-GGUF:UD-Q4_K_M","messages":[{"role":"user","content":"Call the ping function with value ready."}],"temperature":0.2,"max_tokens":128,"tools":[{"type":"function","function":{"name":"ping","description":"Call this function with the requested value.","parameters":{"type":"object","properties":{"value":{"type":"string"}},"required":["value"]}}}],"tool_choice":"required"}' \
  | python3 -c 'import json,sys; m=json.load(sys.stdin)["choices"][0]["message"]; calls=m.get("tool_calls") or []; assert calls and calls[0]["function"]["name"] == "ping"; assert not m.get("reasoning_content"); print(calls[0]["function"])'
```

Expected: a native `ping` tool call is printed with no reasoning content.

### Task 3: Verify Odysseus Connectivity

**Files:**
- Runtime only: existing Odysseus deployment

- [ ] **Step 1: Confirm Odysseus still reaches its local endpoint**

Run from the Odysseus repository:

```bash
docker compose exec -T odysseus python -c "import json,urllib.request; data=json.load(urllib.request.urlopen('http://host.docker.internal:8081/v1/models', timeout=10)); assert data.get('data'); print([m['id'] for m in data['data']])"
```

Expected: the Qwen model ID is listed.

- [ ] **Step 2: Verify completion proxying through port 8081**

Run from the Odysseus repository:

```bash
curl --silent --show-error --fail http://127.0.0.1:8081/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"unsloth/Qwen3.6-35B-A3B-MTP-GGUF:UD-Q4_K_M","messages":[{"role":"user","content":"Reply with exactly: odysseus-ready"}],"temperature":0.2,"max_tokens":64}' \
  | python3 -c 'import json,sys; m=json.load(sys.stdin)["choices"][0]["message"]; assert m.get("content", "").strip() == "odysseus-ready"; assert not m.get("reasoning_content"); print(m["content"].strip())'
```

Expected: `odysseus-ready` is printed with no reasoning content.

- [ ] **Step 3: Check runtime state**

Run:

```bash
docker inspect --format 'created={{.Created}} restart={{.RestartCount}} status={{.State.Status}}' llama-server
docker compose ps --all
```

Expected: `llama-server` is running with restart count 0; the Odysseus stack remains running and SearXNG remains healthy.

- [ ] **Step 4: Manual chat verification**

In the existing Odysseus agent chat, repeat the email-sender request and then send a simple factual correction.

Expected: the agent emits visible replies and tool calls without a prolonged thinking stream.
