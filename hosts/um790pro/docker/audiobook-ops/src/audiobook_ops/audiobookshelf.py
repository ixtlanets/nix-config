from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import dataclass
from difflib import SequenceMatcher
import hashlib
import json
import re
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

from audiobook_ops.interface import CatalogMutationError, OperationError


@dataclass(frozen=True)
class AbsBytesResponse:
    content_type: str | None
    body: bytes


class AbsHTTP(Protocol):
    def json(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> object: ...

    def bytes(self, method: str, path: str, maximum_bytes: int) -> AbsBytesResponse: ...

    def upload_cover(
        self,
        path: str,
        *,
        filename: str,
        mime_type: str,
        content: bytes,
    ) -> object: ...


class PreparedCoverFetcher(Protocol):
    def fetch(self, source_url: str) -> dict[str, object]: ...


class AudiobookshelfHTTPClient:
    """Bounded bearer transport for the version-pinned ABS adapter."""

    def __init__(self, base_url: str, api_token: str) -> None:
        parsed = urlparse(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise OperationError("invalid Audiobookshelf address")
        if not api_token:
            raise OperationError("Audiobookshelf API token is required")
        self._base_url = base_url.rstrip("/")
        self._authorization = f"Bearer {api_token}"

    def json(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> object:
        if method not in {"GET", "PATCH", "DELETE"} or not path.startswith("/api/"):
            raise OperationError("unsupported Audiobookshelf request")
        body = None
        headers = {"Accept": "application/json", "Authorization": self._authorization}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            headers["Content-Type"] = "application/json"
        response = self._request(Request(self._base_url + path, data=body, headers=headers, method=method), 16 * 1024 * 1024)
        if method == "DELETE":
            return {}
        try:
            return json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise OperationError("Audiobookshelf returned invalid JSON") from error

    def bytes(self, method: str, path: str, maximum_bytes: int) -> AbsBytesResponse:
        if method != "GET" or not path.startswith("/api/items/"):
            raise OperationError("unsupported Audiobookshelf binary request")
        return self._request(
            Request(
                self._base_url + path,
                headers={"Accept": "image/*", "Authorization": self._authorization},
                method="GET",
            ),
            maximum_bytes,
        )

    def upload_cover(
        self,
        path: str,
        *,
        filename: str,
        mime_type: str,
        content: bytes,
    ) -> object:
        if (
            not path.startswith("/api/items/")
            or not path.endswith("/cover")
            or not re.fullmatch(r"cover\.(?:jpg|png|webp)", filename)
            or mime_type not in {"image/jpeg", "image/png", "image/webp"}
            or len(content) > 10 * 1024 * 1024
        ):
            raise OperationError("invalid Audiobookshelf cover upload")
        boundary = "audiobookops" + hashlib.sha256(content).hexdigest()[:24]
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="cover"; filename="{filename}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        response = self._request(
            Request(
                self._base_url + path,
                data=body,
                headers={
                    "Accept": "application/json",
                    "Authorization": self._authorization,
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
                method="POST",
            ),
            1024 * 1024,
        )
        try:
            return json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise OperationError("Audiobookshelf returned invalid JSON") from error

    @staticmethod
    def _request(request: Request, maximum_bytes: int) -> AbsBytesResponse:
        try:
            with urlopen(request, timeout=30) as response:
                declared = response.headers.get("Content-Length")
                if declared is not None and int(declared) > maximum_bytes:
                    raise OperationError("Audiobookshelf response exceeds the size limit")
                body = response.read(maximum_bytes + 1)
                content_type = response.headers.get("Content-Type")
        except HTTPError as error:
            error.close()
            raise OperationError("Audiobookshelf request failed") from error
        except (URLError, TimeoutError, ValueError) as error:
            raise OperationError("Audiobookshelf request failed") from error
        if len(body) > maximum_bytes:
            raise OperationError("Audiobookshelf response exceeds the size limit")
        return AbsBytesResponse(content_type, body)


def _normalized(value: object) -> str:
    return " ".join(str(value).casefold().replace("ё", "е").split())


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


class AudiobookshelfAdapter:
    """Version-isolated Audiobookshelf 2.36.0 catalog and mutation adapter."""

    _FIELDS = {
        "title": "title",
        "subtitle": "subtitle",
        "narrators": "narrators",
        "genres": "genres",
        "published_year": "publishedYear",
        "published_date": "publishedDate",
        "publisher": "publisher",
        "description": "description",
        "isbn": "isbn",
        "asin": "asin",
        "language": "language",
        "explicit": "explicit",
        "abridged": "abridged",
    }

    def __init__(self, http: AbsHTTP, cover_fetcher: PreparedCoverFetcher) -> None:
        self._http = http
        self._cover_fetcher = cover_fetcher

    def search(self, query: str) -> list[dict[str, object]]:
        tokens = set(re.findall(r"\w+", _normalized(query)))
        ranked: list[tuple[float, dict[str, object]]] = []
        for library in self._book_libraries():
            for item in self._items(str(library["id"])):
                normalized = self._normalize_item(item)
                metadata = normalized["metadata"]
                haystack = " ".join(
                    [
                        str(metadata.get("title", "")),
                        *[str(value) for value in metadata.get("authors", [])],
                        *[str(value) for value in metadata.get("narrators", [])],
                        *[
                            str(value.get("name", ""))
                            for value in metadata.get("series", [])
                            if isinstance(value, dict)
                        ],
                    ]
                )
                haystack_normalized = _normalized(haystack)
                haystack_tokens = set(re.findall(r"\w+", haystack_normalized))
                overlap = len(tokens & haystack_tokens) / len(tokens) if tokens else 0.0
                similarity = SequenceMatcher(
                    None, _normalized(metadata.get("title", "")), _normalized(query), autojunk=False
                ).ratio()
                score = max(overlap, similarity)
                if score > 0:
                    normalized["match_score_milli"] = round(score * 1000)
                    ranked.append((score, normalized))
        ranked.sort(
            key=lambda pair: (
                -pair[0],
                _normalized(pair[1]["metadata"].get("title", "")),
                str(pair[1]["item_id"]),
            )
        )
        return [item for _score, item in ranked]

    def audit(self, library_ids: list[str]) -> dict[str, object]:
        libraries = self._book_libraries()
        accessible = {str(library["id"]): library for library in libraries}
        selected = library_ids or sorted(accessible)
        if any(library_id not in accessible for library_id in selected):
            raise OperationError("requested book library is not accessible")
        issues: list[dict[str, object]] = []
        identities: dict[tuple[str, tuple[str, ...]], list[dict[str, object]]] = {}
        author_count = 0
        series_count = 0
        for library_id in selected:
            author_count += len(self._paged_entities(library_id, "authors"))
            series_count += len(self._paged_entities(library_id, "series"))
            for raw in self._items(library_id):
                item = self._normalize_item(raw)
                metadata = item["metadata"]
                if not str(metadata.get("title") or "").strip():
                    issues.append(self._issue("missing_title", item))
                if not metadata.get("authors"):
                    issues.append(self._issue("missing_authors", item))
                if not metadata.get("narrators"):
                    issues.append(self._issue("missing_narrators", item))
                if any(
                    not isinstance(series, dict)
                    or not str(series.get("name") or "").strip()
                    or not str(series.get("sequence") or "").strip()
                    for series in metadata.get("series", [])
                ):
                    issues.append(self._issue("incomplete_series", item))
                identity = (
                    _normalized(metadata.get("title", "")),
                    tuple(sorted(_normalized(author) for author in metadata.get("authors", []))),
                )
                identities.setdefault(identity, []).append(item)
        for identity, items in identities.items():
            if identity[0] and len(items) > 1:
                issues.append(
                    {
                        "kind": "suspected_duplicate",
                        "item_ids": [item["item_id"] for item in items],
                        "library_ids": [item["library_id"] for item in items],
                    }
                )
        return {
            "library_ids": selected,
            "authors_read": author_count,
            "series_read": series_count,
            "issues": issues,
        }

    def get_item(self, library_id: str, item_id: str) -> dict[str, object]:
        raw = self._http.json(
            "GET", f"/api/items/{quote(item_id, safe='')}?expanded=1"
        )
        if not isinstance(raw, dict) or raw.get("libraryId") != library_id:
            raise OperationError("Audiobookshelf returned a different item")
        return self._normalize_item(raw, fetch_cover=True)

    def prepare_cover(self, source_url: str) -> dict[str, object]:
        return self._cover_fetcher.fetch(source_url)

    def snapshot_exact(self, target: dict[str, object]) -> dict[str, object]:
        item = self.get_item(str(target["library_id"]), str(target["item_id"]))
        self._require_target(item, target)
        cover = item["cover"]
        if cover is not None:
            response = self._http.bytes(
                "GET",
                f"/api/items/{quote(str(target['item_id']), safe='')}/cover?raw=1",
                10 * 1024 * 1024,
            )
            mime_type = (response.content_type or "").split(";", 1)[0].strip().casefold()
            if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
                raise OperationError("Audiobookshelf returned an invalid cover snapshot")
            if not response.body or len(response.body) > 10 * 1024 * 1024:
                raise OperationError("Audiobookshelf returned an invalid cover snapshot")
            cover = {
                **cover,
                "mime_type": mime_type,
                "filename": {
                    "image/jpeg": "cover.jpg",
                    "image/png": "cover.png",
                    "image/webp": "cover.webp",
                }[mime_type],
                "checksum": hashlib.sha256(response.body).hexdigest(),
                "_content_b64": base64.b64encode(response.body).decode(),
            }
        return {"metadata": deepcopy(item["metadata"]), "cover": cover}

    def apply_exact(
        self,
        target: dict[str, object],
        desired: dict[str, object],
        rollback: dict[str, object],
    ) -> dict[str, object]:
        current = self.get_item(str(target["library_id"]), str(target["item_id"]))
        self._require_target(current, target)
        try:
            self._write_snapshot(str(target["item_id"]), desired, rollback)
            updated = self.get_item(str(target["library_id"]), str(target["item_id"]))
            self._require_snapshot(updated, target, desired)
            return updated
        except OperationError as error:
            compensated = False
            try:
                self._write_snapshot(str(target["item_id"]), rollback, desired)
                restored = self.get_item(str(target["library_id"]), str(target["item_id"]))
                self._require_snapshot(restored, target, rollback)
                compensated = True
            except OperationError:
                compensated = False
            raise CatalogMutationError(
                "Audiobookshelf update failed; previous state was restored"
                if compensated
                else "Audiobookshelf update failed and requires attention",
                compensated=compensated,
            ) from error

    def _write_snapshot(
        self,
        item_id: str,
        desired: dict[str, object],
        reference: dict[str, object],
    ) -> None:
        desired_metadata = desired.get("metadata")
        reference_metadata = reference.get("metadata")
        if not isinstance(desired_metadata, dict) or not isinstance(reference_metadata, dict):
            raise OperationError("invalid Audiobookshelf metadata snapshot")
        media_payload: dict[str, object] = {}
        metadata_payload: dict[str, object] = {}
        for local, remote in self._FIELDS.items():
            if desired_metadata.get(local) != reference_metadata.get(local):
                metadata_payload[remote] = deepcopy(desired_metadata.get(local))
        if desired_metadata.get("authors") != reference_metadata.get("authors"):
            metadata_payload["authors"] = [
                {"name": name} for name in desired_metadata.get("authors", [])
            ]
        if desired_metadata.get("series") != reference_metadata.get("series"):
            metadata_payload["series"] = deepcopy(desired_metadata.get("series", []))
        if desired_metadata.get("tags") != reference_metadata.get("tags"):
            media_payload["tags"] = deepcopy(desired_metadata.get("tags", []))
        if metadata_payload:
            media_payload["metadata"] = metadata_payload
        if media_payload:
            self._http.json(
                "PATCH", f"/api/items/{quote(item_id, safe='')}/media", media_payload
            )

        desired_cover = desired.get("cover")
        reference_cover = reference.get("cover")
        desired_checksum = (
            desired_cover.get("checksum") if isinstance(desired_cover, dict) else None
        )
        reference_checksum = (
            reference_cover.get("checksum") if isinstance(reference_cover, dict) else None
        )
        if desired_checksum == reference_checksum:
            return
        path = f"/api/items/{quote(item_id, safe='')}/cover"
        if desired_cover is None:
            self._http.json("DELETE", path)
            return
        if not isinstance(desired_cover, dict):
            raise OperationError("invalid Audiobookshelf cover snapshot")
        try:
            content = base64.b64decode(str(desired_cover["_content_b64"]), validate=True)
            filename = str(desired_cover["filename"])
            mime_type = str(desired_cover["mime_type"])
        except (KeyError, ValueError) as error:
            raise OperationError("invalid Audiobookshelf cover snapshot") from error
        if hashlib.sha256(content).hexdigest() != desired_checksum:
            raise OperationError("Audiobookshelf cover snapshot checksum changed")
        self._http.upload_cover(
            path, filename=filename, mime_type=mime_type, content=content
        )

    def _book_libraries(self) -> list[dict[str, object]]:
        payload = self._http.json("GET", "/api/libraries")
        if not isinstance(payload, dict) or not isinstance(payload.get("libraries"), list):
            raise OperationError("Audiobookshelf returned invalid libraries")
        libraries = [
            library
            for library in payload["libraries"]
            if isinstance(library, dict)
            and library.get("mediaType") == "book"
            and isinstance(library.get("id"), str)
        ]
        return sorted(libraries, key=lambda library: str(library["id"]))

    def _items(self, library_id: str) -> list[dict[str, object]]:
        listed = self._paged_entities(library_id, "items")
        expanded: list[dict[str, object]] = []
        for item in listed:
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id:
                raise OperationError("Audiobookshelf returned invalid item identity")
            exact = self._http.json(
                "GET", f"/api/items/{quote(item_id, safe='')}?expanded=1"
            )
            if not isinstance(exact, dict) or exact.get("libraryId") != library_id:
                raise OperationError("Audiobookshelf returned a different item")
            expanded.append(exact)
        return expanded

    def _paged_entities(self, library_id: str, entity: str) -> list[dict[str, object]]:
        if entity not in {"items", "authors", "series"}:
            raise OperationError("unsupported Audiobookshelf entity")
        collected: list[dict[str, object]] = []
        page = 0
        while True:
            query = urlencode({"limit": 100, "page": page, **({"minified": 0} if entity == "items" else {})})
            payload = self._http.json(
                "GET",
                f"/api/libraries/{quote(library_id, safe='')}/{entity}?{query}",
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                raise OperationError(f"Audiobookshelf returned invalid {entity}")
            results = payload["results"]
            if any(not isinstance(result, dict) for result in results):
                raise OperationError(f"Audiobookshelf returned invalid {entity}")
            collected.extend(results)
            total = payload.get("total", len(collected))
            if not isinstance(total, int) or total < len(collected):
                raise OperationError(f"Audiobookshelf returned invalid {entity} total")
            if len(collected) >= total:
                return collected
            if not results or page >= 10_000:
                raise OperationError(f"Audiobookshelf {entity} pagination stalled")
            page += 1

    def _normalize_item(
        self,
        raw: object,
        *,
        fetch_cover: bool = False,
    ) -> dict[str, object]:
        if not isinstance(raw, dict) or raw.get("mediaType") != "book":
            raise OperationError("Audiobookshelf returned a non-book item")
        media = raw.get("media")
        if not isinstance(media, dict) or not isinstance(media.get("metadata"), dict):
            raise OperationError("Audiobookshelf returned invalid book metadata")
        source = media["metadata"]
        authors = source.get("authors", [])
        series = source.get("series", [])
        narrators = source.get("narrators", [])
        genres = source.get("genres", [])
        tags = media.get("tags", [])
        if (
            not isinstance(authors, list)
            or any(
                not isinstance(author, dict)
                or not isinstance(author.get("name"), str)
                for author in authors
            )
            or not isinstance(series, list)
            or any(
                not isinstance(value, dict)
                or not isinstance(value.get("name"), str)
                or value.get("sequence") is not None
                and not isinstance(value.get("sequence"), str)
                for value in series
            )
            or not isinstance(narrators, list)
            or any(not isinstance(value, str) for value in narrators)
            or not isinstance(genres, list)
            or any(not isinstance(value, str) for value in genres)
            or not isinstance(tags, list)
            or any(not isinstance(value, str) for value in tags)
        ):
            raise OperationError("Audiobookshelf returned invalid authors or series")
        metadata = {
            local: deepcopy(source.get(remote))
            for local, remote in self._FIELDS.items()
        }
        metadata["authors"] = [str(author["name"]) for author in authors]
        metadata["narrators"] = deepcopy(narrators)
        metadata["series"] = [
            {"name": str(value.get("name")), "sequence": value.get("sequence")}
            for value in series
        ]
        metadata["genres"] = deepcopy(genres)
        metadata["tags"] = deepcopy(tags)
        cover_path = media.get("coverPath")
        cover: dict[str, object] | None = None
        if isinstance(cover_path, str) and cover_path:
            cover = {"path": cover_path}
            if fetch_cover:
                response = self._http.bytes(
                    "GET",
                    f"/api/items/{quote(str(raw.get('id')), safe='')}/cover?raw=1",
                    10 * 1024 * 1024,
                )
                if not response.body:
                    raise OperationError("Audiobookshelf returned an empty cover")
                cover["checksum"] = hashlib.sha256(response.body).hexdigest()
        identity = {
            "item_id": raw.get("id"),
            "library_id": raw.get("libraryId"),
            "path": raw.get("path"),
            "updated_at": raw.get("updatedAt"),
            "metadata": metadata,
            "cover_path": cover_path,
        }
        if any(not isinstance(identity[key], str) or not identity[key] for key in ("item_id", "library_id", "path")):
            raise OperationError("Audiobookshelf returned invalid item identity")
        return {
            "library_id": identity["library_id"],
            "item_id": identity["item_id"],
            "path": identity["path"],
            "revision": _digest(identity),
            "metadata": metadata,
            "cover": cover,
        }

    @staticmethod
    def _issue(kind: str, item: dict[str, object]) -> dict[str, object]:
        return {
            "kind": kind,
            "library_id": item["library_id"],
            "item_id": item["item_id"],
            "path": item["path"],
            "revision": item["revision"],
        }

    @staticmethod
    def _require_target(item: dict[str, object], target: dict[str, object]) -> None:
        if any(item.get(key) != target.get(key) for key in ("library_id", "item_id", "path", "revision")):
            raise OperationError("Audiobookshelf item identity changed")

    @staticmethod
    def _require_snapshot(
        item: dict[str, object], target: dict[str, object], snapshot: dict[str, object]
    ) -> None:
        if any(item.get(key) != target.get(key) for key in ("library_id", "item_id", "path")):
            raise OperationError("Audiobookshelf item path changed")
        if item.get("metadata") != snapshot.get("metadata"):
            raise OperationError("Audiobookshelf metadata verification failed")
        expected_cover = snapshot.get("cover")
        observed_cover = item.get("cover")
        if expected_cover is None:
            if observed_cover is not None:
                raise OperationError("Audiobookshelf cover verification failed")
        elif (
            not isinstance(expected_cover, dict)
            or not isinstance(observed_cover, dict)
            or expected_cover.get("checksum") != observed_cover.get("checksum")
        ):
            raise OperationError("Audiobookshelf cover verification failed")
