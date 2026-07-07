# Repository Guidelines

## Important Notes
- Do not run `sudo nixos-rebuild build --flake .#zenbook` or similar commands yourself. Always ask the user to execute them.
- Keep `install.sh` in sync with changes to helper scripts (vpn, vless, tat, etc.) from the Nix configs; replicate behavior updates there for CachyOS/Arch installs.
- Voice typing words are shared in `dotfiles/voice-typing/words.json` and loaded by `modules/home-manager/voice-typing-words.nix`. When updating `voxtypeReplacements`, keep `handyCustomWords` in sync; every replacement value must be present in Handy custom words, and the Nix assertion should remain strict with no exceptions.
- `london` is an Ubuntu VPS, not a NixOS host. Keep reproducible Ubuntu-managed service bundles under `hosts/london/ubuntu/<service>/`. Do not add `london` to `nixosConfigurations` unless explicitly requested.
- For Vaultwarden on `london`, keep Docker/Caddy/systemd/deploy assets under `hosts/london/ubuntu/vaultwarden/` and secrets under `secrets/vaultwarden/london/`.
- Be careful with the existing London proxy setup (`microsocks`, Tailscale Serve, and related proxy docs/secrets). Do not change or restart it unless the task explicitly requires it.

## Project Structure & Module Organization
- Root: Nix flake (`flake.nix`, `flake.lock`), overlays (`overlays/`), custom packages (`pkgs/`).
- Hosts: per‑machine configs under `hosts/<host>/{nixos,home-manager}/` (e.g., `hosts/x1carbon/nixos/configuration.nix`).
- Modules: reusable modules in `modules/{nixos,home-manager}/*.nix`.
- Dotfiles: auxiliary configs in `dotfiles/` consumed by modules.
- Secrets: encrypted material in `secrets/{gpg,ssh}/` (managed by git‑crypt).

## Architecture Overview
- Flake outputs: provides `packages`, `devShells`, `overlays`, `nixosModules`, `homeManagerModules`, `nixosConfigurations`, `darwinConfigurations`, and `homeConfigurations` from `flake.nix`.
- Hosts compose reusable modules plus hardware profiles; `specialArgs`/`extraSpecialArgs` pass `outputs`, `dpi`, and `ghostty` into modules for consistent theming and settings.
- Overlays: `additions` exposes `pkgs/` as first‑class attributes; `unstable-packages` exposes `pkgs.unstable`; custom tweaks live in `overlays/default.nix` under `modifications`.
- Packages: lightweight derivations in `pkgs/*.nix` consumed via overlay or as `.#<attr>` (e.g., `.#marker-pdf`).
- Home‑Manager: per‑user configs under `hosts/<host>/home-manager/` import shared modules from `modules/home-manager`.

## Build, Test, and Development Commands
- Enter dev shell: `nix develop` (adds `nix`, `home-manager`, `git`).
- Build a package: `nix build .#marker-pdf` (see `pkgs/`).
- NixOS build/switch: `sudo nixos-rebuild switch --flake .#x1carbon`.
- Darwin switch: `darwin-rebuild switch --flake .#m1max`.
- Home‑manager only: `home-manager switch --flake .#nik@wsl`.

## Coding Style & Naming Conventions
- Language: Nix. Indent 2 spaces; trailing commas ok; prefer attribute‑set style and `lib.mk*` helpers.
- Files: lower‑case with hyphens (e.g., `linux-desktop.nix`, `waybar.nix`).
- Modules: keep options and imports grouped; prefer alphabetical ordering within sets.
- Packages: add `.nix` under `pkgs/` and expose via `pkgs/default.nix` using `pkgs.callPackage`.
- Formatting: use `nixpkgs-fmt` or `nixfmt-rfc-style` (available via HM config). Example: `nixpkgs-fmt .`.

## Testing Guidelines
- Eval flake and build targets you touched: `nix build .#<attr>`.
- For host edits, do a dry build first: `sudo nixos-rebuild build --flake .#<host>` or `home-manager switch --flake .#<user>@<host> --dry-run`.
- If you add or rename files referenced by the flake, stage them with git before running `nixos-rebuild` or `home-manager switch`, otherwise the flake source may not include them.
- If adding modules, ensure they import cleanly by referencing them from a host before switching.

## Commit & Pull Request Guidelines
- Messages: concise, present tense. Optionally scope with host/module, e.g., `[x1carbon] scale Steam` or `home-manager: add ghostty`.
- PRs: include a summary, affected hosts/modules, commands used to validate (build/switch), and any screenshots/logs for UI‑visible changes.
- Keep changes focused; separate unrelated module and host changes.

## Security & Configuration Tips
- Do not commit plaintext secrets. `secrets/gpg/**` and `secrets/ssh/**` are encrypted via git‑crypt.
- To work with secrets, ensure GPG access and run `git-crypt unlock`.
