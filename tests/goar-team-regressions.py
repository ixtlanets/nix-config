#!/usr/bin/env python3
"""Exercise the artifact validator on private copies, never mutate the candidate."""

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("goar_contract", ROOT / "tests/goar-team-links.py")
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)


class ArtifactRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="goar-contract-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ("secrets/vless", "secrets/proxy/goar-team"):
            shutil.copytree(ROOT / folder, self.root / folder)
        self.profiles = self.root / "secrets/vless"
        self.bundle = self.root / "secrets/proxy/goar-team"

    def reject(self, expected):
        with self.assertRaisesRegex(CONTRACT.ContractError, expected):
            CONTRACT.validate(self.root)

    def edit_json(self, path, change):
        data = json.loads(path.read_text())
        change(data)
        path.write_text(json.dumps(data))

    def test_complete_candidate(self):
        self.assertEqual(CONTRACT.validate(self.root), (13, 8, 13))

    def test_missing_link_for_every_named_identity(self):
        for name in CONTRACT.BASELINE["names"]:
            with self.subTest(identity=name):
                path = self.profiles / (name + ".vless.txt")
                raw = path.read_bytes()
                path.unlink()
                try:
                    self.reject("link inventory missing/extra")
                finally:
                    path.write_bytes(raw)

    def test_missing_qr(self):
        (self.profiles / "nik-macos.qr.png").unlink()
        self.reject("missing QR")

    def test_extra_discovered_link(self):
        shutil.copyfile(self.profiles / "nik-ios.vless.txt", self.profiles / "unexpected.vless.txt")
        self.reject("extra/service link")

    def test_service_identity_is_not_deliverable(self):
        shutil.copyfile(self.profiles / "nik-ios.vless.txt", self.profiles / "RealityEZPZ.vless.txt")
        self.reject("extra/service link")

    def test_extra_discovered_qr(self):
        shutil.copyfile(self.profiles / "nik-ios.qr.png", self.profiles / "unexpected.qr.png")
        self.reject("extra/service QR")

    def test_extra_discovered_json(self):
        shutil.copyfile(self.profiles / "nik-ios.json", self.profiles / "unexpected.json")
        self.reject("extra JSON identity")

    def test_duplicate_link_identity(self):
        shutil.copyfile(self.profiles / "nik-ios.vless.txt", self.profiles / "nik-macos.vless.txt")
        self.reject("label mismatch/duplicate")

    def test_duplicate_target_outbound(self):
        path = self.profiles / "nik-ios.json"
        self.edit_json(path, lambda d: d["outbounds"].append(next(o for o in d["outbounds"] if o.get("server") == CONTRACT.SERVER)))
        self.reject("duplicate/non-VLESS target")

    def test_missing_json(self):
        (self.profiles / "nik-ios.json").unlink()
        self.reject("JSON inventory missing/extra")

    def test_wrong_json_port(self):
        path = self.profiles / "nik-ios.json"
        path.write_bytes(path.read_bytes().replace(b'"server_port": 24443', b'"server_port": 443'))
        self.reject("JSON authority/port")

    def test_fingerprint_parity(self):
        path = self.profiles / "nik-ios.json"
        path.write_bytes(path.read_bytes().replace(b'"fingerprint": "firefox"', b'"fingerprint": "chrome"'))
        self.reject("JSON/link parity")

    def test_qr_mismatch(self):
        shutil.copyfile(self.profiles / "nik-android.qr.png", self.profiles / "nik-ios.qr.png")
        self.reject("QR byte roundtrip")

    def test_link_credential_authority(self):
        from urllib.parse import urlsplit
        path = self.profiles / "nik-ios.vless.txt"
        source = urlsplit((self.profiles / "nik-android.vless.txt").read_text().strip())
        old = urlsplit(path.read_text().strip())
        path.write_text(path.read_text().replace(old.username, source.username))
        self.reject("authority mismatch")

    def test_wrong_link_port(self):
        path = self.profiles / "nik-ios.vless.txt"
        path.write_bytes(path.read_bytes().replace(b":24443?", b":443?"))
        self.reject("link endpoint")

    def test_config_port(self):
        path = self.bundle / "config"
        path.write_bytes(path.read_bytes().replace(b"port=24443\n", b"port=443\n"))
        self.reject("node/config port")

    def test_retained_old_mapping(self):
        path = self.bundle / "docker-compose.yml"
        path.write_text(path.read_text().replace("    - 443:8443\n", ""))
        self.reject("retained 443 mapping")

    def test_missing_alternate_mapping(self):
        path = self.bundle / "docker-compose.yml"
        path.write_text(path.read_text().replace('    - "24443:8443"\n', ""))
        self.reject("quoted alternate mapping")

    def test_duplicate_engine_name(self):
        path = self.bundle / "engine.conf"
        self.edit_json(path, lambda d: d["inbounds"][1]["users"].append(d["inbounds"][1]["users"][0]))
        self.reject("duplicate engine names")

    def test_duplicate_engine_credential(self):
        path = self.bundle / "engine.conf"
        def duplicate(d):
            d["inbounds"][1]["users"][1]["uuid"] = d["inbounds"][1]["users"][0]["uuid"]
        self.edit_json(path, duplicate)
        self.reject("duplicate engine credentials")

    def test_missing_engine_identity(self):
        self.edit_json(self.bundle / "engine.conf", lambda d: d["inbounds"][1]["users"].pop(0))
        self.reject("named engine inventory")

    def test_helper_user_drift(self):
        path = self.bundle / "users"
        path.write_text("\n".join(path.read_text().splitlines()[1:]) + "\n")
        self.reject("helper/engine users parity")

    def test_unrequested_routing_change(self):
        path = self.profiles / "nik-ios.json"
        path.write_bytes(path.read_bytes().replace(b'"download_detour": "direct"', b'"download_detour": "proxy"'))
        self.reject("JSON changed beyond port")

    def test_unrequested_engine_change(self):
        path = self.bundle / "engine.conf"
        self.edit_json(path, lambda d: d.update(log={"level": "debug"}))
        self.reject("original server identity/config changed")

    def test_unrequested_compose_image_change(self):
        path = self.bundle / "docker-compose.yml"
        path.write_text(path.read_text().replace("1.13.5", "latest"))
        self.reject("original server identity/config changed")


if __name__ == "__main__":
    unittest.main()
