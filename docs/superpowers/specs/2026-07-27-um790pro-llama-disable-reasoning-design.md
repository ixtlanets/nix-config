# UM790Pro Llama Reasoning Control Design

## Goal

Disable hidden reasoning for the Qwen llama.cpp endpoint used exclusively by
Odysseus, prioritizing reliable tool calls, visible answers, and lower latency.

## Current State

- `hosts/um790pro/docker/llama-server/docker-compose.yml` runs
  `unsloth/Qwen3.6-35B-A3B-MTP-GGUF:UD-Q4_K_M` with llama.cpp on host port 8080.
- The server defaults to `--reasoning auto`; the Qwen template therefore opens
  a `<think>` block for each completion.
- Odysseus reaches the endpoint through the host's existing port-8081 path.
- Observed failures include a 353-second repetitive reasoning stream and a
  390-second reasoning-only completion with no visible answer.
- The same model on `m1max` already runs successfully with reasoning disabled.

## Design

Add both supported llama.cpp controls to the UM790Pro Compose command:

```yaml
      - --reasoning
      - "off"
      - --chat-template-kwargs
      - '{"enable_thinking": false}'
```

`--reasoning off` disables llama.cpp reasoning mode. The template kwarg makes
the Qwen chat template emit an immediately closed thinking section and proceed
directly to visible content or a tool call. Using both mirrors the existing
`m1max` configuration and avoids relying on auto-detection behavior.

No model, context-size, GPU, speculative-decoding, cache, network, or logging
settings change.

## Runtime Application

Validate the Compose file, then recreate only the `llama-server` service. Do
not rebuild or switch the NixOS host configuration because this service is
managed by the standalone Compose file.

## Verification

1. Confirm the recreated container command contains both reasoning controls.
2. Confirm `/props` responds and reports the same model and 16K context.
3. Send a direct OpenAI-compatible request and verify it returns visible content
   without a non-empty reasoning field.
4. Send a tool-enabled request and verify the model emits a native tool call.
5. Retry the Odysseus email workflow and confirm lower latency and no extended
   thinking stream.

## Rollback

Remove the four added command entries and recreate `llama-server`. All existing
model data remains in the `hf-cache` volume.

## Out Of Scope

- Per-request adaptive reasoning in Odysseus.
- Odysseus attachment-tool registration and reasoning-only fallback fixes.
- Sampling, temperature, or maximum-output-token changes.
