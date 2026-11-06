#!/usr/bin/env python3
"""Real helper + ffmpeg against a loopback-only API2 fixture, no ASR/network service."""
import hashlib
import http.server
import io
import json
import os
import pathlib
import subprocess
import tempfile
import threading
import unittest
import wave

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "dotfiles/omarchy/bin/transcribe-media"


class HelperTests(unittest.TestCase):
    def test_api_sidecars_chunking_and_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            calls = []
            mode = ["valid"]

            class Handler(http.server.BaseHTTPRequestHandler):
                def do_POST(self):
                    self.assert_request = self.headers.get("Authorization") == "Bearer fixture-token"
                    length = int(self.headers["Content-Length"])
                    body = self.rfile.read(length)
                    with wave.open(io.BytesIO(body), "rb") as audio:
                        calls.append((self.path, self.assert_request, audio.getnframes(), audio.getframerate()))
                    self.send_response(200 if mode[0] != "error" else 503)
                    self.end_headers()
                    self.wfile.write({"valid": b'{"transcript":"Test words.","durationMs":123}',
                                      "empty": b'{"transcript":""}', "invalid": b'not json',
                                      "error": b'private server diagnostic'}[mode[0]])

                def log_message(self, *args):
                    pass

            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            discovery = home / "Library/Application Support/hex/local-api.json"
            discovery.parent.mkdir(parents=True)
            config = {"apiVersion": "2", "port": server.server_port, "token": "fixture-token"}
            discovery.write_text(json.dumps(config))
            media = home / "meeting.wav"
            with wave.open(str(media), "wb") as audio:
                audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                audio.writeframes(b"\0\0" * (121 * 16000))
            before = hashlib.sha256(media.read_bytes()).hexdigest()
            env = dict(os.environ, HOME=str(home), HTTP_PROXY="http://invalid:1", http_proxy="http://invalid:1")

            def run(*args):
                return subprocess.run(["bash", str(SCRIPT), *args, str(media)], env=env,
                                      capture_output=True, text=True, timeout=30)

            result = run()
            self.assertEqual(result.returncode, 0, result.stderr)
            output = home / "meeting.transcript.json"
            markdown = home / "meeting.transcript.md"
            value = json.loads(output.read_text())
            self.assertEqual(value["modelId"]["predefined"], "parakeet_v3")
            self.assertEqual(value["language"], "ru")
            self.assertEqual(value["timing"], "coarse-audio-chunks")
            self.assertFalse(value["capabilities"]["diarization"])
            self.assertFalse(value["capabilities"]["alignedTimestamps"])
            self.assertEqual([(s["start"], s["end"], s["speakerId"]) for s in value["segments"]],
                             [(0, 120, None), (120, 121, None)])
            self.assertEqual([c[2] for c in calls], [120 * 16000, 16000])
            self.assertTrue(all(c[0] == "/transcriptions?model=parakeet_v3&language=ru" and c[1] for c in calls))
            self.assertIn("[00:02:00-00:02:01] Test words.", markdown.read_text())
            self.assertIn("not speech-aligned", markdown.read_text())
            self.assertNotIn("Speaker 1", markdown.read_text())
            previous = output.read_bytes()
            self.assertNotEqual(run().returncode, 0)
            self.assertEqual(len(calls), 2)
            for failure in ("invalid", "empty", "error"):
                mode[0] = failure
                result = run("--force")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(output.read_bytes(), previous)
                self.assertNotIn("fixture-token", result.stderr)
                self.assertNotIn("private server diagnostic", result.stderr)
                self.assertFalse(list(home.glob(".meeting.transcript.*")))
            mode[0] = "valid"
            self.assertEqual(run("--force").returncode, 0)
            config["apiVersion"] = "99"
            discovery.write_text(json.dumps(config))
            self.assertNotEqual(run("--force").returncode, 0)
            discovery.unlink()
            self.assertNotEqual(run("--force").returncode, 0)
            self.assertEqual(hashlib.sha256(media.read_bytes()).hexdigest(), before)
            unsupported = home / "bad.aiff"
            unsupported.write_bytes(b"not audio")
            result = subprocess.run(["bash", str(SCRIPT), str(unsupported)], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
