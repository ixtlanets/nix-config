# transcribe-media: local Hex on macOS

The Home Manager package is Darwin-only. Run Hex 3.3.0 with verified Parakeet v3 installed, then use `transcribe-media recording.m4a`. JSON and Markdown sidecars are written next to the original. Existing sidecars require `--force`; inference/validation failure preserves them. Input audio is unchanged.

- Discovers owner-local `~/Library/Application Support/hex/local-api.json` on every file. API2, loopback only, bearer token never placed on the command line or printed. No cloud, SSH fallback, model preparation/download or second app instance.
- Converts locally with ffmpeg to 16 kHz mono PCM16 WAV, transcribes sequential 120-second chunks with explicit `model=parakeet_v3&language=ru`. Temporary converted audio is removed on normal success/failure. Private source/output files stay on this Mac.
- JSON retains `modelId.predefined` and `segments` (`id`, `text`, `start`, `end`, `speakerId`). **These are coarse input-audio chunk bounds, not speech-aligned timestamps.** `timing=coarse-audio-chunks`, `speakerId=null`, and explicit false capability flags prevent invented speakers/timing claims. Markdown carries the same warning and chunk ranges.
- Hex API2 provides final raw text, no speaker diarization or word/utterance alignment. GUI vocabulary/replacements/rewrite are not applied. Stereo is downmixed; independent channels/speakers are not retained. Hard chunk boundaries can degrade words. Empty chunks fail rather than inventing text or silently dropping audio. Existing precise Spokenly sidecars are not migrated/reinterpreted.
- A per-user advisory lock serializes this helper only; direct Hex/desktop clients bypass it. A request timeout is 600 seconds per chunk; cancelling HTTP does not prove native inference stopped. The full decoded WAV uses local temporary disk proportional to duration.
- Requires the running Hex desktop API; embedded/headless startup is not implemented/tested here. Start Hex before using the helper.

## Checks

`bash tests/transcribe-media.sh` exercises the real helper + ffmpeg against a loopback API2 fixture: chunk coverage, auth/model/language, no proxy use, JSON/Markdown, no fabricated speakers, refusal/force semantics, invalid/empty/error responses, source hash preservation and sanitized failures. `bash tests/transcribe-media-config.sh` checks Darwin packaging. These fixtures do not establish real ASR quality.

2026-11-06: m1max Hex 3.3.0 API2 health/capabilities and installed verified Parakeet v3/ru were checked. Real approved Russian voice sample acceptance results are stored privately under `~/.local/state/hex-media-migration/` on m1max, with no transcript in this repository.
