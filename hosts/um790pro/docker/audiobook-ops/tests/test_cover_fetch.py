from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import tempfile
import unittest

from audiobook_ops.cover import CoverFetcher, CoverResponse, SubprocessImageDecoder
from audiobook_ops.interface import OperationError


class FakeResolver:
    def __init__(self, addresses: dict[str, list[str]]) -> None:
        self.addresses = addresses
        self.calls: list[tuple[str, int]] = []

    def resolve(self, hostname: str, port: int) -> list[str]:
        self.calls.append((hostname, port))
        return self.addresses.get(hostname, [])


class FakeHTTP:
    def __init__(self, responses: dict[str, CoverResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, int, tuple[str, ...]]] = []

    def fetch(
        self, url: str, maximum_bytes: int, addresses: list[str]
    ) -> CoverResponse:
        self.calls.append((url, maximum_bytes, tuple(addresses)))
        return self.responses[url]


class FakeDecoder:
    def __init__(self, width: int = 1200, height: int = 1200) -> None:
        self.width = width
        self.height = height
        self.calls: list[tuple[bytes, str]] = []

    def inspect(self, content: bytes, mime_type: str) -> tuple[int, int]:
        self.calls.append((content, mime_type))
        return self.width, self.height


class FakeRouteGuard:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.calls = 0

    def require(self) -> None:
        self.calls += 1
        if not self.available:
            raise OperationError("required VLESS route is unavailable")


class CoverFetcherTests(unittest.TestCase):
    def test_https_redirect_chain_is_revalidated_and_returns_bounded_artifact(self) -> None:
        content = b"decoded jpeg fixture"
        resolver = FakeResolver(
            {"covers.example": ["8.8.8.8"], "cdn.example": ["1.1.1.1"]}
        )
        http = FakeHTTP(
            {
                "https://covers.example/book": CoverResponse(
                    status=302,
                    content_type=None,
                    location="https://cdn.example/final.jpg",
                    body=b"",
                ),
                "https://cdn.example/final.jpg": CoverResponse(
                    status=200,
                    content_type="image/jpeg",
                    location=None,
                    body=content,
                ),
            }
        )
        decoder = FakeDecoder()
        guard = FakeRouteGuard()

        result = CoverFetcher(http, resolver, decoder, guard).fetch(
            "https://covers.example/book"
        )

        self.assertEqual(
            resolver.calls,
            [("covers.example", 443), ("cdn.example", 443)],
        )
        self.assertEqual(result["checksum"], hashlib.sha256(content).hexdigest())
        self.assertEqual(result["filename"], "cover.jpg")
        self.assertEqual(result["width"], 1200)
        self.assertEqual(result["height"], 1200)
        self.assertEqual(result["_content_b64"], base64.b64encode(content).decode())
        self.assertEqual(guard.calls, 2)

    def test_private_tailnet_metadata_and_redirect_destinations_fail_closed(self) -> None:
        unsafe = (
            "127.0.0.1",
            "10.0.0.1",
            "169.254.169.254",
            "100.64.0.1",
            "::1",
        )
        for address in unsafe:
            with self.subTest(address=address):
                http = FakeHTTP({})
                fetcher = CoverFetcher(
                    http,
                    FakeResolver({"covers.example": [address]}),
                    FakeDecoder(),
                    FakeRouteGuard(),
                )
                with self.assertRaisesRegex(OperationError, "cover destination"):
                    fetcher.fetch("https://covers.example/book.jpg")
                self.assertEqual(http.calls, [])

        http = FakeHTTP(
            {
                "https://covers.example/book.jpg": CoverResponse(
                    status=302,
                    content_type=None,
                    location="https://private.example/cover.jpg",
                    body=b"",
                )
            }
        )
        fetcher = CoverFetcher(
            http,
            FakeResolver(
                {"covers.example": ["8.8.8.8"], "private.example": ["10.1.2.3"]}
            ),
            FakeDecoder(),
            FakeRouteGuard(),
        )
        with self.assertRaisesRegex(OperationError, "cover destination"):
            fetcher.fetch("https://covers.example/book.jpg")

    def test_invalid_scheme_body_mime_dimensions_and_redirect_count_fail_closed(self) -> None:
        resolver = FakeResolver({"covers.example": ["8.8.8.8"]})
        with self.assertRaisesRegex(OperationError, "HTTPS"):
            CoverFetcher(FakeHTTP({}), resolver, FakeDecoder(), FakeRouteGuard()).fetch(
                "http://covers.example/book.jpg"
            )

        class RejectingDecoder:
            def inspect(self, _content: bytes, _mime_type: str) -> tuple[int, int]:
                raise OperationError("cover image decode failed")

        cases = (
            (
                "cover response exceeds",
                CoverResponse(200, "image/jpeg", None, b"12345"),
                {"max_bytes": 4},
                FakeDecoder(),
            ),
            (
                "unsupported cover MIME",
                CoverResponse(200, "text/html", None, b"<html>"),
                {},
                FakeDecoder(),
            ),
            (
                "cover dimensions",
                CoverResponse(200, "image/png", None, b"png"),
                {},
                FakeDecoder(5000, 5000),
            ),
            (
                "cover image decode failed",
                CoverResponse(200, "image/webp", None, b"polyglot-or-malformed"),
                {},
                RejectingDecoder(),
            ),
        )
        for expected, response, options, decoder in cases:
            with self.subTest(expected=expected):
                fetcher = CoverFetcher(
                    FakeHTTP({"https://covers.example/book.jpg": response}),
                    resolver,
                    decoder,
                    FakeRouteGuard(),
                    **options,
                )
                with self.assertRaisesRegex(OperationError, expected):
                    fetcher.fetch("https://covers.example/book.jpg")

        redirect = CoverResponse(
            302, None, "https://covers.example/book.jpg", b""
        )
        with self.assertRaisesRegex(OperationError, "redirect limit"):
            CoverFetcher(
                FakeHTTP({"https://covers.example/book.jpg": redirect}),
                resolver,
                FakeDecoder(),
                FakeRouteGuard(),
                max_redirects=1,
            ).fetch("https://covers.example/book.jpg")

    def test_vless_failure_stops_before_dns_or_https(self) -> None:
        resolver = FakeResolver({"covers.example": ["8.8.8.8"]})
        http = FakeHTTP({})

        with self.assertRaisesRegex(OperationError, "VLESS route"):
            CoverFetcher(
                http, resolver, FakeDecoder(), FakeRouteGuard(available=False)
            ).fetch("https://covers.example/book.jpg")

        self.assertEqual(resolver.calls, [])
        self.assertEqual(http.calls, [])

    def test_subprocess_decoder_requires_matching_codec_and_complete_decode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            probe = root / "ffprobe"
            decoder = root / "ffmpeg"
            probe.write_text(
                "#!/usr/bin/env python3\n"
                "import json\n"
                "print(json.dumps({'streams':[{'codec_name':'mjpeg','width':800,'height':600}]}))\n"
            )
            decoder.write_text("#!/bin/sh\nexit 0\n")
            probe.chmod(0o755)
            decoder.chmod(0o755)
            image_decoder = SubprocessImageDecoder(str(probe), str(decoder))

            self.assertEqual(
                image_decoder.inspect(b"jpeg fixture", "image/jpeg"), (800, 600)
            )
            with self.assertRaisesRegex(OperationError, "MIME"):
                image_decoder.inspect(b"not png", "image/png")

            decoder.write_text("#!/bin/sh\nexit 1\n")
            with self.assertRaisesRegex(OperationError, "decode failed"):
                image_decoder.inspect(b"broken jpeg", "image/jpeg")


if __name__ == "__main__":
    unittest.main()
