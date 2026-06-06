# Nix Config

This repository contains a Nix flake configuration for managing multiple machines running NixOS, macOS (via Nix-Darwin), and standalone Home Manager setups (e.g., WSL).

## Supported Machines

- **NixOS**: Linux machines with full NixOS installations.
- **macOS**: Apple Macs using Nix-Darwin.
- **WSL/Home Manager**: Ubuntu WSL2 instances with Home Manager for user environments.

## Prerequisites

- Install Nix: Follow the [official guide](https://nixos.org/download.html).
- Enable flakes: Add `experimental-features = nix-command flakes` to `/etc/nix/nix.conf` (or `~/.config/nix/nix.conf`).
- Clone this repo: `git clone <this-repo> && cd nix-config`

## Usage

### NixOS (Using nixos-anywhere)

For installing or updating NixOS on a machine remotely or locally.

1. **Prepare the target machine**: Ensure SSH access or local access. For remote installs, have SSH keys set up.

2. **Run nixos-anywhere**:

   ```bash
   nix run github:nix-community/nixos-anywhere -- --flake .#<host> <user>@<ip>
   ```

   Replace `<host>` with your NixOS host (e.g., `x1carbon`), and `<user>@<ip>` with the target SSH details.

3. **Post-install**: On the machine, switch to the config:

   ```bash
   sudo nixos-rebuild switch --flake .#<host>
   ```

Available NixOS hosts: `x1carbon`, `x1extreme`, `x13`, `um960pro`, `zenbook`, `matebook`, `desktop`.

### Windows Setup

Run from Windows PowerShell. On a fresh Windows install where Ubuntu WSL does not exist yet, clone this repository somewhere on Windows first, such as `C:\Users\nik\src\nix-config`, and run the setup script from that checkout:

```powershell
cd C:\Users\nik\src\nix-config
powershell.exe -ExecutionPolicy Bypass -File .\scripts\windows-setup.ps1
```

If Ubuntu WSL already exists and the repository is checked out there, run it from the WSL UNC path instead:

```powershell
cd \\wsl.localhost\Ubuntu\home\nik\nix-config
powershell.exe -ExecutionPolicy Bypass -File .\scripts\windows-setup.ps1
```

The setup scripts are idempotent and safe to rerun. Use `-Only Apps`, `-Only Yt`, `-Only Fonts`, `-Only Cursors`, `-Only Wsl`, or `-Only VoiceTyping` to run one area. Use `-SkipInstall` to report missing install targets without acquiring or installing packages, fonts, or cursors; configuration sync steps such as the `yt` shim/config and Handy custom words may still run.

The Windows `yt` helper is installed as `%LOCALAPPDATA%\Microsoft\WinGet\Links\yt.cmd`. It reads a URL from the Windows clipboard, clears the clipboard, and downloads with `yt-dlp` into `%USERPROFILE%\Videos`. Windows setup installs `yt-dlp.yt-dlp.nightly` through winget.

Some steps need administrator rights. On Windows 11 24H2+, enable Sudo for Windows in Settings, then use the recommended `forceNewWindow` mode:

```powershell
sudo config --enable forceNewWindow
```

WSL setup uses:

```powershell
wsl --install -d Ubuntu --no-launch
```

It may require a reboot. The script reports this but does not reboot automatically. This WSL setup can create Ubuntu after running from a Windows checkout, so the `\\wsl.localhost\Ubuntu` path is only required when using an existing WSL checkout.

### WSL (Home Manager on Fresh Ubuntu WSL2)

For setting up a fresh Ubuntu WSL2 instance with Home Manager.

1. **Install Ubuntu WSL2**: On Windows, install WSL2 and Ubuntu from the Microsoft Store or via `wsl --install -d Ubuntu`.

2. **Initial Setup in WSL**:
   - Open Ubuntu terminal.
   - Update and install basics:

     ```bash
     sudo apt update && sudo apt upgrade -y
     sudo apt install -y curl git
     ```

3. **Install Nix**:

   ```bash
   curl -L https://nixos.org/nix/install | sh
   . ~/.nix-profile/etc/profile.d/nix.sh
   ```

4. **Enable flakes**:

   ```bash
   mkdir -p ~/.config/nix
   echo "experimental-features = nix-command flakes" >> ~/.config/nix/nix.conf
   ```

5. **Clone and setup Home Manager**:

   ```bash
   git clone <this-repo> ~/nix-config
   cd ~/nix-config
   nix run home-manager/master -- init --switch
   ```

6. **Switch to config**:

   ```bash
   home-manager switch --flake .#nik@wsl
   ```

This sets up your user environment with dotfiles, packages, and services.

### macOS (Nix-Darwin)

For Macs managed by Nix-Darwin. Example host: `m3max`.

1. **Install Nix**: Install Nix with the official multi-user installer:

   ```bash
   sh <(curl -L https://nixos.org/nix/install) --daemon
   ```

   Restart the shell after installation, or load Nix manually:

   ```bash
   . /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
   ```

2. **Enable flakes**: Ensure Nix has flakes enabled:

   ```bash
   mkdir -p ~/.config/nix
   printf 'experimental-features = nix-command flakes\n' >> ~/.config/nix/nix.conf
   ```

3. **Clone the repo**:

   ```bash
   git clone git@github.com:ixtlanets/nix-config.git ~/nix-config
   cd ~/nix-config
   ```

4. **Unlock secrets**: Required for Syncthing identities and other encrypted material:

   ```bash
   git-crypt unlock
   ```

   If this fails, import the required GPG key first.

5. **Bootstrap or switch Nix-Darwin**:

   On a fresh Mac without `darwin-rebuild` yet, run:

   ```bash
   nix run github:lnl7/nix-darwin -- switch --flake .#m3max
   ```

   After Nix-Darwin is installed, use:

   ```bash
   darwin-rebuild switch --flake .#m3max
   ```

6. **Verify the active host**:

   ```bash
   scutil --get HostName
   nix eval .#darwinConfigurations.m3max.config.networking.hostName
   ```

   Expected Nix output: `"m3max"`.

7. **Syncthing on `m3max`**:

   `m3max` has a pre-generated Syncthing identity stored in:

   ```text
   secrets/syncthing/m3max/cert.pem
   secrets/syncthing/m3max/key.pem
   ```

   Device ID:

   ```text
   NQ2KNGN-4ZT42Z3-RGRWOO6-53NLUNM-AQFI25Z-3CED6MP-K2UVMB4-6RW74QV
   ```

   Do not reuse this identity on another machine while `m3max` is running Syncthing.

Available Darwin hosts: `m1max`, `m3max`, `i9mac`.

To add another Apple Silicon Mac, copy `hosts/m3max`, rename host-specific paths and hostname, add a matching `darwinConfigurations.<host>` entry in `flake.nix`, then add a unique Syncthing identity under `secrets/syncthing/<host>/` if Syncthing should be enabled.

## Development

- **Dev shell**: `nix develop` for tools like `home-manager`, `git`, `nix`.
- **Build package**: `nix build .#<package>` (e.g., `.#marker-pdf`).
- **Format code**: `nix fmt` (uses nixfmt-rfc-style).
- **Checks**: `nix flake check` for linting and formatting.

## Adding a New Host

- For NixOS: Add to `flake.nix` under `nixosConfigurations`, create `hosts/<host>/nixos/configuration.nix` and `hosts/<host>/home-manager/home.nix`.
- For Darwin: Add to `darwinConfigurations`.
- For Home Manager: Add to `homeConfigurations`.

## Secrets

Secrets are managed with git-crypt. To unlock: `git-crypt unlock` (requires GPG key).

Encrypted paths currently include `secrets/gpg/**`, `secrets/ssh/**`, `secrets/syncthing/**`,
`secrets/vless/**`, and `secrets/proxy/**`.

## Contributing

- Commit messages: Concise, present tense (e.g., `[x1carbon] add package`).
- PRs: Include summary, affected hosts, and test commands.
