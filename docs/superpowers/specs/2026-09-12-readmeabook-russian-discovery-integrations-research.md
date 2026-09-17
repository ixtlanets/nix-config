# ReadMeABook: Russian discovery and Prowlarr-first integration research

Date: 2026-09-12

## Question

Does ReadMeABook provide a ready-made integration that can discover Russian
audiobooks directly through Prowlarr/RuTracker, use a metadata provider other
than Audible/Audnexus, or create a custom request without first finding an
Audible catalogue entry?

## Conclusion

No. ReadMeABook v1.2.2 and current upstream `main` do not provide a supported
Prowlarr-first discovery UI, a Russian metadata provider, or an official addon
that removes the Audible/ASIN dependency. Prowlarr is already integrated, but
it is the **release search** layer after ReadMeABook has an audiobook identity;
Audible/Audnexus remains the **book discovery and identity** layer.

The upstream maintainer explicitly rejected additional metadata providers as
not planned: Audible and ASINs are used across discovery, authors, series,
deduplication, requests, cover caching, runtime lookup, and Plex/ABS matching.
Even Goodreads and Hardcover entries are resolved back to Audible before a
request is created. See the maintainer's response in
[issue #260](https://github.com/kikootwo/ReadMeABook/issues/260#issuecomment-5333833921)
and the earlier statement in
[issue #134](https://github.com/kikootwo/ReadMeABook/issues/134#issuecomment-4006442437).

## Version scope

The latest release inspected is
[v1.2.2](https://github.com/kikootwo/ReadMeABook/releases/tag/v1.2.2). Upstream
`main` at [`bc371860`](https://github.com/kikootwo/ReadMeABook/commit/bc371860d06c921e2f474ada226b7a3c6427fca5)
is four commits ahead; those commits are download/retry/delete/result-limiting
fixes, not a new discovery or metadata integration. The exact comparison is
[v1.2.2...bc371860](https://github.com/kikootwo/ReadMeABook/compare/v1.2.2...bc371860d06c921e2f474ada226b7a3c6427fca5).

## What the built-in searches actually query

- The main audiobook search obtains an `AudibleService` and calls its search
  method; the UI describes the page as finding books from Audible:
  [API route](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/app/api/audiobooks/search/route.ts#L17-L38),
  [search page](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/app/search/page.tsx#L56-L64).
- Author search uses Audnexus:
  [author route](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/app/api/authors/search/route.ts#L19-L63).
- Series search uses Audible:
  [series route](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/app/api/series/search/route.ts#L13-L40).
- Supported Audible regions are `us`, `ca`, `uk`, `au`, `in`, `de`, `es`, and
  `fr`; there is no Russian region or Russian language profile:
  [region types](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/lib/types/audible.ts#L8-L19),
  [language types](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/lib/constants/language-config.ts#L19-L20).

Consequently, `Вадим Панов` and `Анклавы` cannot be made reliable merely by
changing Prowlarr settings: those queries fail or become irrelevant before
Prowlarr participates.

## What the Prowlarr integration already provides

ReadMeABook has automatic, manual, and interactive Prowlarr searches. The
documented `Manual Search` and `Interactive Search` endpoints operate on an
existing request ID, and the UI exposes them on requests in specific states:
[Prowlarr documentation](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/documentation/phase3/prowlarr.md#L64-L94).
They are not a separate Prowlarr-first catalogue.

There is also a useful lower-level endpoint,
`POST /api/audiobooks/search-torrents`, which accepts arbitrary `title` and
`author` and searches configured Prowlarr indexers before a request exists:
[endpoint schema and implementation](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/app/api/audiobooks/search-torrents/route.ts#L21-L42).
However, the stock UI invokes this flow from an audiobook details modal and
requires the full audiobook object to create the request:
[modal binding](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/components/requests/InteractiveTorrentSearchModal.tsx#L271-L310),
[details modal](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/components/audiobooks/AudiobookDetailsModal.tsx#L814-L832).
The request-with-selected-release schema still requires an `asin`, `title`,
and `author`, then attempts Audnexus enrichment:
[request schema](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/app/api/audiobooks/request-with-torrent/route.ts#L19-L30),
[Audnexus enrichment](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/app/api/audiobooks/request-with-torrent/route.ts#L120-L150).

Therefore, most required release-search machinery already exists, but there is
no supported UI path from a free-form Russian book query to a custom local book
identity and request.

## Other built-in integrations

Goodreads and Hardcover are shelf/list ingestion integrations rather than
alternative metadata providers. Both resolve imported books to an Audible ASIN
before creating requests:
[Goodreads sync](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/documentation/backend/services/goodreads-sync.md#L29-L45),
[Hardcover sync](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/documentation/backend/services/hardcover-sync.md#L1-L20).
They do not solve discovery for books absent from Audible.

`Manual Import` is for already-present local audio files attached to an
audiobook details flow; it is not a custom Prowlarr discovery/request screen:
[details modal actions](https://github.com/kikootwo/ReadMeABook/blob/bc371860d06c921e2f474ada226b7a3c6427fca5/src/components/audiobooks/AudiobookDetailsModal.tsx#L705-L724).

## Pending and third-party work

The closest upstream contribution is open
[PR #290](https://github.com/kikootwo/ReadMeABook/pull/290), which adds an
admin-only magnet-link/`.torrent` upload. It is not merged or released, still
attaches the release to an existing request, and does not provide Russian
metadata or Prowlarr-first discovery.

A Discord bot is proposed in open
[PR #231](https://github.com/kikootwo/ReadMeABook/pull/231), but it also starts
requests through Audible search and is not a replacement metadata/discovery
provider. No supported addon or plugin interface for replacing the Audible
identity layer is documented in the upstream repository.

## Practical implication for this deployment

There is no ready setting or addon to enable. The realistic options are:

1. Keep the existing guarded `manual-request.py` workflow: search directly in
   Prowlarr/RuTracker, choose an exact topic, create a controlled request, and
   preserve admin approval and the existing download/publisher pipeline.
2. Add a small repo-managed UI over the same workflow. It can reuse
   ReadMeABook's Prowlarr search/ranking endpoint, but it must introduce a safe
   local identity for non-Audible books and explicit metadata fields.
3. Fork/patch ReadMeABook itself to abstract its ASIN identity model. Upstream's
   own assessment in issue #260 indicates that this is a broad architectural
   change rather than a small provider adapter.

For this installation, option 2 is the smallest user-facing improvement while
retaining the production controls already built around requests, Transmission,
publishing, and Audiobookshelf.
