# Omarchy installation

This directory owns host inputs for the first stage only: official Omarchy
Quattro ISO plus a `cidata` drive installs the base OS, owner account, LUKS,
locale, Git identity, and SSH access. Personal packages and dotfiles belong to
the later provisioner.

## x1carbon

Target facts were read from `x1carbon` over Tailscale SSH on 2026-08-24:

```text
device: /dev/nvme0n1
size:   512110190592 bytes
model:  Micron MTFDHBA512TDV
serial: 20362B0F0DBD
root:   /dev/nvme0n1p2
```

Booting official Omarchy ISO with generated `cidata.iso` **erases this entire
disk**. Before every install, boot live ISO, run this command, and compare all
four target fields with `omarchy/cidata/x1carbon.conf`:

```bash
lsblk -bdno PATH,SIZE,TYPE,MODEL,SERIAL
```

Official `cidata` schema has no pre-wipe hook or serial field. Generated config
therefore still names `/dev/nvme0n1`; live-environment check immediately before
booting installer remains mandatory. Do not proceed if another NVMe device is
present or any field differs.

Build payload from repository root while current `x1carbon` remains online.
Builder pins its existing SSH host key and refuses to continue unless live
path, size, model, and serial exactly match profile. Password prompt sets same
password for user, root, and LUKS, matching official Omarchy wizard behavior:

```bash
nix shell nixpkgs#xorriso nixpkgs#whois --command \
  scripts/omarchy-build-cidata.sh x1carbon --confirm-disk /dev/nvme0n1
```

Output lands in ignored `omarchy/output/x1carbon/`. It contains password hash
and plaintext LUKS passphrase inside JSON and ISO; keep it private and delete it
after installation:

```bash
rm -rf omarchy/output/x1carbon
```

Installation procedure:

1. Write official stable Omarchy Quattro ISO to first USB drive.
2. Write `omarchy/output/x1carbon/cidata.iso` to second drive, or expose it as a
   virtual CD-ROM with volume label `cidata`.
3. Re-check target device, size, model, and serial from live environment.
4. Boot official ISO with both media attached. Configurator is skipped; install
   wipes `/dev/nvme0n1`, creates LUKS/Btrfs, and reboots automatically.
5. Enter LUKS password at first boot. Log in locally or SSH as `nik` using one
   of public keys listed in generated `authorized_keys`.

No private SSH/GPG keys or Tailscale auth key enter `cidata`. Stock Omarchy
enables `sshd` and opens its firewall only because `authorized_keys` is present.

## Personal provisioning

After base installation and SSH access work, install selected packages and
apply user configuration from repository source machine:

```bash
scripts/omarchy-provision.sh --install-packages --install-gui --import-gpg \
  --import-syncthing --import-vless nik@192.168.1.15
```

### Required network order: VLESS before Tailscale

On a fresh host, use LAN SSH for the initial provisioning connection. Configure
and authorize Tailscale only while an already verified VLESS tunnel is active;
do not rely on Tailscale enrollment from `cidata` on a network where its control
path needs VLESS. The required order is:

1. Install the host VLESS config and start `vless-sing-box.service`.
2. Verify that the managed TUN interface exists and a non-Google HTTPS probe
   succeeds through it.
3. Keep VLESS active while running and authorizing `tailscale up`.
4. Verify that Tailscale reaches `BackendState: Running` and MagicDNS resolves its DNS name.
5. Verify the final Google-through-London routing policy.

The provisioning root phase enforces this sequence when `--import-vless` is
used. Starting with Tailscale and planning to enable VLESS afterward can leave
the host authorized but without its first usable network map.

Package installation is interactive because Omarchy requests privilege through
its normal policy. Provisioning detects the target's short hostname, includes an
optional `omarchy/packages/<hostname>.txt` manifest, keeps Bash as login/session
shell, and adds Zsh only as an interactive terminal shell. It also installs the
NixOS-equivalent `tat`, `yt`, and `yp` helpers in `~/.local/bin`; `yt` downloads
clipboard URLs to `~/Videos`, while `yp` uses `~/tmp/.tt/inbox`. The NixOS tmux
configuration and its TPM-managed plugins are installed alongside them; an existing
XDG tmux config or helper is preserved once with a `.pre-nix-config` suffix. The
`urlview` runtime is installed from the AUR when available. The Syncthing identity
import and shared topology support the Omarchy hosts listed in
`scripts/omarchy-configure-syncthing.sh`, including `x1carbon`, `zenbook`, and
`t14s`.

Third-party Omarchy shell plugins are declared in `omarchy/plugins.tsv`.
Provisioning installs every entry and applies the shared `shell.json`, including
the active OmaQuote, Timezones, wallpaper manager, and multi-monitor manager
widgets. The multi-monitor manager package is installed from the AUR and its
`hyprmoncfgd` user service is enabled for automatic profile switching. OmaQuote
receives the shared collection generated from
`dotfiles/quotes.txt` plus its managed display config; `otf-monaspace` supplies
the configured Monaspace Krypton font. Verification fails if a declared plugin
is missing or disabled, or if the OmaQuote collection, runtime settings, or font
do not match.

With `--import-vless`, provisioning selects
`secrets/vless/<hostname>.json`, validates it, installs it at
`/etc/sing-box/vless.json`, and provides `vless up|down|status`. The source host
must have `jq` and `sing-box` so validation finishes before the target is changed.
On systems using `systemd-resolved`, the VLESS unit removes sing-box's synthetic
TUN DNS registration after startup. System DNS still traverses the TUN without
making `198.19.0.2` the host resolver. Tailscale DNS remains enabled so its
native split DNS configuration resolves MagicDNS names without replacing the
system resolver for public domains.
Provisioning performs a temporary VLESS smoke test after importing the config;
`vless up` returns successfully only after the managed TUN interface appears.
The root phase keeps that verified tunnel active through the interactive
Tailscale login, then performs the final route check after Tailscale connects.
GUI provisioning uses Omarchy installers for Brave, Firefox, VS Code, and
ChatGPT; installs Bitwarden, T3 Code, and Telegram from package manifests; and
applies managed browser extensions. It also installs the Bibata cursor theme and
matches the NixOS `Bibata-Original-Ice` cursor at size 24. Re-running command is
safe.
