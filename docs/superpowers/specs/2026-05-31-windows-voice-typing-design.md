# Windows Voice Typing Setup Design

## Goal

Add a Windows-native setup path for Handy voice typing custom words. The Windows setup should use PowerShell and `winget`, while keeping `dotfiles/voice-typing/words.json` as the single source of truth shared with the existing macOS and Voxtype configuration.

This design covers Handy setup only. Throne migration is intentionally left for a later, separate script.

## Entry Points

Create two scripts under `scripts/`:

- `windows-setup.ps1`: the main Windows host setup entrypoint.
- `windows-voice-typing.ps1`: the Handy-specific setup and synchronization script.

`windows-setup.ps1` should be thin orchestration. It should verify that it is running on Windows, resolve the repository root from its own path, and call `windows-voice-typing.ps1`.

Expected commands:

```powershell
.\scripts\windows-setup.ps1
.\scripts\windows-setup.ps1 -SkipInstall
.\scripts\windows-setup.ps1 -Force
```

`windows-setup.ps1` should pass common flags through to specialized scripts.

## Handy Setup

`windows-voice-typing.ps1` should manage Handy only.

Responsibilities:

- Verify that it is running on Windows.
- Resolve the repository root from its own path unless an explicit root is passed for testing.
- Check for `winget` unless `-SkipInstall` is set.
- Install or upgrade Handy with package id `cjpais.Handy` via `winget`.
- Read `dotfiles/voice-typing/words.json`.
- Validate that every value in `voxtypeReplacements` is present in `handyCustomWords`.
- Update `%APPDATA%\com.pais.handy\settings_store.json`.

The Windows Handy settings file has the same shape as the macOS settings file:

```json
{
  "settings": {
    "custom_words": []
  }
}
```

The script should only replace `settings.custom_words`. It should preserve every other existing setting.

## Data Flow

1. `windows-setup.ps1` locates the repository root.
2. `windows-setup.ps1` calls `windows-voice-typing.ps1`.
3. `windows-voice-typing.ps1` loads `dotfiles/voice-typing/words.json`.
4. The script validates the shared word invariant.
5. The script writes `handyCustomWords` into Handy's Windows settings file.

This keeps the source of truth in the repository and avoids duplicating words in a separate Windows-only file.

## Safety

Before modifying `settings_store.json`, `windows-voice-typing.ps1` should create a timestamped backup in the same directory, for example:

```text
settings_store.json.backup-20260531-143000
```

If `settings_store.json` does not exist, the script should create the Handy settings directory and start from:

```json
{"settings":{}}
```

If `handy.exe` is running, the default behavior should be to skip the settings write and tell the user to close Handy or rerun with `-Force`. With `-Force`, the script may write while Handy is running.

## Error Handling

The scripts should fail clearly when:

- They are not running on Windows.
- `winget` is missing and installation was requested.
- `dotfiles/voice-typing/words.json` is missing or invalid JSON.
- The shared word invariant fails.
- Handy settings cannot be read or written.

The scripts should not require administrator privileges for normal operation because Handy installs into the user profile and settings live under `%APPDATA%`.

## Validation

Implementation should be checked with:

- PowerShell parser validation for both scripts.
- A dry run or skip-install run that reads the shared words and reports the target Handy settings path.
- A real run on the Windows host after closing Handy.
- A JSON check confirming that `settings.custom_words` matches `handyCustomWords`.

No `sudo nixos-rebuild` command is needed for this work.
