#!/usr/bin/env python3

import subprocess
import tempfile
import unittest
from pathlib import Path


BUNDLE_DIR = Path(__file__).resolve().parents[1]
PATCHER = BUNDLE_DIR / "scripts" / "patch-readmeabook-transmission.js"


class ReadMeABookImagePatchTest(unittest.TestCase):
    def test_tracker_errors_remain_nonterminal_but_local_errors_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            chunk = root / "server" / "chunks" / "app.js"
            chunk.parent.mkdir(parents=True)
            chunk.write_text(
                'mapStatus(e,t){return t>0?"failed":({0:"paused",4:"downloading"})[e]||"downloading"}',
                encoding="utf-8",
            )
            request_route = root / "server" / "chunks" / "request.js"
            request_route.write_text(
                'let E=y.RMABLogger.create("API.RequestById");'
                'return b.NextResponse.json({success:!0,request:s})',
                encoding="utf-8",
            )

            first = subprocess.run(
                ["node", str(PATCHER), str(root)],
                check=False,
                capture_output=True,
                text=True,
            )
            second = subprocess.run(
                ["node", str(PATCHER), str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("patched 1 Transmission status mapper", first.stdout)
            self.assertIn("patched 1 request serializer", first.stdout)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("already patched 1 Transmission status mapper", second.stdout)
            self.assertIn("already patched 1 request serializer", second.stdout)
            self.assertIn('return t===3?"failed":', chunk.read_text(encoding="utf-8"))
            self.assertNotIn('return t>0?"failed":', chunk.read_text(encoding="utf-8"))
            request_source = request_route.read_text(encoding="utf-8")
            self.assertIn("torrentSizeBytes", request_source)
            self.assertIn(".toString()", request_source)
            self.assertNotIn("request:s})", request_source)

    def test_unknown_upstream_layout_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = subprocess.run(
                ["node", str(PATCHER), tempdir],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no Transmission status mapper found", result.stderr)


if __name__ == "__main__":
    unittest.main()
