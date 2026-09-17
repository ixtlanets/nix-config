# Alternatives to ReadMeABook for Russian audiobooks

Date: 2026-09-12

## Decision

Pilot **Shelfmark** alongside the current ReadMeABook installation. It is the
best fit for Russian audiobooks because its `Manual` search mode sends the
user's free-form query directly to Prowlarr and opens the release browser. A
request such as `Вадим Панов Анклавы` therefore does not have to exist first in
Audible, Google Books, Open Library, or Hardcover.

Shelfmark should initially be a Russian-discovery and request front end, not a
replacement for the production publisher. It can use the existing Prowlarr,
RuTracker and Transmission services on UM790Pro, download into a separate
local staging directory, and invoke a new guarded publisher that transfers the
result over SSH to Moscow. Audiobookshelf and Absorb remain unchanged.

Do **not** replace ReadMeABook with Shelfarr for this purpose. Shelfarr is a
more polished metadata-first automation system, but its request flow starts
from a work found through Hardcover, Google Books, or Open Library. That is a
broader catalogue than ReadMeABook's Audible-only discovery, but it retains the
same structural failure mode for Russian books missing or poorly indexed in
those catalogues.

## Why Shelfmark wins

Shelfmark explicitly supports `search_by=manual`. Its documentation says that
manual search opens the release browser after an explicit submit rather than
running a metadata search. The implementation forwards that query to the
Prowlarr release source and uses the audiobook category (`3030`) by default;
an expanded search can retry without the category restriction. This is the
only mature candidate inspected that combines:

- a ready web UI for raw tracker-first searches;
- Prowlarr and audiobook-aware result handling;
- Transmission support, including a distinct audiobook label and download
  directory;
- user/request modes and an administrator request queue;
- audiobook extraction, renaming/organization, and multi-file-aware custom
  post-processing scripts;
- optional metadata discovery through Google Books, Open Library, and
  Hardcover when those catalogues do contain the book.

Primary sources: [Shelfmark repository](https://github.com/calibrain/shelfmark),
[manual-search URL behaviour](https://github.com/calibrain/shelfmark/blob/1b17fe179abdef8fe2733efecc4f13a07a7f8d57/docs/url-search-parameters.md),
[Prowlarr configuration](https://github.com/calibrain/shelfmark/blob/1b17fe179abdef8fe2733efecc4f13a07a7f8d57/docs/environment-variables.md#prowlarr),
[Transmission configuration](https://github.com/calibrain/shelfmark/blob/1b17fe179abdef8fe2733efecc4f13a07a7f8d57/docs/environment-variables.md#download-clients),
[custom-script contract](https://github.com/calibrain/shelfmark/blob/1b17fe179abdef8fe2733efecc4f13a07a7f8d57/docs/custom-scripts.md), and
[request modes](https://github.com/calibrain/shelfmark/blob/1b17fe179abdef8fe2733efecc4f13a07a7f8d57/docs/users-and-requests.md).
The inspected revision is `1b17fe179abdef8fe2733efecc4f13a07a7f8d57`;
the latest inspected release is
[v1.3.15](https://github.com/calibrain/shelfmark/releases/tag/v1.3.15).

### Shelfmark manual query versus Shelfarr metadata-first discovery

| Concern | Shelfmark | Shelfarr |
| --- | --- | --- |
| Entry point | Either metadata search or raw `Manual` query | A metadata work selected from a provider |
| Query reaching RuTracker | User's submitted Cyrillic text is sent to Prowlarr | Prowlarr search follows selection of a metadata result |
| Book absent from Western catalogues | Still searchable and downloadable | No ready request path was found |
| Metadata quality | Good when a provider matches; manual results may need correction | Usually better structured when a work is found |
| Existing Prowlarr and Transmission | Both supported | Both supported |
| Fit for `Вадим Панов` / `Анклавы` | Strong: tracker-first escape hatch | Uncertain: still gated by catalogue coverage |

Shelfarr's README documents discovery through Hardcover, Google Books and
Open Library, acquisition through Prowlarr/Jackett/Newznab, Transmission,
renaming/organization, and Audiobookshelf integration. Its application code,
however, builds requests around a metadata `work_id`; no supported raw
Prowlarr-query request screen was found. See the
[Shelfarr repository](https://github.com/Pedro-Revez-Silva/shelfarr),
[metadata service](https://github.com/Pedro-Revez-Silva/shelfarr/blob/e6f3071650e6dd1060c6ddbd33e52207c76f2e92/app/services/metadata_service.rb), and
[custom acquisition provider interface](https://github.com/Pedro-Revez-Silva/shelfarr/blob/e6f3071650e6dd1060c6ddbd33e52207c76f2e92/docs/custom-acquisition-providers.md).
The inspected Shelfarr revision is
`e6f3071650e6dd1060c6ddbd33e52207c76f2e92`, corresponding to its
[2026-09-10 release](https://github.com/Pedro-Revez-Silva/shelfarr/releases/tag/v2026.09.10.1).

## Deployment fit for UM790Pro and Moscow

The split-host boundary is the main integration constraint:

```text
Shelfmark on UM790Pro
  -> existing local Prowlarr -> RuTracker through the VLESS path
  -> existing local Transmission
  -> UM790Pro staging directory
  -> guarded SSH publisher
  -> /media/disk1/media/ReadMeABook (or a sibling root) on Moscow
  -> existing Audiobookshelf scan
  -> Absorb
```

Shelfmark's remote path mappings solve differing **container/download-client**
paths, but they do not copy a completed book to another host. Its destination
must be visible to the Shelfmark container. For this deployment the safe design
is therefore:

1. Run Shelfmark in the same repo-managed bundle/network environment as the
   existing UM790Pro services. Use the same host/VLESS egress arrangement that
   is already proven for Prowlarr and RuTracker.
2. Give it a distinct Transmission label and a distinct staging root so the
   current ReadMeABook publisher cannot mistake a Shelfmark download for a
   ReadMeABook job.
3. Add a Shelfmark-specific publisher, or generalize the existing publisher
   around a source-independent manifest. Preserve forced SSH commands, host-key
   pinning, atomic incoming-to-final rename, ledger/idempotency checks, and
   explicit Audiobookshelf scan.
4. Use Shelfmark's JSON custom-script payload as the hand-off contract. It is
   designed to carry richer context for multi-file audiobooks, but the script
   should enqueue publication rather than perform an unguarded remote copy.

No change is required in Absorb. Audiobookshelf remains the system of record;
once the publisher puts a supported audiobook under a folder scanned by the
existing library, it is transparent to clients. Shelfmark's documented ABS
feature is principally a library link, so the existing publisher-triggered
scan remains important.

## Other candidates

### Librarr (JeremiahM37)

This is the strongest runner-up. It has a direct audiobook search tab, forwards
free-form searches to Prowlarr using audiobook category `3030`, supports
Transmission, maintains a Wanted list with quality profiles, organizes files
as `{Author}/{Title}`, and has explicit Audiobookshelf scan settings. Its
README and source also show a generic `query + " audiobook"` fallback.

The drawback is product maturity and metadata handling: it is a young project,
and a direct Prowlarr result can enter the pipeline with the full torrent name
as the title and no normalized author. The Wanted flow, where title and author
are supplied explicitly, is safer. It is worth a second pilot if Shelfmark's
manual-result metadata proves too awkward, but not the first production choice.

Sources: [Librarr repository and deployment documentation](https://github.com/JeremiahM37/librarr),
[Prowlarr search implementation](https://github.com/JeremiahM37/librarr/blob/612fc2845f1fd5ddca072759d9f2d907cbd3a3af/internal/search/prowlarr.go), and
[release v1.3.0](https://github.com/JeremiahM37/librarr/releases/tag/v1.3.0).

### LazyLibrarian

LazyLibrarian supports audiobook wanted items, Torznab feeds (therefore a
Prowlarr endpoint), Transmission, and metadata from services such as
OpenLibrary and Google Books. It is capable, but discovery remains
metadata-first and its broader ebook-oriented workflow adds complexity without
providing Shelfmark's clean raw-query escape hatch. It is not recommended for
this Russian-first use case. Source: [upstream project](https://gitlab.com/LazyLibrarian/LazyLibrarian).

### Readarr

Reject for a new production deployment. The project was archived on
2025-06-27, and its own README states that it was retired after its metadata
service became unusable and the Open Library transition stalled. Source:
[Readarr repository](https://github.com/Readarr/Readarr).

### BookBounty

Reject. BookBounty retrieves missing **ebooks** for Readarr from LibGen; its
documented formats are ebook formats and it depends on Readarr. It is not an
audiobook/Prowlarr request manager. Source:
[BookBounty repository](https://github.com/Squeaks72/BookBounty).

### AudioBookRequest Jackett fork

Reject for production. The Jackett/Torznab fork is explicitly work in progress,
has no stable release, and is much less established than Shelfmark. The
original AudioBookRequest also remains tied to metadata sources that do not
solve Russian discovery reliably. Sources:
[AudioBookRequest](https://github.com/markbeep/AudioBookRequest) and
[AudioBookRequest-Jackett](https://github.com/Andris73/AudioBookRequest-Jackett).

### Audiobookshelf Discovery Edition

This fork is interesting because it adds a direct Prowlarr search and a
FantLab metadata provider, which is unusually relevant to Russian books.
However, it replaces the Audiobookshelf server itself, is based on a specific
ABS version, documents downgrade risk, requires qBittorrent rather than the
existing Transmission setup, and has no stable release track. It is useful as
design evidence for a future FantLab provider, not as a production dependency.
Source: [Audiobookshelf Discovery Edition](https://github.com/MatthewNapierTV/Audiobookshelf-Discovery-Edition).

## Pilot acceptance criteria

Keep ReadMeABook running and validate Shelfmark in parallel with two canaries:

- a Russian multi-file MP3 release found only through a raw Cyrillic query;
- a Russian M4B release with author, title, series name and series sequence
  supplied or corrected before publication.

The pilot passes only if the exact RuTracker result can be selected, the VLESS
egress path is preserved, Transmission completion is detected, files are
published atomically to Moscow, Audiobookshelf sees one correctly grouped book,
Absorb plays it and retains progress, and a repeated publisher run is
idempotent. Series metadata should be an explicit gate: tracker-first search
solves acquisition, but it does not by itself guarantee clean Russian metadata.

## Final recommendation

Adopt **Shelfmark as a parallel Russian-book request UI**, reusing Prowlarr,
RuTracker, Transmission, the VLESS routing, and the proven Moscow publication
boundary. Retain ReadMeABook until the Shelfmark canaries and a short soak pass.
If manual imports repeatedly require too much metadata repair, pilot
JeremiahM37's Librarr next; do not fall back to Shelfarr unless its metadata
catalogue is first shown to contain the actual Russian authors and series the
household requests.
