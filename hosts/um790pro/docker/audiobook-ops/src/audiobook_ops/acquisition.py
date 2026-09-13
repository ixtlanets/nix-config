from __future__ import annotations

from copy import deepcopy
import hashlib
from html import unescape
import json
import re
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

from audiobook_ops.interface import OperationError


class RouteGuard(Protocol):
    def require(self) -> None: ...


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        file_pointer: object,
        code: int,
        message: str,
        headers: object,
        new_url: str,
    ) -> None:
        return None


class HTTPVlessRouteGuard:
    """Require fresh positive evidence from the host-managed VLESS route probe."""

    def __init__(self, health_url: str) -> None:
        parsed = urlparse(health_url)
        if (
            parsed.scheme != "http"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path != "/health"
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise OperationError("invalid VLESS route health address")
        self._health_url = health_url
        self._opener = build_opener(_RejectRedirects())

    def require(self) -> None:
        request = Request(self._health_url, headers={"Accept": "application/json"})
        try:
            with self._opener.open(request, timeout=5) as response:
                payload = response.read(4097)
        except HTTPError as error:
            error.close()
            raise OperationError("required VLESS route is unavailable") from error
        except (URLError, TimeoutError, ValueError) as error:
            raise OperationError("required VLESS route is unavailable") from error
        if len(payload) > 4096:
            raise OperationError("required VLESS route is unavailable")
        try:
            evidence = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise OperationError("required VLESS route is unavailable") from error
        if not isinstance(evidence, dict) or evidence.get("status") != "ok" or evidence.get(
            "route"
        ) != "vless":
            raise OperationError("required VLESS route is unavailable")


class ProwlarrHTTP(Protocol):
    def search(self, query: str) -> list[dict[str, object]]: ...

    def topic(self, internal_url: str) -> str: ...


class ProwlarrHTTPClient:
    """Bounded HTTP implementation for the pinned Prowlarr contract."""

    def __init__(self, base_url: str, api_key: str) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise OperationError("invalid Prowlarr address")
        if not api_key:
            raise OperationError("Prowlarr API key is required")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def search(self, query: str) -> list[dict[str, object]]:
        encoded = urlencode(
            {"categories": "3030", "query": query, "type": "search"}
        )
        request = Request(
            f"{self._base_url}/api/v1/search?{encoded}",
            headers={"Accept": "application/json", "X-Api-Key": self._api_key},
        )
        payload = self._read(request, 2 * 1024 * 1024)
        try:
            value = json.loads(payload)
        except json.JSONDecodeError as error:
            raise OperationError("Prowlarr returned invalid JSON") from error
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise OperationError("Prowlarr returned an invalid search result")
        return value

    def topic(self, internal_url: str) -> str:
        request = Request(internal_url, headers={"Accept": "text/html"})
        # The restricted gateway deliberately mirrors RuTracker's legacy
        # windows-1251 response contract.
        return self._read(request, 512 * 1024).decode(
            "windows-1251", errors="replace"
        )

    @staticmethod
    def _read(request: Request, maximum: int) -> bytes:
        try:
            with urlopen(request, timeout=30) as response:
                declared = response.headers.get("Content-Length")
                if declared is not None and int(declared) > maximum:
                    raise OperationError("upstream response exceeds the size limit")
                payload = response.read(maximum + 1)
        except HTTPError as error:
            error.close()
            raise OperationError("upstream request failed") from error
        except (URLError, TimeoutError, ValueError) as error:
            raise OperationError("upstream request failed") from error
        if len(payload) > maximum:
            raise OperationError("upstream response exceeds the size limit")
        return payload


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _topic_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "rutracker-gateway"
        or parsed.port != 8080
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != "/forum/viewtopic.php"
        or parsed.fragment
    ):
        return None
    query = parse_qs(parsed.query)
    if set(query) != {"t"}:
        return None
    matches = query["t"]
    if len(matches) != 1 or not matches[0].isdigit():
        return None
    return matches[0]


def _bounded_topic_evidence(document: str) -> tuple[str | None, str]:
    bounded = document[:65536]
    title_match = re.search(r"<title[^>]*>(.*?)</title>", bounded, re.I | re.S)
    title = None
    if title_match:
        title = " ".join(unescape(title_match.group(1)).split())[:300]
    without_markup = re.sub(r"<[^>]+>", " ", bounded)
    excerpt = " ".join(unescape(without_markup).split())[:1000]
    return title, excerpt


def _normalized_tokens(value: str) -> set[str]:
    return set(re.findall(r"\w+", value.casefold().replace("ё", "е")))


def _audio_format(title: str) -> str | None:
    lowered = title.casefold()
    for audio_format in ("m4b", "flac", "m4a", "mp3"):
        if re.search(rf"(?:^|\W){audio_format}(?:$|\W)", lowered):
            return audio_format
    return None


class ProwlarrReleaseAdapter:
    """Normalize RuTracker results while retaining resolution data internally."""

    def __init__(self, http: ProwlarrHTTP, route_guard: RouteGuard) -> None:
        self._http = http
        self._route_guard = route_guard
        self._candidates: dict[str, dict[str, object]] = {}

    def search(self, queries: list[str]) -> list[dict[str, object]]:
        if (
            not isinstance(queries, list)
            or not 1 <= len(queries) <= 12
            or any(not isinstance(query, str) or not query.strip() for query in queries)
        ):
            raise OperationError("one to twelve non-empty search queries are required")

        selected: dict[str, dict[str, object]] = {}
        identities: dict[tuple[str, str], str] = {}
        for query in queries:
            self._route_guard.require()
            results = self._http.search(query)
            if not isinstance(results, list):
                raise OperationError("Prowlarr returned an invalid search result")
            for raw in results:
                normalized = self._normalize(raw, query)
                if normalized is None:
                    continue
                topic_key = ("topic", str(normalized["topic_id"]))
                infohash = normalized["_private"].get("infohash")
                infohash_key = ("infohash", str(infohash)) if infohash else None
                existing_id = identities.get(topic_key)
                if existing_id is None and infohash_key is not None:
                    existing_id = identities.get(infohash_key)
                if existing_id is None:
                    candidate_id = str(normalized["candidate_id"])
                    selected[candidate_id] = normalized
                    identities[topic_key] = candidate_id
                    if infohash_key is not None:
                        identities[infohash_key] = candidate_id
                    continue

                existing = selected[existing_id]
                matched_queries = list(existing["matched_queries"])
                if query not in matched_queries:
                    matched_queries.append(query)
                best_query_match = max(
                    int(existing["rank_evidence"]["query_match_milli"]),
                    int(normalized["rank_evidence"]["query_match_milli"]),
                )
                if int(normalized["seeders"]) > int(existing["seeders"]):
                    normalized["candidate_id"] = existing_id
                    normalized["matched_queries"] = matched_queries
                    normalized["rank_evidence"][
                        "query_match_milli"
                    ] = best_query_match
                    selected[existing_id] = normalized
                else:
                    existing["matched_queries"] = matched_queries
                    existing["rank_evidence"][
                        "query_match_milli"
                    ] = best_query_match

        self._candidates.update(selected)
        ranked = sorted(
            selected.values(),
            key=lambda candidate: (
                -int(candidate["rank_evidence"]["query_match_milli"]),
                -int(candidate["rank_evidence"]["format_preference"]),
                -int(candidate["seeders"]),
                int(candidate["size_bytes"]),
                str(candidate["title"]).casefold(),
                str(candidate["candidate_id"]),
            ),
        )
        return [self._public(candidate) for candidate in ranked]

    def inspect(self, candidate_id: str) -> dict[str, object]:
        candidate = self._candidate(candidate_id)
        self._route_guard.require()
        internal_url = str(candidate["_private"]["info_url"])
        if _topic_id(internal_url) != candidate["topic_id"]:
            raise OperationError("candidate topic route is unsafe")
        document = self._http.topic(internal_url)
        if not isinstance(document, str):
            raise OperationError("RuTracker returned an invalid topic document")
        topic_title, topic_excerpt = _bounded_topic_evidence(document)
        return {
            **self._public(candidate),
            "topic_title": topic_title,
            "topic_excerpt": topic_excerpt,
        }

    def resolve(self, candidate_id: str) -> dict[str, object]:
        candidate = self._candidate(candidate_id)
        private = candidate["_private"]
        infohash = private.get("infohash")
        magnet = private.get("magnet_uri")
        if not isinstance(infohash, str) or not isinstance(magnet, str):
            raise OperationError("candidate has no credential-free magnet resolution")
        parsed = urlparse(magnet)
        xt = parse_qs(parsed.query).get("xt", [])
        if parsed.scheme != "magnet" or xt != [f"urn:btih:{infohash}"]:
            raise OperationError("candidate magnet identity changed")
        return {"infohash": infohash, "magnet_uri": magnet}

    def _candidate(self, candidate_id: str) -> dict[str, object]:
        try:
            return self._candidates[candidate_id]
        except KeyError as error:
            raise OperationError("unknown release candidate") from error

    @staticmethod
    def _public(candidate: dict[str, object]) -> dict[str, object]:
        return {
            key: deepcopy(value)
            for key, value in candidate.items()
            if not key.startswith("_")
        }

    @staticmethod
    def _normalize(
        raw: object, query: str
    ) -> dict[str, object] | None:
        if not isinstance(raw, dict):
            return None
        if "rutracker" not in str(raw.get("indexer", "")).casefold():
            return None
        topic_id = _topic_id(raw.get("infoUrl"))
        title = raw.get("title")
        if topic_id is None or not isinstance(title, str) or not title.strip():
            return None
        infohash_value = raw.get("infoHash")
        infohash = (
            infohash_value.lower()
            if isinstance(infohash_value, str)
            and re.fullmatch(r"[0-9a-fA-F]{40}", infohash_value)
            else None
        )
        identity = f"rutracker:{topic_id}:{infohash or ''}"
        candidate_id = "cand_" + hashlib.sha256(identity.encode()).hexdigest()[:24]
        seeders = raw.get("seeders", 0)
        leechers = raw.get("leechers", 0)
        size = raw.get("size", 0)
        public = {
            "candidate_id": candidate_id,
            "source": "rutracker",
            "topic_id": topic_id,
            "title": title.strip(),
            "format": _audio_format(title),
            "seeders": max(0, int(seeders)) if isinstance(seeders, (int, float)) else 0,
            "leechers": max(0, int(leechers)) if isinstance(leechers, (int, float)) else 0,
            "size_bytes": max(0, int(size)) if isinstance(size, (int, float)) else 0,
            "matched_queries": [query],
        }
        title_tokens = _normalized_tokens(title)
        query_tokens = _normalized_tokens(query)
        query_match = (
            len(title_tokens & query_tokens) / len(query_tokens) if query_tokens else 0
        )
        public["rank_evidence"] = {
            "query_match_milli": round(query_match * 1000),
            "format_preference": {
                "m4b": 4,
                "flac": 3,
                "m4a": 2,
                "mp3": 1,
            }.get(public["format"], 0),
            "seeders": public["seeders"],
            "size_bytes": public["size_bytes"],
        }
        private = {
            "download_url": raw.get("downloadUrl"),
            "info_url": raw.get("infoUrl"),
            "infohash": infohash,
            "magnet_uri": raw.get("magnetUrl"),
        }
        revision = hashlib.sha256(
            _canonical({"public": public, "infohash": infohash}).encode()
        ).hexdigest()
        return {**public, "revision": revision, "_private": private}
