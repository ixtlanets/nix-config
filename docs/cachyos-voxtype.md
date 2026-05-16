# CachyOS Voxtype Setup

Manual Voxtype setup for the CachyOS GNOME Wayland machine. This is intentionally separate from the NixOS `pkgs/voxtype.nix` override because this host is not managed through NixOS and uses an upstream binary installed into `/usr/local/bin`.

## Goal

- GNOME Wayland.
- No Voxtype OSD.
- Parakeet v3 transcription.
- Push-to-talk on Right Alt.
- Paste output.
- Small post-processing fix for common Russian `ё` cases emitted as `<unk>`.

## Binary

The active binary is manually installed at:

```bash
/usr/local/bin/voxtype
```

Current target:

```text
voxtype 0.7.1
```

Asset used:

```text
voxtype-0.7.1-linux-x86_64-onnx-avx2
```

Reason: the CPU is an AMD Ryzen 9 6900HS. It supports AVX2 but not AVX-512, so the ONNX AVX2 build is the correct Parakeet-capable binary.

## Install Or Upgrade

Download and verify the upstream release asset:

```bash
mkdir -p /tmp/opencode/voxtype-0.7.1
gh release download v0.7.1 \
  --repo peteonrails/voxtype \
  --pattern 'voxtype-0.7.1-linux-x86_64-onnx-avx2' \
  --pattern 'SHA256SUMS' \
  --clobber \
  --dir /tmp/opencode/voxtype-0.7.1

cd /tmp/opencode/voxtype-0.7.1
sha256sum --check --ignore-missing SHA256SUMS
chmod +x voxtype-0.7.1-linux-x86_64-onnx-avx2
./voxtype-0.7.1-linux-x86_64-onnx-avx2 --version
```

Install it:

```bash
sudo install -Dm755 \
  /tmp/opencode/voxtype-0.7.1/voxtype-0.7.1-linux-x86_64-onnx-avx2 \
  /usr/local/bin/voxtype
```

This manual binary install does not install the full package-managed set of Voxtype variants. Because of that, `voxtype setup onnx --status` can still report that no ONNX variants are installed. That is expected for this setup; `voxtype setup check` and the service logs are the useful validation points.

## Config

Main config:

```bash
~/.config/voxtype/config.toml
```

Relevant sections:

```toml
engine = "parakeet"
state_file = "auto"

[hotkey]
key = "RIGHTALT"
enabled = true

[audio]
device = "default"
sample_rate = 16000
max_duration_secs = 60

[audio.feedback]
enabled = true
theme = "subtle"
volume = 0.5

[output]
mode = "paste"
paste_keys = "ctrl+shift+v"
restore_clipboard = true

[output.post_process]
command = "~/.config/voxtype/fix-russian-unk.pl"
timeout_ms = 1000

[output.notification]
on_transcription = true

[status]
icon_theme = "nerd-font"

[osd]
enabled = false

[parakeet]
model = "parakeet-tdt-0.6b-v3"
```

Keep `device = "default"`. This lets PipeWire/GNOME route Voxtype to whichever input device is currently selected, including external microphones.

Audio feedback is enabled as a practical start-recording cue. Speak after the start sound rather than immediately after physically pressing Right Alt; this avoids losing the beginning of an utterance while the audio source is opening.

## Russian `<unk>` Fix

Parakeet v3 supports Russian, but the local `vocab.txt` includes `<unk>` and does not appear to include `ё`. In practice, common words such as `всё` and `ещё` can be transcribed as `Вс<unk>` and `Ещ<unk>`.

Do not globally replace `<unk>` with `ё`. Keep the post-processor constrained to common forms.

Script path:

```bash
~/.config/voxtype/fix-russian-unk.pl
```

Current script:

```perl
#!/usr/bin/env perl
use strict;
use warnings;
use utf8;
use open ':std', ':encoding(UTF-8)';

my $text = do { local $/; <STDIN> };

my %forms = (
  'Вс' => 'Всё',
  'вс' => 'всё',
  'Ещ' => 'Ещё',
  'ещ' => 'ещё',
  'Е'  => 'Её',
  'е'  => 'её',
  'Мо' => 'Моё',
  'мо' => 'моё',
  'Св' => 'Своё',
  'св' => 'своё',
  'Тв' => 'Твоё',
  'тв' => 'твоё',
);

for my $prefix (sort { length($b) <=> length($a) } keys %forms) {
  my $replacement = $forms{$prefix};
  $text =~ s/(?<!\p{L})\Q$prefix\E<unk>(?!\p{L})/$replacement/g;
}

print $text;
```

Make it executable:

```bash
chmod +x ~/.config/voxtype/fix-russian-unk.pl
```

Quick test:

```bash
printf '%s\n' 'Вс<unk> работает. Ещ<unk> тест. Это <unk> неизвестно.' \
  | ~/.config/voxtype/fix-russian-unk.pl
```

Expected output:

```text
Всё работает. Ещё тест. Это <unk> неизвестно.
```

## Service

Install and enable the user service:

```bash
voxtype setup systemd
```

Operational commands:

```bash
systemctl --user status voxtype.service --no-pager
systemctl --user restart voxtype.service
journalctl --user -u voxtype.service -f
```

## Validation

Run:

```bash
voxtype --version
voxtype setup check
voxtype status --format json
```

Expected service log lines:

```text
Post-processing enabled: command="~/.config/voxtype/fix-russian-unk.pl", timeout=1000ms
Loading transcription model: parakeet-tdt-0.6b-v3
Parakeet Tdt model loaded
Listening for hotkey: RIGHTALT (hold to record, release to transcribe)
Listening for KEY_RIGHTALT
```

Expected status when idle:

```json
{"alt":"idle","class":"idle","tooltip":"Voxtype ready - hold hotkey to record"}
```

## Known Limitations

- This is a manual `/usr/local/bin` install, not an AUR-managed or Nix-managed package.
- `voxtype setup onnx --status` may not understand this single-binary manual install.
- Parakeet v3 has known Cyrillic/Russian quirks and no language hint control in this path.
- The post-process script intentionally fixes only known frequent `<unk>` forms.
- OSD is disabled. GNOME Wayland is not a good target for the current layer-shell OSD frontends.
