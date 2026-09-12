# Hermes audiobook automation service baseline

**Observed:** 2026-09-12 21:27 UTC (2026-09-13 00:27 Europe/Moscow)

**Scope:** read-only inventory for GitHub issue #4 before implementing or
deploying `audiobook-ops`. No container, unit, timer, file, credential,
Transmission task, publication, or Audiobookshelf item was changed. No secret
value was read or included in this document.

## Repository state

- Branch: `master`.
- HEAD: `c2693eece2e6032ed41ad5197843680cce298239`.
- `git status --porcelain=v1`: empty before scaffold work.

## UM790Pro Compose baseline

The deployed Compose file matches the repository copy byte-for-byte:

```text
sha256 20110553b27ae6295f6a287f06a884bb5e4d1f3a1021749021feafb01b45c3bc
```

Its secret-safe JSON rendering has SHA-256
`ec9348fef5036eb12d99178b49445f2e19943ec8285778096111a513fc854869`.
The rendering contains the five expected services and these exact image
references/runtime image IDs:

| Container | Configured image | Runtime image ID | State |
|---|---|---|---|
| `readmeabook` | `localhost/readmeabook:1.2.2-transmission-tracker-fix-1` | `sha256:a4d0de6fcb7a8672f8f8ea322736e7e4b34869100d025cb8d0ccd72cc71b510f` | running, healthy |
| `readmeabook-flaresolverr` | `ghcr.io/flaresolverr/flaresolverr@sha256:258523d25e4e07028c3a206f0e03ae807b26a50a201dd320f09a18464ecf86fa` | same digest | running, healthy |
| `readmeabook-rutracker-gateway` | `ghcr.io/flaresolverr/flaresolverr@sha256:258523d25e4e07028c3a206f0e03ae807b26a50a201dd320f09a18464ecf86fa` | same digest | running, healthy |
| `readmeabook-prowlarr` | `lscr.io/linuxserver/prowlarr@sha256:c7502a75b021d964481c129c84590b9cbc40f83aadd4e553f173871bc0deaa3c` | same digest | running, healthy |
| `readmeabook-transmission` | `lscr.io/linuxserver/transmission@sha256:fc3b07f2f571c0392edd4dd386067138a0fe157d2158a976769409a292e43936` | same digest | running; no container healthcheck |

The render binds the current ReadMeABook UI only to
`100.95.213.117:3030`, Prowlarr only to `127.0.0.1:9696`, and publishes no
host port for Transmission, FlareSolverr, or the RuTracker gateway. It uses
the retained roots below:

```text
/home/nik/services/readmeabook/prowlarr      -> Prowlarr /config
/home/nik/services/readmeabook/transmission -> Transmission /config
/home/nik/services/readmeabook/downloads    -> /downloads
/home/nik/services/readmeabook/flaresolverr -> FlareSolverr /config
```

The deployed RuTracker gateway also matches the repository copy at SHA-256
`08d663560f39940e8b4e7fb5f9041f9115f075d0503ffba9f6bf02a1fa341ac4`.

## Units and activity boundary

All five timers are disabled and inactive; no matching timer is scheduled:

```text
readmeabook-publisher.timer      disabled, inactive
readmeabook-torrent-policy.timer disabled, inactive
readmeabook-cleanup.timer        disabled, inactive
readmeabook-backup.timer         disabled, inactive
readmeabook-healthcheck.timer    disabled, inactive
```

Each corresponding oneshot service is inactive/dead with its last result
`success` and exit status `0`. The publisher ledger has an empty `pending`
object. The Transmission queue contains four completed, error-free torrents;
each has `percentDone=1.0` and status `6` (seeding). The `incomplete` download
directory is empty. Therefore no acquisition or publication was active at the
observation boundary.

| Transmission ID | Infohash | State | Name |
|---|---|---|---|
| 1 | `1a5eb6b90595e74de2d12f5366e733795de29071` | seeding, 100%, error 0 | Борис Конофальский — Глубокий рейд. Книга 4. КЛЯКСЫ |
| 2 | `00d415a3230944772364297e9efe58c02dcf62d0` | seeding, 100%, error 0 | Борис Конофальский — 5. Глубокий рейд |
| 3 | `968f2a2ecce7b55d086b29ffe0280ec36d957cc4` | seeding, 100%, error 0 | Трудно быть богом |
| 4 | `b8d2e0055953035c243a8890a2fce30e2abd06c8` | seeding, 100%, error 0 | Кроткая (фантастический рассказ).m4b |

The retained download and staging trees contain the completed legacy data for
these records and must not be interpreted as active work. UM790Pro had
`170588236` KiB (about 162.7 GiB) available under the state filesystem, above
the 100 GiB local reserve.

## Publication history and exact Audiobookshelf mapping

The immutable ledger contains three active `published` records and one
`unpublished` historical record. All active records map to exact items in the
single accessible Audiobookshelf book library
`47e465fa-78b1-44bb-a697-98fc02bd8596`.

| Ledger request ID | Final relative path | Infohash | Manifest ID | ABS item ID | ABS media ID |
|---|---|---|---|---|---|
| `0cc1a664-29a5-4542-a483-aaebae3bf0b3` | `Борис Конофальский/Глубокий рейд manualrutracker6557008` | `00d415a3230944772364297e9efe58c02dcf62d0` | `cea49b9f4712998f8836141a19274eff2bedd35d58e277698523546696cb2c18` | `9bff45e8-f58c-4e45-a57b-b62a0bcc3da8` | `b9bfb5b6-238b-4416-b207-9ffcc728b9f3` |
| `83920e0c-1504-4882-8aba-3c25460e20dc` | `Конофальский Борис/Кляксы manualrutracker6887881` | `1a5eb6b90595e74de2d12f5366e733795de29071` | `4f873106c7c2300ab3c3303733b6707e44b3a052e2e656960ec59832aa105edc` | `81ed85d9-dd3c-438f-9ee2-68791860c3b5` | `2ab86705-68eb-4a29-a28f-4782968063b5` |
| `8c229675-3f6b-43ba-a7af-e71232936f2e` | `Аркадий и Борис Стругацкие/Трудно быть богом manualrutracker6600274` | `968f2a2ecce7b55d086b29ffe0280ec36d957cc4` | `d7606142b9217526c4e83dbbbf915902d0364fe70ba2191e15f75d7adb0af5f5` | `15e62639-a3e7-4690-8e7c-f7aab388946a` | `55078069-e76a-40a2-a91f-adf520c9729b` |

The exact ledger facts associated with those rows are, in table order:

```text
files=32 bytes=543823726 published_at_epoch=1789203518 abs_confirmed_at_epoch=1789205128
files=41 bytes=572920033 published_at_epoch=1789198527 abs_confirmed_at_epoch=1789201943
files=1  bytes=208351921 published_at_epoch=1789205162 abs_confirmed_at_epoch=1789206773
```

The historical tombstone is request
`53bcd578-67e5-4a49-9913-85ef625f2cf8`, infohash
`b8d2e0055953035c243a8890a2fce30e2abd06c8`, manifest
`fb8e8481664c74c96645cbab03bb1d47c2e69931e64f4cfafcee5bc540a62499`,
and former final path
`Федор Михайлович Достоевский/Кроткая manualrutracker6214434`. Its ledger
status is `unpublished`, and that path is absent from the Moscow managed tree.

## Moscow and Audiobookshelf baseline

- Container: `audiobookshelf`, running with restart policy `unless-stopped`.
- Service status: initialized, language `ru`, server version `2.36.0`.
- Configured image: `nix-config/audiobookshelf:2.36.0-arm64-14a6492c`.
- Runtime image ID:
  `sha256:28b665b047a1e02474fad2bc703bd2a7489e4e72295f67e431c17f07c63320b3`.
- Accessible book libraries: one, named `Audiobooks`, exact library ID shown
  above, with 191 book items.
- Managed mount: `/media/disk1/media/ReadMeABook` -> `/readmeabook:ro`.
- Managed root: directory, mode `2775`, owner `nik:nik`.
- Incoming root: `/media/disk1/media/.readmeabook-incoming`, empty, mode `0700`,
  owner `nik:nik`.
- Both roots are on device ID `2049`, permitting atomic promotion.
- Available space: `278961108` KiB (about 266.0 GiB), above the 200 GiB remote
  reserve.

The inventory used the container's own SQLite driver in read-only mode to map
paths to item IDs, avoiding any API credential or write endpoint. The physical
managed path remains unchanged; the display-name rename to `Загруженные книги`
is deferred to the accepted service cutover.
