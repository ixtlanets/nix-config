#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
helpers_dir="$repo_root/dotfiles/omarchy/bin"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

mock_bin="$tmp_dir/bin"
mkdir -p "$mock_bin" "$tmp_dir/project.name"

for helper in tat yt yp; do
  [[ -x "$helpers_dir/$helper" ]] || {
    printf 'Missing executable Omarchy helper: %s\n' "$helper" >&2
    exit 1
  }
done

cat > "$mock_bin/tmux" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$TMUX_CALLS"
MOCK

cat > "$mock_bin/wl-paste" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' 'https://example.test/video'
MOCK

cat > "$mock_bin/wl-copy" <<'MOCK'
#!/usr/bin/env bash
cat > "$CLIPBOARD_CONTENTS"
MOCK

cat > "$mock_bin/yt-dlp" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$YT_DLP_CALLS"
MOCK

chmod +x "$mock_bin/tmux" "$mock_bin/wl-paste" "$mock_bin/wl-copy" "$mock_bin/yt-dlp"

tmux_calls="$tmp_dir/tmux.calls"
(
  cd "$tmp_dir/project.name"
  env -u TMUX PATH="$mock_bin:$PATH" TMUX_CALLS="$tmux_calls" "$helpers_dir/tat"
)
grep -Fxq 'new-session -As project-name' "$tmux_calls"

for helper in yt yp; do
  helper_home="$tmp_dir/$helper-home"
  clipboard_contents="$tmp_dir/$helper.clipboard"
  yt_dlp_calls="$tmp_dir/$helper.yt-dlp.calls"
  mkdir -p "$helper_home"

  if [[ "$helper" == yt ]]; then
    config_home="$helper_home/.config"
    env -u XDG_CONFIG_HOME \
      HOME="$helper_home" \
      PATH="$mock_bin:$PATH" \
      WAYLAND_DISPLAY=wayland-1 \
      CLIPBOARD_CONTENTS="$clipboard_contents" \
      YT_DLP_CALLS="$yt_dlp_calls" \
      "$helpers_dir/$helper"
  else
    config_home="$helper_home/custom-config"
    HOME="$helper_home" \
      XDG_CONFIG_HOME="$config_home" \
      PATH="$mock_bin:$PATH" \
      WAYLAND_DISPLAY=wayland-1 \
      CLIPBOARD_CONTENTS="$clipboard_contents" \
      YT_DLP_CALLS="$yt_dlp_calls" \
      "$helpers_dir/$helper"
  fi

  [[ ! -s "$clipboard_contents" ]] || {
    printf '%s did not clear the clipboard\n' "$helper" >&2
    exit 1
  }
  if [[ "$helper" == yt ]]; then
    output="$helper_home/Videos/%(title)s.%(ext)s"
    [[ -d "$helper_home/Videos" ]]
  else
    output="$helper_home/tmp/.tt/inbox/%(title)s.%(ext)s"
    [[ -d "$helper_home/tmp/.tt/inbox" ]]
  fi
  expected_calls="$tmp_dir/$helper.yt-dlp.expected"
  printf '%s\n' \
    --config-location \
    "$config_home/yt-dlp/config" \
    --output \
    "$output" \
    'https://example.test/video' > "$expected_calls"
  cmp -s "$expected_calls" "$yt_dlp_calls" || {
    printf '%s passed unexpected arguments to yt-dlp\n' "$helper" >&2
    diff -u "$expected_calls" "$yt_dlp_calls" >&2 || true
    exit 1
  }
done

printf 'PASS: Omarchy helpers preserve tat, yt, and yp behavior\n'
