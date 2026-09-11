#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
script="$repo_root/dotfiles/omarchy/bin/transcribe-media"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

[[ -x "$script" ]] || {
  printf 'Missing executable helper: %s\n' "$script" >&2
  exit 1
}

mock_bin="$tmp_dir/bin"
mkdir -p "$mock_bin" "$tmp_dir/media"
media="$tmp_dir/media/meeting.m4a"
printf 'placeholder audio\n' > "$media"

cat > "$mock_bin/spokenly" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$@" > "$SPOKENLY_CALLS"
case "${SPOKENLY_MODE:-valid}" in
  valid)
    printf '%s\n' '{"modelId":{"predefined":"test-model"},"segments":[{"id":"segment-1","text":"Hello world.","start":0,"end":1.42,"speakerId":"speaker-0"}]}'
    ;;
  invalid)
    printf '%s\n' 'not json'
    ;;
  *)
    printf 'Unexpected SPOKENLY_MODE: %s\n' "$SPOKENLY_MODE" >&2
    exit 2
    ;;
esac
MOCK
chmod +x "$mock_bin/spokenly"

calls="$tmp_dir/spokenly.calls"
PATH="$mock_bin:$PATH" SPOKENLY_CALLS="$calls" "$script" "$media"

expected_calls="$tmp_dir/spokenly.expected"
printf '%s\n' \
  transcribe \
  "$media" \
  --format \
  json \
  --speakers > "$expected_calls"
cmp -s "$expected_calls" "$calls" || {
  printf 'transcribe-media passed unexpected arguments to spokenly\n' >&2
  diff -u "$expected_calls" "$calls" >&2 || true
  exit 1
}

json_output="$tmp_dir/media/meeting.transcript.json"
markdown_output="$tmp_dir/media/meeting.transcript.md"
jq -e '(.modelId.predefined == "test-model") and (.segments | length == 1)' "$json_output" >/dev/null
[[ -f "$markdown_output" ]]
grep -Fxq '# meeting' "$markdown_output"
grep -Fxq '[00:00:00] Speaker 1: Hello world.' "$markdown_output"

if PATH="$mock_bin:$PATH" SPOKENLY_CALLS="$calls" "$script" "$media"; then
  printf 'transcribe-media overwrote existing output without --force\n' >&2
  exit 1
fi

rm -f "$json_output" "$markdown_output"
if PATH="$mock_bin:$PATH" SPOKENLY_CALLS="$calls" SPOKENLY_MODE=invalid "$script" "$media"; then
  printf 'transcribe-media accepted malformed JSON from spokenly\n' >&2
  exit 1
fi
[[ ! -e "$json_output" && ! -e "$markdown_output" ]] || {
  printf 'transcribe-media left output after malformed JSON\n' >&2
  exit 1
}

unsupported="$tmp_dir/media/unsupported.aiff"
printf 'placeholder audio\n' > "$unsupported"
rm -f "$calls"
if PATH="$mock_bin:$PATH" SPOKENLY_CALLS="$calls" "$script" "$unsupported"; then
  printf 'transcribe-media accepted an unsupported file format\n' >&2
  exit 1
fi
[[ ! -e "$calls" ]] || {
  printf 'transcribe-media called Spokenly for an unsupported file format\n' >&2
  exit 1
}

printf 'PASS: transcribe-media writes validated JSON and Markdown sidecars\n'
