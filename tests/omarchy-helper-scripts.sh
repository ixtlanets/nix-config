#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
helpers_dir="$repo_root/dotfiles/omarchy/bin"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

mock_bin="$tmp_dir/bin"
mkdir -p "$mock_bin" "$tmp_dir/project.name"

for helper in kbd-backlight tat yt yp; do
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

cat > "$mock_bin/brightnessctl" <<'MOCK'
#!/usr/bin/env bash
case "$*" in
  '--list --machine-readable')
    printf '%s\n' 'intel_backlight,backlight,50,50%,100' 'tpacpi::kbd_backlight,leds,0,0%,2'
    ;;
  '--device=tpacpi::kbd_backlight get')
    printf '%s\n' "$KBD_CURRENT"
    ;;
  '--device=tpacpi::kbd_backlight max')
    printf '%s\n' "$KBD_MAXIMUM"
    ;;
  '--device=tpacpi::kbd_backlight set '*)
    printf '%s\n' "$*" >> "$BRIGHTNESS_CALL"
    ;;
  '--device=tpacpi::kbd_backlight --save set '*)
    printf '%s\n' "$*" >> "$BRIGHTNESS_CALL"
    ;;
  *)
    printf 'Unexpected brightnessctl arguments: %s\n' "$*" >&2
    exit 1
    ;;
esac
MOCK

cat > "$mock_bin/omarchy-hyprland-session-locked" <<'MOCK'
#!/usr/bin/env bash
[[ ${KBD_LOCKED:-false} == true ]]
MOCK

cat > "$mock_bin/sleep" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$SLEEP_CALL"
MOCK

cat > "$mock_bin/yt-dlp" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$YT_DLP_CALLS"
MOCK

chmod +x \
  "$mock_bin/brightnessctl" \
  "$mock_bin/omarchy-hyprland-session-locked" \
  "$mock_bin/sleep" \
  "$mock_bin/tmux" \
  "$mock_bin/wl-copy" \
  "$mock_bin/wl-paste" \
  "$mock_bin/yt-dlp"

for state in 'toggle 0 2 2' 'toggle 1 2 0' 'up 1 2 2' 'up 2 2 2' 'down 1 2 0' 'down 0 2 0'; do
  read -r action current maximum target <<< "$state"
  brightness_call="$tmp_dir/brightness-$action-$current.call"
  PATH="$mock_bin:$PATH" \
    KBD_CURRENT="$current" \
    KBD_MAXIMUM="$maximum" \
    KBD_LOCKED=false \
    BRIGHTNESS_CALL="$brightness_call" \
    "$helpers_dir/kbd-backlight" "$action"
  expected_brightness_call="$tmp_dir/brightness-$action-$current.expected"
  printf '%s\n' \
    "--device=tpacpi::kbd_backlight set $target" \
    "--device=tpacpi::kbd_backlight --save set $target" > "$expected_brightness_call"
  cmp -s "$expected_brightness_call" "$brightness_call" || {
    printf 'kbd-backlight %s did not change %s to %s\n' "$action" "$current" "$target" >&2
    exit 1
  }
done

locked_brightness_call="$tmp_dir/brightness-locked.call"
sleep_call="$tmp_dir/sleep.call"
PATH="$mock_bin:$PATH" \
  KBD_CURRENT=0 \
  KBD_MAXIMUM=2 \
  KBD_LOCKED=true \
  BRIGHTNESS_CALL="$locked_brightness_call" \
  SLEEP_CALL="$sleep_call" \
  "$helpers_dir/kbd-backlight" toggle
grep -Fxq '0.2' "$sleep_call" || {
  printf 'kbd-backlight did not wait for the lock-screen restore\n' >&2
  exit 1
}
locked_brightness_expected="$tmp_dir/brightness-locked.expected"
printf '%s\n' \
  '--device=tpacpi::kbd_backlight set 2' \
  '--device=tpacpi::kbd_backlight --save set 2' > "$locked_brightness_expected"
cmp -s "$locked_brightness_expected" "$locked_brightness_call" || {
  printf 'kbd-backlight did not toggle after the lock-screen restore\n' >&2
  exit 1
}

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

printf 'PASS: Omarchy helpers preserve kbd-backlight, tat, yt, and yp behavior\n'
