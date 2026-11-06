from __future__ import annotations

from datetime import UTC, datetime
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import parse_qs, urlparse

from audiobook_ops.acquisition import (
    HTTPVlessRouteGuard,
    ProwlarrHTTPClient,
    ProwlarrReleaseAdapter,
)
from audiobook_ops.interface import AudiobookOperations, OperationError
from audiobook_ops.mcp_adapter import MCPAdapter

from test_domain_interface import (
    FakeCatalogAdapter,
    FakeClock,
    FakeExternalActionAdapter,
)


class FakeRouteGuard:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.calls = 0

    def require(self) -> None:
        self.calls += 1
        if not self.available:
            raise OperationError("required VLESS route is unavailable")


class FakeProwlarrHTTP:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.topic_requests: list[str] = []
        self.download_requests: list[str] = []
        self.responses: dict[str, list[dict[str, object]]] = {}
        self.topic_html = "<html><title>Кроткая — аудиокнига</title><body>Читает Иван</body></html>"
        self.download_location = "magnet:?xt=urn:btih:" + "c" * 40

    def search(self, query: str) -> list[dict[str, object]]:
        self.queries.append(query)
        return self.responses.get(query, [])

    def topic(self, internal_url: str) -> str:
        self.topic_requests.append(internal_url)
        return self.topic_html

    def download_redirect(self, download_path: str) -> str:
        self.download_requests.append(download_path)
        return self.download_location


class ProwlarrReleaseAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.http = FakeProwlarrHTTP()
        self.guard = FakeRouteGuard()
        self.adapter = ProwlarrReleaseAdapter(self.http, self.guard)

    @staticmethod
    def release(
        *,
        title: str,
        topic_id: str,
        infohash: str,
        seeders: int,
        size: int = 1234,
    ) -> dict[str, object]:
        return {
            "title": title,
            "indexer": "RuTracker",
            "protocol": "torrent",
            "seeders": seeders,
            "leechers": 2,
            "size": size,
            "infoHash": infohash,
            "infoUrl": f"http://rutracker-gateway:8080/forum/viewtopic.php?t={topic_id}",
            "downloadUrl": f"http://prowlarr:9696/download/{topic_id}?apikey=supersecret",
            "magnetUrl": f"magnet:?xt=urn:btih:{infohash}&dn={title}",
        }

    def test_cyrillic_variants_merge_deduplicate_and_rank_deterministically(self) -> None:
        queries = [
            "Фёдор Достоевский Кроткая",
            "Федор Достоевский Кроткая",
            "Достоевский Кроткая аудиокнига",
            "Кроткая Иван",
        ]
        duplicate = self.release(
            title="Достоевский — Кроткая [Иван] MP3",
            topic_id="6214434",
            infohash="a" * 40,
            seeders=12,
        )
        self.http.responses = {
            queries[0]: [duplicate],
            queries[1]: [{**duplicate, "seeders": 25}],
            queries[2]: [
                self.release(
                    title="Кроткая — Достоевский [Пётр] M4B",
                    topic_id="7000000",
                    infohash="b" * 40,
                    seeders=40,
                )
            ],
            queries[3]: [duplicate],
        }

        result = self.adapter.search(queries)

        self.assertEqual(self.http.queries, queries)
        self.assertEqual(self.guard.calls, len(queries))
        self.assertEqual(len(result), 2)
        self.assertEqual([candidate["topic_id"] for candidate in result], ["6214434", "7000000"])
        self.assertEqual(result[0]["seeders"], 25)
        self.assertEqual(result[0]["matched_queries"], [queries[0], queries[1], queries[3]])
        self.assertGreater(
            result[0]["rank_evidence"]["query_match_milli"],
            result[1]["rank_evidence"]["query_match_milli"],
        )
        self.assertNotEqual(result[0]["candidate_id"], result[0]["topic_id"])
        encoded = json.dumps(result, ensure_ascii=False)
        for forbidden in ("magnet:", "downloadUrl", "infoUrl", "infoHash", "supersecret"):
            self.assertNotIn(forbidden, encoded)
        resolution = self.adapter.resolve(result[0]["candidate_id"])
        self.assertEqual(set(resolution), {"infohash", "magnet_uri"})
        self.assertNotIn("supersecret", json.dumps(resolution))

    def test_resolve_uses_credential_free_prowlarr_redirect_when_search_has_no_magnet(self) -> None:
        query = "Антон Чехов Палата № 6"
        infohash = "079cd115f98b5c45eec300e425fb7670e9edaf97"
        self.http.download_location = (
            f"magnet:?xt=urn:btih:{infohash.upper()}"
            "&tr=http%3A%2F%2Fbt3.t-ru.org%2Fann%3Fmagnet"
            "&dn=Chekhov&ws=https%3A%2F%2Fattacker.invalid%2Fsecret-passkey"
        )
        release = self.release(
            title="Чехов Антон — Палата №6 [Андрей Одинцов, MP3]",
            topic_id="6888193",
            infohash="a" * 40,
            seeders=12,
        )
        release["infoHash"] = None
        release["magnetUrl"] = ""
        release["downloadUrl"] = (
            "http://prowlarr:9696/1/download?apikey=supersecret"
            "&link=YWJjZA%3D%3D"
            "&file=Chekhov.torrent"
        )
        self.http.responses = {query: [release]}

        candidate = self.adapter.search([query])[0]
        resolution = self.adapter.resolve(candidate["candidate_id"])

        self.assertEqual(
            self.http.download_requests,
            [
                "/1/download?"
                "link=YWJjZA%3D%3D"
                "&file=Chekhov.torrent"
            ],
        )
        self.assertEqual(
            resolution,
            {
                "infohash": infohash,
                "magnet_uri": (
                    f"magnet:?xt=urn:btih:{infohash}"
                    "&tr=http://bt3.t-ru.org/ann?magnet"
                ),
            },
        )
        self.assertEqual(self.guard.calls, 2)
        self.assertNotIn("supersecret", json.dumps(candidate))
        self.assertNotIn("supersecret", json.dumps(resolution))
        self.assertNotIn("secret-passkey", json.dumps(resolution))

    def test_fallback_request_plan_keeps_resolution_material_out_of_mcp_results(self) -> None:
        query = "Антон Чехов Палата № 6"
        release = self.release(
            title="Чехов Антон — Палата №6 [Андрей Одинцов, MP3]",
            topic_id="6888193",
            infohash="a" * 40,
            seeders=12,
        )
        release["infoHash"] = None
        release["magnetUrl"] = None
        release["downloadUrl"] = (
            "http://prowlarr:9696/1/download?apikey=supersecret"
            "&link=YWJjZA%3D%3D&file=Chekhov.torrent"
        )
        self.http.responses = {query: [release]}
        with tempfile.TemporaryDirectory() as temporary_directory:
            operations = AudiobookOperations.open(
                Path(temporary_directory) / "state.sqlite3",
                clock=FakeClock(datetime(2026, 9, 13, tzinfo=UTC)),
                release_adapter=self.adapter,
                external_action_adapter=FakeExternalActionAdapter(),
                catalog_adapter=FakeCatalogAdapter(),
            )
            try:
                mcp = MCPAdapter(operations)
                searched = mcp.call("release_search", {"queries": [query]})
                candidate = searched["candidates"][0]
                planned = mcp.call(
                    "request_plan",
                    {
                        "candidate_id": candidate["candidate_id"],
                        "candidate_revision": candidate["revision"],
                        "work": {
                            "title": "Палата № 6",
                            "authors": ["Антон Чехов"],
                            "series": [],
                        },
                        "audio_edition": {
                            "narrators": ["Андрей Одинцов"],
                            "abridged": False,
                        },
                        "origin_conversation_id": "telegram:135617",
                    },
                )
            finally:
                operations.close()

        encoded = json.dumps({"searched": searched, "planned": planned})
        for forbidden in (
            "supersecret",
            "download",
            "magnet:",
            "infohash",
            "YWJjZA",
        ):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual(planned["status"], "awaiting_approval")

    def test_inspect_uses_only_the_selected_internal_topic_and_returns_bounded_evidence(self) -> None:
        query = "Достоевский Кроткая"
        self.http.responses = {
            query: [
                self.release(
                    title="Достоевский — Кроткая [Иван] MP3",
                    topic_id="6214434",
                    infohash="a" * 40,
                    seeders=12,
                )
            ]
        }
        candidate = self.adapter.search([query])[0]

        inspected = self.adapter.inspect(candidate["candidate_id"])

        self.assertEqual(
            self.http.topic_requests,
            ["http://rutracker-gateway:8080/forum/viewtopic.php?t=6214434"],
        )
        self.assertEqual(inspected["topic_id"], "6214434")
        self.assertEqual(inspected["topic_title"], "Кроткая — аудиокнига")
        self.assertLessEqual(len(inspected["topic_excerpt"]), 1000)
        self.assertNotIn("magnet_uri", inspected)
        self.assertNotIn("download_url", inspected)

    def test_inspect_omits_active_and_hidden_html_but_keeps_release_description(self) -> None:
        query = "Кроткая Иван"
        self.http.responses = {
            query: [self.release(title="Кроткая [Иван] MP3", topic_id="6214434", infohash="a" * 40, seeders=12)]
        }
        self.http.topic_html = """<html><head><title>Кроткая - аудиокнига</title>
            <script>window.BB = 'SCRIPT_SECRET';</script><style>STYLE_SECRET</style></head>
            <body><form><input name="form_token" value="FORM_SECRET">FORM_SECRET</form>
            <div hidden>HIDDEN_SECRET</div><div aria-hidden="true">ARIA_SECRET</div>
            <div style="display: none">DISPLAY_SECRET</div>
            <p>Автор: Достоевский</p><p>Читает: Иван</p><p>Серия: Классика</p>
            <p>Описание &amp; содержание</p></body></html>"""
        candidate = self.adapter.search([query])[0]
        inspected = self.adapter.inspect(candidate["candidate_id"])
        excerpt = inspected["topic_excerpt"]
        self.assertEqual(inspected["topic_title"], "Кроткая - аудиокнига")
        for text in ("Достоевский", "Читает: Иван", "Серия: Классика", "Описание & содержание"):
            self.assertIn(text, excerpt)
        for forbidden in ("window.BB", "form_token", "SCRIPT_SECRET", "STYLE_SECRET", "FORM_SECRET", "HIDDEN_SECRET", "ARIA_SECRET", "DISPLAY_SECRET"):
            self.assertNotIn(forbidden, json.dumps(inspected, ensure_ascii=False))

        with tempfile.TemporaryDirectory() as temporary_directory:
            operations = AudiobookOperations.open(
                Path(temporary_directory) / "state.sqlite3", release_adapter=self.adapter
            )
            try:
                mcp = MCPAdapter(operations)
                observed = mcp.call("release_inspect", {"candidate_id": candidate["candidate_id"]})
                self.http.topic_html = self.http.topic_html.replace("SCRIPT_SECRET", "ROTATED_SCRIPT").replace("FORM_SECRET", "ROTATED_FORM")
                repeated = mcp.call("release_inspect", {"candidate_id": candidate["candidate_id"]})
                self.assertEqual(observed["revision"], repeated["revision"])
                self.assertEqual(observed["topic_excerpt"], repeated["topic_excerpt"])
                plan = mcp.call("request_plan", {
                    "candidate_id": candidate["candidate_id"],
                    "candidate_revision": observed["revision"],
                    "work": {"title": "Кроткая", "authors": ["Достоевский"], "series": []},
                    "audio_edition": {"narrators": ["Иван"], "abridged": False},
                    "origin_conversation_id": "test",
                })
                self.assertEqual(plan["status"], "awaiting_approval")
                self.assertNotIn("ROTATED_FORM", json.dumps(plan))
            finally:
                operations.close()

    def test_inspect_ignores_self_closing_slashes_on_suppressed_html_elements(self) -> None:
        query = "Кроткая Иван"
        self.http.responses = {
            query: [self.release(title="Кроткая [Иван] MP3", topic_id="6214434", infohash="a" * 40, seeders=12)]
        }
        for opening, closing in (
            ("<script/>", "</script>"),
            ("<style/>", "</style>"),
            ("<form/>", "</form>"),
            ("<div hidden/>", "</div>"),
            ('<div aria-hidden="true"/>', "</div>"),
            ('<div style="display: none"/>', "</div>"),
        ):
            with self.subTest(opening=opening):
                self.http.topic_html = (
                    "<title>Кроткая - аудиокнига</title>"
                    + opening + "SESSION_SENTINEL" + closing
                    + '<input hidden/><p>Читает: Иван</p>'
                )
                candidate = self.adapter.search([query])[0]
                inspected = self.adapter.inspect(candidate["candidate_id"])
                self.assertEqual(inspected["topic_title"], "Кроткая - аудиокнига")
                self.assertIn("Читает: Иван", inspected["topic_excerpt"])
                self.assertNotIn("SESSION_SENTINEL", json.dumps(inspected, ensure_ascii=False))

    def test_inspect_rejects_topic_urls_outside_the_exact_internal_route(self) -> None:
        query = "Достоевский Кроткая"
        unsafe_urls = (
            "https://rutracker-gateway:8080/forum/viewtopic.php?t=6214434",
            "http://user@rutracker-gateway:8080/forum/viewtopic.php?t=6214434",
            "http://rutracker-gateway:80/forum/viewtopic.php?t=6214434",
            "http://rutracker-gateway:8080/forum/viewtopic.php?t=6214434&x=1",
            "http://rutracker-gateway:8080/forum/viewtopic.php?t=6214434#fragment",
        )
        for index, unsafe_url in enumerate(unsafe_urls):
            with self.subTest(unsafe_url=unsafe_url):
                release = self.release(
                    title="Достоевский — Кроткая [Иван] MP3",
                    topic_id=str(6214434 + index),
                    infohash=f"{index + 1:040x}",
                    seeders=12,
                )
                release["infoUrl"] = unsafe_url
                self.http.responses = {query: [release]}

                self.assertEqual(self.adapter.search([query]), [])

    def test_vless_failure_stops_before_search_or_topic_fetch(self) -> None:
        self.guard.available = False

        with self.assertRaisesRegex(OperationError, "VLESS route"):
            self.adapter.search(["Кириллический запрос"])

        self.assertEqual(self.http.queries, [])
        self.assertEqual(self.http.topic_requests, [])

    def test_http_vless_guard_requires_live_explicit_route_evidence(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            evidence: dict[str, str] = {"status": "ok", "route": "vless"}

            def do_GET(self) -> None:
                body = json.dumps(self.evidence).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        guard = HTTPVlessRouteGuard(f"http://{host}:{port}/health")
        try:
            guard.require()
            Handler.evidence = {"status": "degraded", "route": "direct"}
            with self.assertRaisesRegex(OperationError, "VLESS route"):
                guard.require()
        finally:
            server.shutdown()
            server.server_close()

        with self.assertRaisesRegex(OperationError, "invalid VLESS"):
            HTTPVlessRouteGuard("https://public.example/health")

    def test_http_client_sends_unicode_query_and_api_key_only_to_prowlarr(self) -> None:
        requests: list[dict[str, object]] = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                requests.append(
                    {
                        "path": parsed.path,
                        "query": parse_qs(parsed.query),
                        "api_key": self.headers.get("X-Api-Key"),
                    }
                )
                if parsed.path == "/api/v1/search":
                    body = json.dumps([{"title": "Кроткая", "indexer": "RuTracker"}]).encode()
                    content_type = "application/json"
                else:
                    body = "<title>Кроткая</title>".encode("windows-1251")
                    content_type = "text/html; charset=windows-1251"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            client = ProwlarrHTTPClient(f"http://{host}:{port}", "test-api-key")
            self.assertEqual(client.search("Фёдор Кроткая"), [{"title": "Кроткая", "indexer": "RuTracker"}])
            self.assertEqual(
                client.topic(f"http://{host}:{port}/forum/viewtopic.php?t=6214434"),
                "<title>Кроткая</title>",
            )
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(requests[0]["query"]["query"], ["Фёдор Кроткая"])
        self.assertEqual(requests[0]["api_key"], "test-api-key")
        self.assertIsNone(requests[1]["api_key"])

    def test_http_client_resolves_only_a_credential_free_internal_download_route(self) -> None:
        requests: list[dict[str, object]] = []
        infohash = "079CD115F98B5C45EEC300E425FB7670E9EDAF97"

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                requests.append(
                    {
                        "path": parsed.path,
                        "query": parse_qs(parsed.query),
                        "api_key": self.headers.get("X-Api-Key"),
                    }
                )
                self.send_response(301)
                self.send_header("Location", f"magnet:?xt=urn:btih:{infohash}")
                self.end_headers()

            def log_message(self, _format: str, *_args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            client = ProwlarrHTTPClient(f"http://{host}:{port}", "test-api-key")
            location = client.download_redirect(
                "/1/download?"
                "link=YWJjZA%3D%3D"
                "&file=Chekhov.torrent"
            )
            with self.assertRaisesRegex(OperationError, "invalid Prowlarr download route"):
                client.download_redirect("https://attacker.invalid/1/download?link=x&file=y")
            with self.assertRaisesRegex(OperationError, "invalid Prowlarr download route"):
                client.download_redirect(
                    "/1/download?link=https%3A%2F%2Fattacker.invalid&file=x.torrent"
                )
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(location, f"magnet:?xt=urn:btih:{infohash}")
        self.assertEqual(
            requests,
            [
                {
                    "path": "/1/download",
                    "query": {
                        "link": ["YWJjZA=="],
                        "file": ["Chekhov.torrent"],
                    },
                    "api_key": "test-api-key",
                }
            ],
        )

    def test_prowlarr_health_rejects_reported_health_problems(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            problems: list[dict[str, str]] = []

            def do_GET(self) -> None:
                path = urlparse(self.path).path
                if path == "/api/v1/health":
                    value = self.problems
                elif path == "/api/v1/indexer":
                    value = [{"id": 1, "name": "RuTracker", "enable": True}]
                else:
                    value = []
                body = json.dumps(value).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            client = ProwlarrHTTPClient(f"http://{host}:{port}", "test-api-key")
            client.health()
            Handler.problems = [
                {"type": "warning", "message": "indexer unavailable"}
            ]
            with self.assertRaisesRegex(OperationError, "health problems"):
                client.health()
        finally:
            server.shutdown()
            server.server_close()

    def test_prowlarr_health_ignores_update_warning_but_checks_rutracker(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            disabled = False
            backend_down = False

            def do_GET(self) -> None:
                path = urlparse(self.path).path
                if self.backend_down:
                    self.send_response(503)
                    self.end_headers()
                    return
                if path == "/api/v1/health":
                    value = [{"source": "UpdateCheck", "type": "warning"}]
                elif path == "/api/v1/indexer":
                    value = [{"id": 1, "name": "RuTracker", "enable": True}]
                elif path == "/api/v1/indexerstatus" and self.disabled:
                    value = [{"indexerId": 1, "disabledTill": "9999-01-01T00:00:00Z"}]
                else:
                    value = []
                body = json.dumps(value).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            client = ProwlarrHTTPClient(f"http://{host}:{port}", "test-api-key")
            client.health()
            Handler.disabled = True
            with self.assertRaisesRegex(OperationError, "required RuTracker indexer is unavailable"):
                client.health()
            Handler.backend_down = True
            with self.assertRaisesRegex(OperationError, "upstream returned HTTP 503"):
                client.health()
        finally:
            server.shutdown()
            server.server_close()

    def test_empty_search_rejects_disabled_rutracker_after_search(self) -> None:
        requests: list[str] = []

        class Handler(BaseHTTPRequestHandler):
            indexers = [{"id": 1, "name": "RuTracker", "enable": True}]
            statuses: list[dict[str, object]] = []

            def do_GET(self) -> None:
                path = urlparse(self.path).path
                requests.append(path)
                if path == "/api/v1/indexer":
                    value = self.indexers
                elif path == "/api/v1/indexerstatus":
                    value = self.statuses
                else:
                    value = []
                body = json.dumps(value).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            client = ProwlarrHTTPClient(f"http://{host}:{port}", "secret-api-key")
            adapter = ProwlarrReleaseAdapter(client, FakeRouteGuard())
            self.assertEqual(adapter.search(["Кроткая"]), [])
            Handler.statuses = [{
                "indexerId": 1, "disabledTill": "9999-01-01T00:00:00Z",
                "message": "secret-api-key upstream body",
            }]
            with self.assertRaises(OperationError) as caught:
                adapter.search(["Кроткая"])
            self.assertEqual(str(caught.exception), "required RuTracker indexer is unavailable")
            self.assertEqual(requests, [
                "/api/v1/search", "/api/v1/indexer", "/api/v1/indexerstatus",
                "/api/v1/search", "/api/v1/indexer", "/api/v1/indexerstatus",
            ])
            with tempfile.TemporaryDirectory() as temporary_directory:
                operations = AudiobookOperations.open(
                    Path(temporary_directory) / "state.sqlite3", release_adapter=adapter
                )
                try:
                    with self.assertRaisesRegex(
                        OperationError, "required RuTracker indexer is unavailable"
                    ):
                        MCPAdapter(operations).call("release_search", {"queries": ["Кроткая"]})
                finally:
                    operations.close()
            Handler.statuses = [{"indexerId": 2, "disabledTill": "9999-01-01T00:00:00Z"}]
            self.assertEqual(adapter.search(["Кроткая"]), [])
            Handler.statuses = [{"indexerId": 1, "disabledTill": "2000-01-01T00:00:00Z"}]
            self.assertEqual(adapter.search(["Кроткая"]), [])
            Handler.statuses = [{"indexerId": 1, "disabledTill": "bad secret"}]
            with self.assertRaisesRegex(OperationError, "invalid indexer status"):
                adapter.search(["Кроткая"])
            Handler.indexers = [{"id": 1, "name": "RuTracker", "enable": False}]
            with self.assertRaisesRegex(OperationError, "required RuTracker indexer is unavailable"):
                adapter.search(["Кроткая"])
        finally:
            server.shutdown()
            server.server_close()

    def test_tracker_http_failure_is_bounded_and_does_not_expose_the_api_key(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b"upstream body with accidental detail")

            def log_message(self, _format: str, *_args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            client = ProwlarrHTTPClient(f"http://{host}:{port}", "secret-api-key")
            with self.assertRaises(OperationError) as caught:
                client.search("Кроткая")
        finally:
            server.shutdown()
            server.server_close()

        message = str(caught.exception)
        self.assertEqual(message, "upstream returned HTTP 503")
        self.assertNotIn("secret-api-key", message)
        self.assertNotIn("accidental detail", message)


if __name__ == "__main__":
    unittest.main()
