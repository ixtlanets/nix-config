from __future__ import annotations

from copy import deepcopy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import unittest

from audiobook_ops.audiobookshelf import (
    AudiobookshelfAdapter,
    AudiobookshelfHTTPClient,
    AbsBytesResponse,
)
from audiobook_ops.interface import CatalogMutationError, OperationError


class FakeCoverFetcher:
    def fetch(self, source_url: str) -> dict[str, object]:
        return {
            "source_url": source_url,
            "final_url": source_url,
            "checksum": hashlib.sha256(b"new-cover").hexdigest(),
            "mime_type": "image/jpeg",
            "filename": "cover.jpg",
            "width": 1000,
            "height": 1000,
            "_content_b64": "bmV3LWNvdmVy",
        }


class MemoryAbsHTTP:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []
        self.cover = b"old-cover"
        self.fail_cover_upload = False
        self.item = {
            "id": "item-one",
            "libraryId": "library-one",
            "path": "/readmeabook/Автор/Книга",
            "relPath": "Автор/Книга",
            "updatedAt": 100,
            "mediaType": "book",
            "media": {
                "metadata": {
                    "title": "Кроткая",
                    "subtitle": "Повесть",
                    "authors": [
                        {"id": "author-one", "name": "Фёдор Достоевский"},
                        {"id": "author-two", "name": "Другой автор"},
                    ],
                    "narrators": ["Иван", "Пётр"],
                    "series": [
                        {"id": "series-one", "name": "Русская классика", "sequence": "4.5"},
                        {"id": "series-two", "name": "Повести", "sequence": "1-2"},
                    ],
                    "genres": ["Классика"],
                    "publishedYear": "1876",
                    "publishedDate": "1876-11",
                    "publisher": "Издатель",
                    "description": "Описание",
                    "isbn": "isbn-one",
                    "asin": "asin-one",
                    "language": "ru",
                    "explicit": False,
                    "abridged": False,
                },
                "coverPath": "/metadata/items/item-one/cover.jpg",
                "tags": ["русская литература"],
            },
        }
        self.second = deepcopy(self.item)
        self.second["id"] = "item-two"
        self.second["path"] = "/readmeabook/Автор/Книга 2"
        self.second["media"]["metadata"]["narrators"] = []
        self.second["media"]["metadata"]["series"][0]["sequence"] = None
        self.third = deepcopy(self.item)
        self.third["id"] = "item-three"
        self.third["libraryId"] = "library-two"
        self.third["path"] = "/audiobooks/Фёдор Достоевский/Идиот"
        self.third["media"]["metadata"]["title"] = "Идиот"

    @staticmethod
    def _minified(item: dict[str, object]) -> dict[str, object]:
        listed = deepcopy(item)
        listed["media"]["metadata"].pop("authors", None)
        return listed

    def json(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> object:
        self.calls.append((method, path, deepcopy(payload)))
        if (method, path) == ("GET", "/api/libraries"):
            return {
                "libraries": [
                    {"id": "library-one", "name": "Books", "mediaType": "book"},
                    {"id": "library-two", "name": "More Books", "mediaType": "book"},
                    {"id": "podcasts", "name": "Podcasts", "mediaType": "podcast"},
                ]
            }
        if method == "GET" and path.startswith("/api/libraries/library-one/items?"):
            return {
                "results": [self._minified(self.item), self._minified(self.second)],
                "total": 2,
            }
        if method == "GET" and path.startswith("/api/libraries/library-two/items?"):
            return {"results": [self._minified(self.third)], "total": 1}
        if method == "GET" and "/authors?" in path:
            return {"results": [{"id": "author-one", "name": "Фёдор Достоевский"}], "total": 1}
        if method == "GET" and "/series?" in path:
            return {"results": [{"id": "series-one", "name": "Русская классика"}], "total": 1}
        if (method, path) == ("GET", "/api/items/item-one?expanded=1"):
            return deepcopy(self.item)
        if (method, path) == ("GET", "/api/items/item-two?expanded=1"):
            return deepcopy(self.second)
        if (method, path) == ("GET", "/api/items/item-three?expanded=1"):
            return deepcopy(self.third)
        if (method, path) == ("PATCH", "/api/items/item-one/media"):
            metadata = payload.get("metadata", {})
            self.item["media"]["metadata"].update(deepcopy(metadata))
            if "tags" in payload:
                self.item["media"]["tags"] = deepcopy(payload["tags"])
            self.item["updatedAt"] += 1
            return {"updated": True, "libraryItem": deepcopy(self.item)}
        if (method, path) == ("DELETE", "/api/items/item-one/cover"):
            self.item["media"]["coverPath"] = None
            self.cover = b""
            self.item["updatedAt"] += 1
            return {}
        raise AssertionError(f"unexpected ABS call: {method} {path}")

    def bytes(self, method: str, path: str, maximum_bytes: int) -> AbsBytesResponse:
        self.calls.append((method, path, maximum_bytes))
        if (method, path) != ("GET", "/api/items/item-one/cover?raw=1"):
            raise AssertionError(f"unexpected ABS byte call: {method} {path}")
        return AbsBytesResponse("image/jpeg", self.cover)

    def upload_cover(
        self,
        path: str,
        *,
        filename: str,
        mime_type: str,
        content: bytes,
    ) -> object:
        self.calls.append(("POST", path, (filename, mime_type, content)))
        if self.fail_cover_upload and content == b"new-cover":
            raise OperationError("simulated cover failure")
        self.cover = content
        self.item["media"]["coverPath"] = f"/metadata/items/item-one/{filename}"
        self.item["updatedAt"] += 1
        return {"success": True, "cover": self.item["media"]["coverPath"]}


class AudiobookshelfAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.http = MemoryAbsHTTP()
        self.adapter = AudiobookshelfAdapter(self.http, FakeCoverFetcher())

    def test_full_catalog_search_and_audit_cover_every_book_library(self) -> None:
        items = self.adapter.search("Федор Кроткая")
        audit = self.adapter.audit([])

        self.assertEqual(
            [item["item_id"] for item in items],
            ["item-one", "item-two", "item-three"],
        )
        exact = self.adapter.get_item("library-one", "item-one")
        self.assertEqual(items[0]["revision"], exact["revision"])
        self.assertEqual(exact["metadata"]["authors"], ["Фёдор Достоевский", "Другой автор"])
        self.assertEqual(exact["metadata"]["narrators"], ["Иван", "Пётр"])
        self.assertEqual(
            exact["metadata"]["series"],
            [
                {"name": "Русская классика", "sequence": "4.5"},
                {"name": "Повести", "sequence": "1-2"},
            ],
        )
        self.assertEqual(exact["metadata"]["tags"], ["русская литература"])
        kinds = [issue["kind"] for issue in audit["issues"]]
        self.assertIn("missing_narrators", kinds)
        self.assertIn("incomplete_series", kinds)
        self.assertIn("suspected_duplicate", kinds)
        requested_paths = [path for _method, path, _payload in self.http.calls]
        self.assertTrue(any("/authors?" in path for path in requested_paths))
        self.assertTrue(any("/series?" in path for path in requested_paths))
        self.assertTrue(any("library-two/items?" in path for path in requested_paths))
        self.assertFalse(any("podcasts/items" in path for path in requested_paths))

    def test_omitted_empty_array_fields_normalize_to_empty_arrays(self) -> None:
        del self.http.item["media"]["metadata"]["narrators"]
        del self.http.item["media"]["metadata"]["genres"]

        item = next(
            item
            for item in self.adapter.search("Кроткая")
            if item["item_id"] == "item-one"
        )

        self.assertEqual(item["metadata"]["narrators"], [])
        self.assertEqual(item["metadata"]["genres"], [])

    def test_partial_metadata_and_cover_update_round_trips_without_moving_item(self) -> None:
        current = self.adapter.get_item("library-one", "item-one")
        target = {
            key: current[key]
            for key in ("library_id", "item_id", "path", "revision")
        }
        rollback = self.adapter.snapshot_exact(target)
        desired = deepcopy(rollback)
        desired["metadata"]["title"] = "Кроткая — новая редакция"
        desired["metadata"]["subtitle"] = None
        desired["metadata"]["authors"] = ["Фёдор Достоевский", "Редактор"]
        desired["metadata"]["narrators"] = ["Новый чтец"]
        desired["metadata"]["series"] = [
            {"name": "Русская классика", "sequence": "1-2"}
        ]
        desired["cover"] = self.adapter.prepare_cover(
            "https://covers.example/new.jpg"
        )

        updated = self.adapter.apply_exact(target, desired, rollback)

        self.assertEqual(updated["path"], target["path"])
        self.assertEqual(updated["metadata"], {key: value for key, value in desired["metadata"].items()})
        self.assertEqual(
            updated["cover"]["checksum"], hashlib.sha256(b"new-cover").hexdigest()
        )
        patch = next(
            payload
            for method, path, payload in self.http.calls
            if method == "PATCH" and path.endswith("/media")
        )
        self.assertEqual(patch["metadata"]["authors"], [{"name": "Фёдор Достоевский"}, {"name": "Редактор"}])
        self.assertEqual(
            patch["metadata"]["series"],
            [{"name": "Русская классика", "sequence": "1-2"}],
        )
        self.assertNotIn("publisher", patch["metadata"])

    def test_cover_failure_compensates_metadata_and_reports_the_result(self) -> None:
        current = self.adapter.get_item("library-one", "item-one")
        target = {
            key: current[key]
            for key in ("library_id", "item_id", "path", "revision")
        }
        rollback = self.adapter.snapshot_exact(target)
        desired = deepcopy(rollback)
        desired["metadata"]["title"] = "Should roll back"
        desired["cover"] = self.adapter.prepare_cover(
            "https://covers.example/new.jpg"
        )
        self.http.fail_cover_upload = True

        with self.assertRaises(CatalogMutationError) as caught:
            self.adapter.apply_exact(target, desired, rollback)

        self.assertTrue(caught.exception.compensated)
        restored = self.adapter.get_item("library-one", "item-one")
        self.assertEqual(restored["metadata"]["title"], "Кроткая")
        self.assertEqual(restored["cover"]["checksum"], rollback["cover"]["checksum"])

    def test_explicit_cover_clear_uses_only_the_exact_item_delete_route(self) -> None:
        current = self.adapter.get_item("library-one", "item-one")
        target = {
            key: current[key]
            for key in ("library_id", "item_id", "path", "revision")
        }
        rollback = self.adapter.snapshot_exact(target)
        desired = deepcopy(rollback)
        desired["cover"] = None

        updated = self.adapter.apply_exact(target, desired, rollback)

        self.assertIsNone(updated["cover"])
        self.assertIn(
            ("DELETE", "/api/items/item-one/cover", None), self.http.calls
        )


class AudiobookshelfHTTPContractTests(unittest.TestCase):
    def test_pinned_routes_payloads_and_bearer_transport(self) -> None:
        requests: list[dict[str, object]] = []

        class Handler(BaseHTTPRequestHandler):
            def _handle(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                requests.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "authorization": self.headers.get("Authorization"),
                        "content_type": self.headers.get("Content-Type"),
                        "body": body,
                    }
                )
                if self.path == "/api/items/item-one/cover?raw=1":
                    response = b"cover-bytes"
                    content_type = "image/jpeg"
                elif self.command == "DELETE":
                    response = b"OK"
                    content_type = "text/plain; charset=utf-8"
                else:
                    response = json.dumps(
                        {"libraries": []}
                        if self.command == "GET"
                        else {"success": True},
                        ensure_ascii=False,
                    ).encode()
                    content_type = "application/json"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            do_GET = _handle
            do_PATCH = _handle
            do_POST = _handle
            do_DELETE = _handle

            def log_message(self, _format: str, *_args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        client = AudiobookshelfHTTPClient(
            f"http://{host}:{port}", "test-abs-token"
        )
        try:
            self.assertEqual(client.json("GET", "/api/libraries"), {"libraries": []})
            self.assertEqual(
                client.json(
                    "PATCH",
                    "/api/items/item-one/media",
                    {"metadata": {"title": "Кроткая"}},
                ),
                {"success": True},
            )
            self.assertEqual(
                client.bytes("GET", "/api/items/item-one/cover?raw=1", 100).body,
                b"cover-bytes",
            )
            self.assertEqual(
                client.upload_cover(
                    "/api/items/item-one/cover",
                    filename="cover.jpg",
                    mime_type="image/jpeg",
                    content=b"jpeg",
                ),
                {"success": True},
            )
            self.assertEqual(client.json("DELETE", "/api/items/item-one/cover"), {})
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(
            [(request["method"], request["path"]) for request in requests],
            [
                ("GET", "/api/libraries"),
                ("PATCH", "/api/items/item-one/media"),
                ("GET", "/api/items/item-one/cover?raw=1"),
                ("POST", "/api/items/item-one/cover"),
                ("DELETE", "/api/items/item-one/cover"),
            ],
        )
        self.assertTrue(
            all(
                request["authorization"] == "Bearer test-abs-token"
                for request in requests
            )
        )
        patch = json.loads(requests[1]["body"])
        self.assertEqual(patch, {"metadata": {"title": "Кроткая"}})
        self.assertIn('filename="cover.jpg"', requests[3]["body"].decode())
        self.assertNotIn(
            "test-abs-token",
            b"".join(request["body"] for request in requests).decode(errors="ignore"),
        )


if __name__ == "__main__":
    unittest.main()
