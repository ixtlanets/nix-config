import importlib.util
import copy
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest


spec = importlib.util.spec_from_file_location(
    "manage", Path(__file__).parents[1] / "scripts/manage.py"
)
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


class WorkerStateTests(unittest.TestCase):
    def test_worker_state_omits_operator_only_subscription_fields(self):
        state = {
            "schema": 1,
            "entry": {"host": "notes.nikcode.xyz"},
            "subscriptions": [
                {
                    "label": "private-label",
                    "token": "private-token",
                    "hash": "a" * 64,
                    "format": "sing-box-ios-legacy",
                    "formats": ["sing-box-ios-legacy"],
                    "enabled": True,
                }
            ],
        }

        compact = manage.worker_state(state)

        self.assertEqual(compact["entry"], state["entry"])
        self.assertNotIn("label", compact["subscriptions"][0])
        self.assertNotIn("token", compact["subscriptions"][0])
        self.assertEqual(compact["subscriptions"][0]["hash"], "a" * 64)


class PilotStateTests(unittest.TestCase):
    def spec(self):
        return {
            "magic_dns_suffix": "example.ts.net",
            "nodes": [
                {"id": "france", "enabled": True, "protocol": "vless", "host": "192.0.2.1", "port": 443,
                 "server_name": "example.com", "public_key": "A" * 43, "short_id": "abcd"},
                {"id": "frankfurt", "enabled": True, "protocol": "vless", "host": "192.0.2.2", "port": 34443,
                 "server_name": "example.com", "public_key": "B" * 43, "short_id": "abcd"},
            ],
        }

    def four_node_state(self):
        # Deterministic public fixtures only; do not issue new pilot identities.
        state = {"schema": 1, **self.spec(), "devices": [], "operator_note": "not-for-renderer",
                 "subscription_hosts": ["config.nikcode.xyz", "subscriptions.nikcode.xyz"],
                 "rules_url": "https://subscriptions.nikcode.xyz/rules/geoip-ru-bdca5cdb44cdcf0940001e5952386822a6f4ffa8b2c8eea00340aa6f585c7f9d.srs"}
        state["nodes"].extend([
            {"id": "poland", "enabled": True, "protocol": "vless", "host": "192.0.2.3", "port": 443,
             "server_name": "example.com", "public_key": "C" * 43, "short_id": "abcd"},
            {"id": "italy", "enabled": True, "protocol": "vless", "host": "192.0.2.4", "port": 443,
             "server_name": "example.com", "public_key": "D" * 43, "short_id": "abcd"},
        ])
        for index, node in enumerate(state["nodes"]):
            node.update(host=f"198.51.100.{101 + index}", server_name="www.microsoft.com", short_id="0123456789abcdef")
        state["nodes"][0]["operator_note"] = "not-for-renderer"
        for index, device_id in enumerate(("nik-iphone-primary", "nik-iphone-spare", "nik-galaxy-s22",
                                           "goar-iphone-primary", "goar-iphone-second", "andrey-maksimov-iphone")):
            token = "p_" + chr(ord("C") + index) * 43
            state["devices"].append({
                "id": device_id, "token": token, "hash": hashlib.sha256(token.encode()).hexdigest(),
                "enabled": True, "tailscale": index < 3, "rule_set_mode": "remote" if index == 2 else "inline",
                "credentials": {node["id"]: {"uuid": f"00000000-0000-4000-8000-{index * 4 + offset + 1:012d}"}
                                for offset, node in enumerate(state["nodes"])},
                "server_revocation": {node["id"]: "not-requested" for node in state["nodes"]},
                "operator_note": "not-for-renderer",
            })
        return state

    def test_four_node_six_device_projection_cli_fits_raw_budget_and_preserves_private_output(self):
        state = self.four_node_state()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "public-state.json"
            source.write_text(json.dumps(state))
            output = Path(directory) / "projection.json"
            command = [sys.executable, manage.__file__, "pilot-project", "--input", str(source), "--output", str(output)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            raw = output.read_bytes()
            self.assertLess(len(raw), 5000)
            projection = json.loads(raw)
            self.assertGreater(len(json.dumps(projection, indent=2).encode()), 5000)
            self.assertEqual(set(projection), {"schema", "magic_dns_suffix", "subscription_hosts", "rules_url", "nodes", "devices"})
            for key in ("schema", "magic_dns_suffix", "subscription_hosts", "rules_url"):
                self.assertEqual(projection[key], state[key])
            self.assertEqual([n["id"] for n in projection["nodes"]], ["france", "frankfurt", "poland", "italy"])
            for projected, node in zip(projection["nodes"], state["nodes"]):
                self.assertEqual(projected, {key: value for key, value in node.items() if key != "operator_note"})
            self.assertEqual(len(projection["devices"]), 6)
            for projected, device in zip(projection["devices"], state["devices"]):
                self.assertEqual(set(projected), {"id", "hash", "enabled", "tailscale", "credentials", "rule_set_mode"})
                for key in projected:
                    self.assertEqual(projected[key], device[key])
                self.assertNotIn(device["token"].encode(), raw)
            self.assertNotIn(b"operator_note", raw)
            self.assertNotIn(b"server_revocation", raw)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            repeated = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertIn("FileExistsError", repeated.stderr)
            self.assertEqual(output.read_bytes(), raw)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(source.read_text()), state)

    def test_four_node_other_pilot_outputs_keep_pretty_json(self):
        state = self.four_node_state()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "public-state.json"
            source.write_text(json.dumps(state))
            for action, options in (("pilot-users", ["--node", "italy"]),
                                    ("pilot-revoke", ["--label", "nik-iphone-primary"])):
                with self.subTest(action=action):
                    output = Path(directory) / (action + ".json")
                    result = subprocess.run([sys.executable, manage.__file__, action, "--input", str(source),
                                             "--output", str(output), *options], capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    raw = output.read_text()
                    self.assertEqual(raw, json.dumps(json.loads(raw), indent=2) + "\n")
                    self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_four_node_projection_cli_still_rejects_invalid_and_over_budget_states(self):
        state = self.four_node_state()
        invalid = copy.deepcopy(state)
        invalid["devices"][5]["credentials"]["italy"] = invalid["devices"][0]["credentials"]["france"]
        over_budget = copy.deepcopy(state)
        over_budget["ru_domains"] = ["padding.example"] * 400
        with tempfile.TemporaryDirectory() as directory:
            for name, candidate in (("duplicate-uuid", invalid), ("over-budget", over_budget)):
                with self.subTest(name=name):
                    source = Path(directory) / (name + ".json")
                    source.write_text(json.dumps(candidate))
                    output = Path(directory) / (name + "-output.json")
                    result = subprocess.run([sys.executable, manage.__file__, "pilot-project", "--input", str(source),
                                             "--output", str(output)], capture_output=True, text=True, timeout=30)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("ValueError", result.stderr)
                    self.assertFalse(output.exists())

    def test_issuer_gives_each_device_and_server_a_distinct_credential(self):
        spec = self.spec()
        spec["nodes"][0]["private_key"] = "must-not-enter-catalog"
        state = manage.new_pilot(spec)
        self.assertEqual([d["id"] for d in state["devices"]], ["nik-iphone-primary", "nik-iphone-spare"])
        self.assertTrue(all(d["tailscale"] for d in state["devices"]))
        uuids = [c["uuid"] for d in state["devices"] for c in d["credentials"].values()]
        self.assertEqual(len(set(uuids)), 4)
        self.assertNotEqual(state["devices"][0]["token"], state["devices"][1]["token"])
        projected = manage.validate_pilot(state)
        self.assertNotIn("private_key", state["nodes"][0])
        self.assertNotIn("private_key", projected["nodes"][0])
        self.assertLess(len(json.dumps(projected).encode()), 5000)
        for device in projected["devices"]:
            self.assertNotIn("token", device)
            self.assertNotIn("server_revocation", device)

    def test_revoke_disables_fetch_but_tracks_pending_server_removal(self):
        state = manage.new_pilot(self.spec())
        other = copy.deepcopy(state["devices"][1])
        manage.revoke_pilot(state, "nik-iphone-primary")
        self.assertFalse(state["devices"][0]["enabled"])
        self.assertEqual(set(state["devices"][0]["server_revocation"].values()), {"pending-removal"})
        self.assertEqual(state["devices"][1], other)
        with self.assertRaises(ValueError):
            manage.revoke_pilot(state, "unknown")

    def test_invalid_identity_hash_or_duplicate_uuid_is_rejected(self):
        state = manage.new_pilot(self.spec())
        state["devices"][0]["hash"] = "0" * 64
        with self.assertRaises(ValueError):
            manage.validate_pilot(state)
        state = manage.new_pilot(self.spec())
        state["devices"][1]["credentials"]["france"] = state["devices"][0]["credentials"]["france"]
        with self.assertRaises(ValueError):
            manage.validate_pilot(state)

    def test_thin_mode_is_validated_projected_and_local_fallback_stays_inline(self):
        state = manage.new_pilot(self.spec())
        device = state["devices"][0]
        device["rule_set_mode"] = "remote"
        self.assertEqual(manage.validate_pilot(state)["devices"][0]["rule_set_mode"], "remote")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "state.json"
            source.write_text(json.dumps(state))
            output = Path(directory) / "fallback.json"
            with contextlib.redirect_stdout(io.StringIO()):
                manage.pilot_action(SimpleNamespace(action="pilot-export", input=str(source), output=str(output),
                                                    label=device["id"], node="frankfurt"))
            raw = output.read_text()
            profile = json.loads(raw)
            self.assertEqual(raw, json.dumps(profile, indent=2) + "\n")
            self.assertEqual(profile["route"]["rule_set"][0]["type"], "inline")
            self.assertGreater(len(profile["route"]["rule_set"][0]["rules"][0]["ip_cidr"]), 10000)
            self.assertEqual(profile["outbounds"][0]["outbounds"], ["frankfurt"])
        device["rule_set_mode"] = "unsupported"
        with self.assertRaises(ValueError):
            manage.validate_pilot(state)

    def test_owned_delivery_options_survive_projection_and_reject_external_hosts(self):
        spec = self.spec()
        spec["subscription_hosts"] = ["config.nikcode.xyz", "subscriptions.nikcode.xyz"]
        spec["rules_url"] = "https://subscriptions.nikcode.xyz/rules/geoip-ru-bdca5cdb44cdcf0940001e5952386822a6f4ffa8b2c8eea00340aa6f585c7f9d.srs"
        state = manage.new_pilot(spec)
        projection = manage.validate_pilot(state)
        self.assertEqual(projection["subscription_hosts"], spec["subscription_hosts"])
        self.assertEqual(projection["rules_url"], spec["rules_url"])
        state["rules_url"] = "https://untrusted.example/rules.srs"
        with self.assertRaises(ValueError):
            manage.validate_pilot(state)

    def test_secret_output_is_private_no_overwrite_and_rejects_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private.json"
            manage.write_private_output(path, "private")
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                manage.write_private_output(path, "replacement")
            self.assertEqual(path.read_text(), "private")
        with self.assertRaises(ValueError):
            manage.write_private_output(manage.ROOT / "private-state.json", "private")


if __name__ == "__main__":
    unittest.main()
