"""Socket-free Prowlarr client evidence; no claims about live search causes."""

import io
import http.client
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from audiobook_ops import acquisition
from audiobook_ops.interface import OperationError


class MemoryResponse(io.BytesIO):
    def __init__(self, body, headers=None):
        super().__init__(body)
        self.headers = headers or {}


class ProwlarrMemoryTest(unittest.TestCase):
    def test_search_reports_only_observed_http_status(self):
        client = acquisition.ProwlarrHTTPClient("http://synthetic.invalid", "API_KEY_SENTINEL")
        for status in (401, 403, 503):
            with self.subTest(status=status):
                body = io.BytesIO(b"UPSTREAM_BODY_SENTINEL")
                error = HTTPError("http://URL_SENTINEL", status, "EXCEPTION_SENTINEL", {}, body)
                with patch.object(acquisition, "urlopen", side_effect=error):
                    with self.assertRaises(OperationError) as caught:
                        client.search("QUERY_SENTINEL")
                self.assertEqual(str(caught.exception), f"upstream returned HTTP {status}")
                self.assertTrue(body.closed)

    def test_search_distinguishes_timeout_from_transport_failure(self):
        client = acquisition.ProwlarrHTTPClient("http://synthetic.invalid", "API_KEY_SENTINEL")
        for error, expected in (
            (TimeoutError("EXCEPTION_SENTINEL"), "upstream request timed out"),
            (URLError(TimeoutError("EXCEPTION_SENTINEL")), "upstream request timed out"),
            (URLError("EXCEPTION_SENTINEL"), "upstream transport failed"),
        ):
            with self.subTest(error=type(error).__name__):
                with patch.object(acquisition, "urlopen", side_effect=error):
                    with self.assertRaises(OperationError) as caught:
                        client.search("QUERY_SENTINEL")
                self.assertEqual(str(caught.exception), expected)

    def test_search_rejects_invalid_json_encoding_with_safe_error(self):
        client = acquisition.ProwlarrHTTPClient("http://synthetic.invalid", "API_KEY_SENTINEL")
        with patch.object(acquisition, "urlopen", return_value=MemoryResponse(b"\xffSECRET_SENTINEL")):
            with self.assertRaises(Exception) as caught:
                client.search("QUERY_SENTINEL")
        self.assertIsInstance(caught.exception, OperationError)
        self.assertEqual(str(caught.exception), "Prowlarr returned invalid JSON")

    def test_search_reports_invalid_response_framing_safely(self):
        client = acquisition.ProwlarrHTTPClient("http://synthetic.invalid", "API_KEY_SENTINEL")
        for length in ("invalid LENGTH_SENTINEL", "-1"):
            with self.subTest(length=length):
                with patch.object(acquisition, "urlopen", return_value=MemoryResponse(b"[]", {"Content-Length": length})):
                    with self.assertRaises(Exception) as caught:
                        client.search("QUERY_SENTINEL")
                self.assertIsInstance(caught.exception, OperationError)
                self.assertEqual(str(caught.exception), "invalid upstream response")
        for error in (http.client.IncompleteRead(b"BODY_SENTINEL", 10), http.client.BadStatusLine("HEADER_SENTINEL")):
            with self.subTest(error=type(error).__name__):
                with patch.object(acquisition, "urlopen", side_effect=error):
                    with self.assertRaises(Exception) as caught:
                        client.search("QUERY_SENTINEL")
                self.assertIsInstance(caught.exception, OperationError)
                self.assertEqual(str(caught.exception), "invalid upstream response")

    def test_empty_search_remains_success_and_invalid_data_stays_distinct(self):
        client = acquisition.ProwlarrHTTPClient("http://synthetic.invalid", "API_KEY_SENTINEL")
        with patch.object(acquisition, "urlopen", side_effect=[
            MemoryResponse(b"[]"),
            MemoryResponse(b'[ {"id": 1, "name": "RuTracker", "enable": true} ]'),
            MemoryResponse(b"[]"),
        ]):
            self.assertEqual(client.search("QUERY_SENTINEL"), [])
        for body, headers, expected in (
            (b"not JSON", {}, "Prowlarr returned invalid JSON"),
            (b"{}", {}, "Prowlarr returned an invalid search result"),
            (b"[1]", {}, "Prowlarr returned an invalid search result"),
            (b"[]", {"Content-Length": "2097153"}, "upstream response exceeds the size limit"),
            (b"x" * 2097153, {}, "upstream response exceeds the size limit"),
        ):
            with self.subTest(expected=expected):
                with patch.object(acquisition, "urlopen", return_value=MemoryResponse(body, headers)):
                    with self.assertRaises(OperationError) as caught:
                        client.search("QUERY_SENTINEL")
                self.assertEqual(str(caught.exception), expected)
