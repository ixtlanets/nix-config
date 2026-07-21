#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
filter="$repo_root/modules/home-manager/handy-settings.jq"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_json_equal() {
  local name="$1"
  local expected="$2"
  local actual="$3"
  local expected_sorted="$tmp_dir/$name.expected.sorted.json"
  local actual_sorted="$tmp_dir/$name.actual.sorted.json"

  jq -S . "$expected" > "$expected_sorted"
  jq -S . "$actual" > "$actual_sorted"
  if ! diff -u "$expected_sorted" "$actual_sorted"; then
    fail "$name did not produce the exact expected document"
  fi
}

run_filter() {
  local input="$1"
  local custom_words="$2"
  local output="$3"

  jq --slurp --slurpfile customWords "$custom_words" -f "$filter" \
    "$input" > "$output"
}

assert_filter_fails() {
  local name="$1"
  local input="$2"
  local custom_words="$3"
  local expected_error="$4"
  local output="$tmp_dir/$name.out.json"
  local stderr="$tmp_dir/$name.stderr"

  if jq --slurp --slurpfile customWords "$custom_words" -f "$filter" \
    "$input" > "$output" 2> "$stderr"; then
    fail "$name unexpectedly succeeded"
  fi
  if [[ -s "$output" ]]; then
    fail "$name produced a merged result despite failing validation"
  fi
  if [[ "$(< "$stderr")" != *"$expected_error"* ]]; then
    printf 'Expected error containing: %s\nActual stderr:\n' "$expected_error" >&2
    sed 's/^/  /' "$stderr" >&2
    fail "$name returned the wrong diagnostic"
  fi
}

cat > "$tmp_dir/custom-words.json" <<'JSON'
["NixOS", "Handy"]
JSON

cat > "$tmp_dir/existing.json" <<'JSON'
{
  "format_version": 3,
  "installation": {
    "id": "root-sentinel",
    "flags": ["keep", {"nested": true}]
  },
  "api_keys": {
    "openai": "keep-root-api-key"
  },
  "settings": {
    "selected_model": "keep-this-model",
    "selected_microphone": "keep-this-microphone",
    "overlay_style": "live",
    "provider": {
      "name": "custom-provider",
      "api_key": "keep-provider-api-key",
      "config": {
        "base_url": "https://provider.invalid/v1",
        "retries": 4
      }
    },
    "unknown_setting": {
      "nested": {
        "values": [1, false, null]
      }
    },
    "keyboard_implementation": "legacy",
    "push_to_talk": false,
    "paste_method": "legacy",
    "autostart_enabled": true,
    "update_checks_enabled": true,
    "custom_words": ["replace-me"],
    "bindings": {
      "transcribe": {
        "id": "existing-id",
        "name": "Existing name",
        "description": "Existing description",
        "default_binding": "existing-default",
        "current_binding": "f6",
        "metadata": {
          "source": "user",
          "nested": [1, 2, 3]
        }
      },
      "cancel": {
        "id": "cancel",
        "current_binding": "escape",
        "metadata": {"keep": true}
      }
    }
  }
}
JSON

cat > "$tmp_dir/existing.expected.json" <<'JSON'
{
  "format_version": 3,
  "installation": {
    "id": "root-sentinel",
    "flags": ["keep", {"nested": true}]
  },
  "api_keys": {
    "openai": "keep-root-api-key"
  },
  "settings": {
    "selected_model": "keep-this-model",
    "selected_microphone": "keep-this-microphone",
    "overlay_style": "live",
    "provider": {
      "name": "custom-provider",
      "api_key": "keep-provider-api-key",
      "config": {
        "base_url": "https://provider.invalid/v1",
        "retries": 4
      }
    },
    "unknown_setting": {
      "nested": {
        "values": [1, false, null]
      }
    },
    "keyboard_implementation": "handy_keys",
    "push_to_talk": true,
    "paste_method": "ctrl_shift_v",
    "autostart_enabled": false,
    "update_checks_enabled": false,
    "custom_words": ["NixOS", "Handy"],
    "bindings": {
      "transcribe": {
        "id": "existing-id",
        "name": "Existing name",
        "description": "Existing description",
        "default_binding": "existing-default",
        "current_binding": "alt_right",
        "metadata": {
          "source": "user",
          "nested": [1, 2, 3]
        }
      },
      "cancel": {
        "id": "cancel",
        "current_binding": "escape",
        "metadata": {"keep": true}
      }
    }
  }
}
JSON

run_filter "$tmp_dir/existing.json" "$tmp_dir/custom-words.json" \
  "$tmp_dir/existing.out.json"
assert_json_equal existing "$tmp_dir/existing.expected.json" \
  "$tmp_dir/existing.out.json"

cat > "$tmp_dir/partial-binding.json" <<'JSON'
{
  "settings": {
    "bindings": {
      "transcribe": {
        "name": "Only existing metadata",
        "plugin_metadata": {"keep": "all"}
      }
    }
  }
}
JSON

cat > "$tmp_dir/partial-binding.expected.json" <<'JSON'
{
  "settings": {
    "bindings": {
      "transcribe": {
        "name": "Only existing metadata",
        "plugin_metadata": {"keep": "all"},
        "current_binding": "alt_right"
      }
    },
    "keyboard_implementation": "handy_keys",
    "push_to_talk": true,
    "paste_method": "ctrl_shift_v",
    "autostart_enabled": false,
    "update_checks_enabled": false,
    "custom_words": ["NixOS", "Handy"]
  }
}
JSON

run_filter "$tmp_dir/partial-binding.json" "$tmp_dir/custom-words.json" \
  "$tmp_dir/partial-binding.out.json"
assert_json_equal partial-binding "$tmp_dir/partial-binding.expected.json" \
  "$tmp_dir/partial-binding.out.json"

cat > "$tmp_dir/missing-binding.json" <<'JSON'
{"settings": {}}
JSON

cat > "$tmp_dir/seeded-binding.expected.json" <<'JSON'
{
  "settings": {
    "bindings": {
      "transcribe": {
        "id": "transcribe",
        "name": "Transcribe",
        "description": "Converts your speech into text.",
        "default_binding": "ctrl+space",
        "current_binding": "alt_right"
      }
    },
    "keyboard_implementation": "handy_keys",
    "push_to_talk": true,
    "paste_method": "ctrl_shift_v",
    "autostart_enabled": false,
    "update_checks_enabled": false,
    "custom_words": ["NixOS", "Handy"]
  }
}
JSON

run_filter "$tmp_dir/missing-binding.json" "$tmp_dir/custom-words.json" \
  "$tmp_dir/missing-binding.out.json"
assert_json_equal missing-binding "$tmp_dir/seeded-binding.expected.json" \
  "$tmp_dir/missing-binding.out.json"

cat > "$tmp_dir/null-binding.json" <<'JSON'
{"settings": {"bindings": {"transcribe": null}}}
JSON

run_filter "$tmp_dir/null-binding.json" "$tmp_dir/custom-words.json" \
  "$tmp_dir/null-binding.out.json"
assert_json_equal null-binding "$tmp_dir/seeded-binding.expected.json" \
  "$tmp_dir/null-binding.out.json"

: > "$tmp_dir/empty-input.json"
assert_filter_fails empty-input "$tmp_dir/empty-input.json" \
  "$tmp_dir/custom-words.json" "expected exactly one input document"

cat > "$tmp_dir/two-documents.json" <<'JSON'
{"settings": {}}
{"settings": {}}
JSON
assert_filter_fails two-documents "$tmp_dir/two-documents.json" \
  "$tmp_dir/custom-words.json" "expected exactly one input document"

printf '%s\n' '42' > "$tmp_dir/scalar-root.json"
assert_filter_fails scalar-root "$tmp_dir/scalar-root.json" \
  "$tmp_dir/custom-words.json" "input document must be an object"

printf '%s\n' '[]' > "$tmp_dir/array-root.json"
assert_filter_fails array-root "$tmp_dir/array-root.json" \
  "$tmp_dir/custom-words.json" "input document must be an object"

cat > "$tmp_dir/invalid-settings.json" <<'JSON'
{"settings": false}
JSON
assert_filter_fails invalid-settings "$tmp_dir/invalid-settings.json" \
  "$tmp_dir/custom-words.json" ".settings must be an object or null"

cat > "$tmp_dir/invalid-bindings.json" <<'JSON'
{"settings": {"bindings": false}}
JSON
assert_filter_fails invalid-bindings "$tmp_dir/invalid-bindings.json" \
  "$tmp_dir/custom-words.json" ".settings.bindings must be an object or null"

cat > "$tmp_dir/invalid-transcribe.json" <<'JSON'
{"settings": {"bindings": {"transcribe": false}}}
JSON
assert_filter_fails invalid-transcribe "$tmp_dir/invalid-transcribe.json" \
  "$tmp_dir/custom-words.json" ".settings.bindings.transcribe must be an object or null"

cat > "$tmp_dir/invalid-custom-words.json" <<'JSON'
{"not": "an array"}
JSON
assert_filter_fails invalid-custom-words "$tmp_dir/missing-binding.json" \
  "$tmp_dir/invalid-custom-words.json" "customWords must be an array"
