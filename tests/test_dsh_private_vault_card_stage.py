#!/usr/bin/python3
"""Synthetic unit tests for the private card stager.

No network, no model, no real OCR cache, no vault: every test uses temporary
directories and injected fake dependencies.  These tests do not claim to
validate patient acceptance end to end; they pin the fail-closed contract.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
import urllib.request
from dataclasses import replace
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import dsh_private_vault_card_stage as stage  # noqa: E402

PATIENT = "Иван Иванович"
SECRET = "СЕКРЕТ-ПАЦИЕНТ-42"
COMPLETE_BLOCK = f"STATUS: COMPLETE\n---\n| Глюкоза | 5,4 | ммоль/л | 3,9-5,5 | ! | {SECRET} |\n"
PARTIAL_BLOCK = "STATUS: PARTIAL\nLIMITATION: нижняя строка обрезана\n---\n| Глюкоза | 5,4 |\n"
UNUSABLE_BLOCK = "STATUS: UNUSABLE\nLIMITATION: скан нечитаем\n---\n"
GOOD_EXTRACTION = {
    "document_type_literal": "Биохимия крови",
    "document_date_literal": "12.03.2026",
    "owner_name_literal": PATIENT,
    "facts": [
        {
            "name_literal": "Глюкоза",
            "result_literal": "5,4",
            "unit_literal": "ммоль/л",
            "reference_literal": "3,9-5,5",
            "reference_marker_literal": "!",
            "source_page": 1,
            "confidence": 0.9,
        }
    ],
}


class FakeDriver:
    def __init__(self, blocks):
        self.blocks = [] if blocks is None else blocks

    def load_validated_ocr_blocks(self, root):
        if isinstance(self.blocks, Exception):
            raise self.blocks
        return self.blocks


class Recorder:
    """Fake HTTP driver: records order and never opens a socket."""

    def __init__(self, response="{}", blocks=None, check_error=None, chat_error=None):
        self.response = response
        self.blocks = [] if blocks is None else blocks
        self.check_error = check_error
        self.chat_error = chat_error
        self.calls = []

    def check(self, api, model):
        self.calls.append(("models", api, model))
        if self.check_error is not None:
            raise self.check_error

    def complete(self, api, model, prompt):
        self.calls.append(("chat", api, model, prompt))
        if self.chat_error is not None:
            raise self.chat_error
        return self.response

    def load(self, path):
        self.calls.append(("driver", str(path)))
        return FakeDriver(self.blocks)

    def deps(self):
        return stage.Deps(self.check, self.complete, self.load)


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dsh-card-stage-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.vault = self.tmp / "vault"
        (self.vault / "Вложения/Оригиналы").mkdir(parents=True)
        (self.vault / "02 Люди/Семья").mkdir(parents=True)
        self.person = self.vault / "02 Люди/Семья/Иван.md"
        self.person.write_text("# Иван\n", encoding="utf-8")
        self.original = self.vault / "Вложения/Оригиналы/scan.pdf"
        self.original.write_bytes(b"%PDF synthetic fixture\n")
        self.cache = self.tmp / "cache"
        self.source = self.cache / "doc-1"
        self.source.mkdir(parents=True)
        (self.source / "render-manifest.json").write_text(
            json.dumps(
                {
                    "orientation_version": 2,
                    "source_id": "doc-1",
                    "page_count": 1,
                    "pages": [
                        {
                            "page": 1,
                            "rendered_file": "page-0001.jpg",
                            "source_file": str(self.original),
                            "source_sha256": "a" * 64,
                            "source_page": 1,
                            "source_kind": "image",
                            "metadata_orientation": 1,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (self.source / "result.json").write_text("{}", encoding="utf-8")
        self.owner_index = self.tmp / "owners.json"
        self.write_owners(
            [
                {
                    "name": PATIENT,
                    "aliases": ["Иванов Иван"],
                    "card": "02 Люди/Семья/Иван.md",
                    "folder": "02 Люди/Семья/Иван/Здоровье",
                }
            ]
        )
        self.staging = self.tmp / "stage"
        self.config = stage.Config(
            vault=self.vault,
            staging_root=self.staging,
            owner_index=self.owner_index,
            ocr_cache=self.cache,
            source_id="doc-1",
            driver_path=self.tmp / "driver.py",
        )

    def write_owners(self, owners):
        self.owner_index.write_text(
            json.dumps({"owners": owners}, ensure_ascii=False), encoding="utf-8"
        )

    def run_stage(self, response=None, blocks=None, config=None, **kwargs):
        recorder = Recorder(
            response=json.dumps(GOOD_EXTRACTION, ensure_ascii=False)
            if response is None
            else response,
            blocks=[COMPLETE_BLOCK] if blocks is None else blocks,
            **kwargs,
        )
        return stage.run(config or self.config, recorder.deps()), recorder.calls

    def cli_args(self, *extra):
        return [
            "--vault", str(self.vault),
            "--staging-root", str(self.staging),
            "--owner-index", str(self.owner_index),
            "--ocr-cache", str(self.cache),
            "--source-id", "doc-1",
            *extra,
        ]

    def snapshot_vault(self):
        return sorted(
            (str(path.relative_to(self.vault)), path.read_bytes())
            for path in self.vault.rglob("*")
            if path.is_file()
        )


class EndpointTests(unittest.TestCase):
    def test_private_literal_endpoints_accepted(self):
        for api in (
            stage.APPROVED_API,
            "https://10.1.2.3:443/v1/chat/completions",
            "http://127.0.0.1:8081/v1/chat/completions",
            "http://[fd00::1]:8081/v1/chat/completions",
            "http://[::1]:8081/v1/chat/completions",
        ):
            self.assertEqual(stage.validate_endpoint(api), api)

    def test_public_documentation_linklocal_multicast_rejected(self):
        for host in (
            "8.8.8.8", "1.1.1.1", "192.0.2.10", "198.51.100.1", "203.0.113.1",
            "169.254.1.1", "224.0.0.1", "0.0.0.0", "[fe80::1]", "[ff02::1]",
        ):
            with self.subTest(host=host):
                with self.assertRaises(stage.StageError) as caught:
                    stage.validate_endpoint(f"http://{host}:8081/v1/chat/completions")
                self.assertEqual(caught.exception.code, "api_not_private")

    def test_userinfo_hostname_path_query_and_scheme_rejected(self):
        cases = {
            "http://user:pass@192.168.1.1:8081/v1/chat/completions": "api_credentials",
            "http://localhost:8081/v1/chat/completions": "api_host_invalid",
            "http://192.168.1.1:8081/v1/models": "api_path_invalid",
            "http://192.168.1.1:8081/v1/chat/completions?x=1": "api_query_invalid",
            "http://192.168.1.1:8081/v1/chat/completions#x": "api_query_invalid",
            "ftp://192.168.1.1:8081/v1/chat/completions": "api_scheme_invalid",
        }
        for api, code in cases.items():
            with self.subTest(api=api):
                with self.assertRaises(stage.StageError) as caught:
                    stage.validate_endpoint(api)
                self.assertEqual(caught.exception.code, code)

    def test_models_url_derives_from_validated_endpoint(self):
        self.assertEqual(
            stage._models_url(stage.APPROVED_API),
            "http://192.168.1.174:8081/v1/models",
        )

    def test_opener_ignores_proxy_environment_and_never_redirects(self):
        env = {"http_proxy": "http://10.0.0.9:3128", "https_proxy": "http://10.0.0.9:3128"}
        with mock.patch.dict(os.environ, env):
            opener = stage._opener()
        proxies = [h for h in opener.handlers if isinstance(h, urllib.request.ProxyHandler)]
        self.assertTrue(all(handler.proxies == {} for handler in proxies))
        self.assertFalse(any(getattr(handler, "proxies", None) for handler in opener.handlers))
        self.assertFalse(any(type(h) is urllib.request.HTTPRedirectHandler for h in opener.handlers))
        redirect = next(h for h in opener.handlers if type(h) is stage._NoRedirect)
        self.assertIsNone(
            redirect.redirect_request(None, None, 302, "Found", {}, "http://8.8.8.8/")
        )

    def test_incomplete_or_malformed_model_responses_rejected(self):
        for reason in (None, "length", "tool_calls"):
            payload = {"choices": [{"finish_reason": reason, "message": {"content": "{}"}}]}
            with self.subTest(reason=reason):
                with self.assertRaises(stage.StageError) as caught:
                    stage.parse_chat_content(payload)
                self.assertEqual(caught.exception.code, "model_incomplete")
        for payload in (
            {},
            {"choices": []},
            {"choices": [{"finish_reason": "stop", "message": {"content": "  "}}]},
            {"choices": [{"finish_reason": "stop"}]},
        ):
            with self.assertRaises(stage.StageError) as caught:
                stage.parse_chat_content(payload)
            self.assertEqual(caught.exception.code, "model_response_invalid")
        good = {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
        self.assertEqual(stage.parse_chat_content(good), "{}")


class ExtractionTests(unittest.TestCase):
    def parse(self, **overrides):
        payload = json.loads(json.dumps(GOOD_EXTRACTION, ensure_ascii=False))
        payload.update(overrides)
        return stage.parse_extraction(json.dumps(payload, ensure_ascii=False), 1)

    def test_valid_extraction_keeps_exact_literals(self):
        parsed = self.parse()
        self.assertEqual(parsed["facts"][0]["result_literal"], "5,4")
        self.assertEqual(parsed["facts"][0]["reference_marker_literal"], "!")

    def test_extra_or_missing_keys_rejected(self):
        with self.assertRaises(stage.StageError) as caught:
            self.parse(extra="x")
        self.assertEqual(caught.exception.code, "extraction_schema_invalid")
        payload = dict(GOOD_EXTRACTION)
        del payload["owner_name_literal"]
        with self.assertRaises(stage.StageError):
            stage.parse_extraction(json.dumps(payload), 1)

    def test_fact_schema_and_bounds_rejected(self):
        for mutate in (
            lambda fact: fact.update(extra="x"),
            lambda fact: fact.update(confidence=True),
            lambda fact: fact.update(confidence=1.5),
            lambda fact: fact.update(confidence=float("nan")),
            lambda fact: fact.update(source_page=0),
            lambda fact: fact.update(source_page=2),
            lambda fact: fact.update(result_literal="line\nbreak"),
            lambda fact: fact.update(unit_literal=""),
        ):
            payload = json.loads(json.dumps(GOOD_EXTRACTION, ensure_ascii=False))
            mutate(payload["facts"][0])
            with self.subTest(payload=payload["facts"][0]):
                with self.assertRaises(stage.StageError) as caught:
                    stage.parse_extraction(json.dumps(payload), 1)
                self.assertEqual(caught.exception.code, "extraction_schema_invalid")

    def test_empty_facts_and_invalid_json_rejected(self):
        with self.assertRaises(stage.StageError) as caught:
            self.parse(facts=[])
        self.assertEqual(caught.exception.code, "extraction_facts_invalid")
        for content in ("not json", '{"a": 1, "a": 2}', "[]", ""):
            with self.subTest(content=content):
                with self.assertRaises(stage.StageError):
                    stage.parse_extraction(content, 1)


class OwnerIndexTests(WorkspaceTest):
    def test_aliases_resolve_to_one_owner(self):
        owners = stage.load_owner_index(self.owner_index, self.vault)
        self.assertEqual(stage.resolve_owner("иванов иван", owners).card, "02 Люди/Семья/Иван.md")

    def test_unknown_and_empty_owner_fail_closed(self):
        owners = stage.load_owner_index(self.owner_index, self.vault)
        for literal in ("Неизвестный", "", None):
            with self.subTest(literal=literal):
                with self.assertRaises(stage.StageError) as caught:
                    stage.resolve_owner(literal, owners)
                self.assertEqual(caught.exception.code, "owner_unresolved")

    def test_duplicate_owner_is_ambiguous(self):
        other = self.vault / "02 Люди/Семья/Пётр.md"
        other.write_text("# Пётр\n", encoding="utf-8")
        self.write_owners(
            [
                {"name": PATIENT, "card": "02 Люди/Семья/Иван.md", "folder": "02 Люди/Семья/Иван/Здоровье"},
                {"name": PATIENT, "card": "02 Люди/Семья/Пётр.md", "folder": "02 Люди/Семья/Пётр/Здоровье"},
            ]
        )
        owners = stage.load_owner_index(self.owner_index, self.vault)
        with self.assertRaises(stage.StageError) as caught:
            stage.resolve_owner(PATIENT, owners)
        self.assertEqual(caught.exception.code, "owner_ambiguous")

    def test_traversal_absolute_missing_and_symlink_owner_paths_rejected(self):
        for card in ("../evil.md", "/etc/passwd", "02 Люди/Семья/Нет.md"):
            with self.subTest(card=card):
                self.write_owners([{"name": PATIENT, "card": card, "folder": "02 Люди/Семья/Иван/Здоровье"}])
                with self.assertRaises(stage.StageError):
                    stage.load_owner_index(self.owner_index, self.vault)
        outside = self.tmp / "outside.md"
        outside.write_text("x", encoding="utf-8")
        link = self.vault / "02 Люди/Семья/Ссылка.md"
        link.symlink_to(outside)
        self.write_owners(
            [{"name": PATIENT, "card": "02 Люди/Семья/Ссылка.md", "folder": "02 Люди/Семья/Иван/Здоровье"}]
        )
        with self.assertRaises(stage.StageError) as caught:
            stage.load_owner_index(self.owner_index, self.vault)
        self.assertEqual(caught.exception.code, "owner_path_invalid")


class PathTests(WorkspaceTest):
    def test_relative_path_rejects_traversal_and_absolute(self):
        for value in ("../x", "/x", "a//b", "a/./b", "a\\b", " a", ""):
            with self.subTest(value=value):
                with self.assertRaises(stage.StageError):
                    stage._relative_path(value, "bad")
        self.assertEqual(stage._relative_path("a/b.md", "bad"), "a/b.md")

    def test_staging_inside_vault_existing_symlink_and_missing_parent(self):
        for staging, code in (
            (self.vault / "stage", "staging_inside_vault"),
            (self.tmp / "missing/stage", "staging_parent_missing"),
        ):
            with self.subTest(staging=staging):
                result, calls = self.run_stage(config=replace(self.config, staging_root=staging))
                self.assertEqual(result.status, "blocked")
                self.assertEqual(result.codes, [code])
                self.assertEqual(calls, [])
        link = self.tmp / "vault-link"
        link.symlink_to(self.vault, target_is_directory=True)
        result, calls = self.run_stage(config=replace(self.config, staging_root=link / "stage"))
        self.assertEqual(result.codes, ["staging_inside_vault"])
        self.assertEqual(calls, [])

    def test_existing_staging_root_is_not_overwritten(self):
        self.staging.mkdir()
        (self.staging / "card.md").write_text("keep", encoding="utf-8")
        result, calls = self.run_stage()
        self.assertEqual(result.codes, ["staging_root_exists"])
        self.assertEqual(calls, [])
        self.assertEqual((self.staging / "card.md").read_text(encoding="utf-8"), "keep")

    def test_cache_inside_vault_and_source_symlink_escape_rejected(self):
        inside = self.vault / "cache/doc-1"
        inside.mkdir(parents=True)
        result, calls = self.run_stage(config=replace(self.config, ocr_cache=self.vault / "cache"))
        self.assertEqual(result.codes, ["ocr_inside_vault"])
        self.assertEqual(calls, [])
        shutil.rmtree(self.source)
        outside = self.tmp / "outside"
        outside.mkdir()
        self.source.symlink_to(outside, target_is_directory=True)
        result, calls = self.run_stage()
        self.assertEqual(result.codes, ["source_path_escape"])
        self.assertEqual(calls, [])

    def test_manifest_mode_and_source_selection(self):
        config = replace(self.config, ocr_cache=None, source_id=None, manifest=self.source / "result.json")
        result, _ = self.run_stage(config=config)
        self.assertEqual(result.status, "staged_complete")
        bad = replace(
            self.config,
            manifest=self.source / "render-manifest.json",
            staging_root=self.tmp / "stage-bad",
        )
        result, calls = self.run_stage(config=bad)
        self.assertEqual(result.codes, ["manifest_invalid"])
        self.assertEqual(calls, [])

    def test_source_selection_rejects_both_or_neither(self):
        base = dict(
            vault=self.vault, staging_root=self.staging, owner_index=self.owner_index,
            api=stage.APPROVED_API, model=stage.APPROVED_MODEL,
            ocr_cache=self.cache, source_id="doc-1", manifest=None,
            ocr_driver=self.tmp / "driver.py", timeout=1.0,
        )
        both = argparse.Namespace(**{**base, "manifest": self.source / "result.json"})
        neither = argparse.Namespace(**{**base, "ocr_cache": None, "source_id": None})
        for namespace in (both, neither):
            with self.assertRaises(stage.StageError) as caught:
                stage._config_from_args(namespace)
            self.assertEqual(caught.exception.code, "source_selection_invalid")
        invalid_id = argparse.Namespace(**{**base, "source_id": "../doc"})
        with self.assertRaises(stage.StageError) as caught:
            stage._config_from_args(invalid_id)
        self.assertEqual(caught.exception.code, "source_id_invalid")


class DriverTests(WorkspaceTest):
    def test_real_loader_imports_only_the_validation_entry_point(self):
        module_path = self.tmp / "fake_driver.py"
        module_path.write_text(
            "def load_validated_ocr_blocks(root):\n    return ['STATUS: COMPLETE\\n---\\n| x | y |']\n",
            encoding="utf-8",
        )
        module = stage._default_driver_loader(module_path)
        self.assertEqual(
            module.load_validated_ocr_blocks(self.source),
            ["STATUS: COMPLETE\n---\n| x | y |"],
        )

    def test_missing_driver_blocks_without_model_calls(self):
        recorder = Recorder(response=json.dumps(GOOD_EXTRACTION), blocks=[COMPLETE_BLOCK])
        deps = stage.Deps(recorder.check, recorder.complete, stage._default_driver_loader)
        result = stage.run(replace(self.config, driver_path=self.tmp / "missing.py"), deps)
        self.assertEqual(result.codes, ["ocr_driver_unavailable"])
        self.assertEqual(recorder.calls, [])

    def test_real_driver_validation_is_invoked_and_rejects_incomplete_cache(self):
        driver = Path.home() / "vault/tools/local_document_ocr.py"
        if not driver.is_file() or importlib.util.find_spec("PIL") is None:
            self.skipTest("canonical OCR driver or its dependencies are not present")
        recorder = Recorder(response=json.dumps(GOOD_EXTRACTION), blocks=[COMPLETE_BLOCK])
        deps = stage.Deps(recorder.check, recorder.complete, stage._default_driver_loader)
        result = stage.run(replace(self.config, driver_path=driver), deps)
        self.assertEqual(result.codes, ["ocr_invalid"])
        self.assertEqual(recorder.calls, [])

    def test_invalid_source_hash_in_manifest_is_rejected(self):
        manifest_path = self.source / "render-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["pages"][0]["source_sha256"] = "not-a-sha"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(stage.StageError) as caught:
            stage._originals(self.source, self.vault)
        self.assertEqual(caught.exception.code, "ocr_invalid")

    def test_driver_validation_failure_and_unusable_status_block(self):
        result, calls = self.run_stage(blocks=RuntimeError("validation failed"))
        self.assertEqual(result.codes, ["ocr_invalid"])
        self.assertEqual([call[0] for call in calls], ["driver"])
        result, calls = self.run_stage(blocks=[UNUSABLE_BLOCK])
        self.assertEqual(result.codes, ["ocr_unusable"])
        self.assertEqual([call[0] for call in calls], ["driver"])


class StagingTests(WorkspaceTest):
    def test_complete_run_writes_private_draft_and_zero_vault_writes(self):
        before = self.snapshot_vault()
        result, calls = self.run_stage()
        self.assertEqual(result.status, "staged_complete")
        self.assertTrue(result.owner_resolved and result.model_verified)
        self.assertEqual([call[0] for call in calls], ["driver", "models", "chat"])
        self.assertEqual(self.snapshot_vault(), before)
        self.assertEqual(stat.S_IMODE(self.staging.stat().st_mode), 0o700)
        for name in ("card.md", "proposal.json", "report.json"):
            path = self.staging / name
            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        proposal = json.loads((self.staging / "proposal.json").read_text(encoding="utf-8"))
        self.assertEqual(proposal["vault_writes"], 0)
        self.assertEqual(proposal["owner"]["card"], "02 Люди/Семья/Иван.md")
        self.assertTrue(proposal["proposed"]["card_path"].startswith("02 Люди/Семья/Иван/Здоровье/"))
        self.assertEqual(proposal["facts"][0]["result_literal"], "5,4")
        self.assertEqual(proposal["facts"][0]["confidence_source"], "model_reported")
        self.assertEqual(proposal["proposed"]["source_verification"], "pending")
        self.assertTrue(proposal["proposed"]["requires_human_approval"])
        card = (self.staging / "card.md").read_text(encoding="utf-8")
        for fragment in ("ocr_status: complete", "| Глюкоза | 5,4 | ммоль/л |", "| ! |", "стр. 1", "0.90"):
            self.assertIn(fragment, card)

    def test_partial_ocr_is_staged_with_limitations_never_complete(self):
        result, _ = self.run_stage(blocks=[PARTIAL_BLOCK])
        self.assertEqual(result.status, "staged_partial")
        self.assertEqual(result.ocr_status, "partial")
        card = (self.staging / "card.md").read_text(encoding="utf-8")
        self.assertIn("ocr_status: partial", card)
        self.assertIn("Ограничение OCR: нижняя строка обрезана", card)
        self.assertNotIn("ocr_status: complete", card)
        proposal = json.loads((self.staging / "proposal.json").read_text(encoding="utf-8"))
        self.assertEqual(proposal["status"], "staged_partial")

    def test_table_cells_escape_pipes_and_paths_stay_inside_vault(self):
        payload = json.loads(json.dumps(GOOD_EXTRACTION, ensure_ascii=False))
        payload["facts"][0]["result_literal"] = "5|4"
        payload["document_type_literal"] = "../../evil`tick"
        result, _ = self.run_stage(response=json.dumps(payload, ensure_ascii=False))
        self.assertEqual(result.status, "staged_complete")
        card = (self.staging / "card.md").read_text(encoding="utf-8")
        self.assertIn("5\\|4", card)
        proposal = json.loads((self.staging / "proposal.json").read_text(encoding="utf-8"))
        card_path = proposal["proposed"]["card_path"]
        self.assertNotIn("../", card_path)
        self.assertNotIn("`", card_path)
        self.assertTrue(str(self.vault / card_path).startswith(str(self.vault)))

    def test_missing_date_and_type_are_flagged_not_normalized(self):
        payload = json.loads(json.dumps(GOOD_EXTRACTION, ensure_ascii=False))
        payload["document_date_literal"] = None
        payload["document_type_literal"] = None
        result, _ = self.run_stage(response=json.dumps(payload, ensure_ascii=False))
        self.assertEqual(result.codes, ["date_missing", "type_missing"])
        proposal = json.loads((self.staging / "proposal.json").read_text(encoding="utf-8"))
        self.assertIn("без-даты", proposal["proposed"]["card_path"])
        self.assertIn("медицинская запись", proposal["proposed"]["card_path"])

    def test_model_failure_never_retries_and_never_stages(self):
        result, calls = self.run_stage(chat_error=stage.StageError("model_timeout"))
        self.assertEqual(result.codes, ["model_timeout"])
        self.assertEqual([call[0] for call in calls], ["driver", "models", "chat"])
        self.assertFalse(self.staging.exists())
        result, calls = self.run_stage(check_error=stage.StageError("model_mismatch"))
        self.assertEqual(result.codes, ["model_mismatch"])
        self.assertEqual([call[0] for call in calls], ["driver", "models"])
        self.assertFalse(self.staging.exists())

    def test_schema_owner_and_json_failures_stage_nothing(self):
        bad_payload = json.loads(json.dumps(GOOD_EXTRACTION, ensure_ascii=False))
        bad_payload["facts"][0]["confidence"] = 2
        for response, code in (
            ("not json", "extraction_json_invalid"),
            (json.dumps(bad_payload), "extraction_schema_invalid"),
            (json.dumps({**GOOD_EXTRACTION, "owner_name_literal": "Другой"}), "owner_unresolved"),
        ):
            with self.subTest(code=code):
                result, _ = self.run_stage(response=response)
                self.assertEqual(result.codes, [code])
                self.assertFalse(self.staging.exists())

    def test_second_run_cannot_overwrite_first_staging(self):
        self.run_stage()
        card_before = (self.staging / "card.md").read_bytes()
        result, calls = self.run_stage()
        self.assertEqual(result.codes, ["staging_root_exists"])
        self.assertEqual(calls, [])
        self.assertEqual((self.staging / "card.md").read_bytes(), card_before)


class CliTests(WorkspaceTest):
    def invoke(self, response=None, blocks=None):
        recorder = Recorder(
            response=json.dumps(GOOD_EXTRACTION, ensure_ascii=False)
            if response is None
            else response,
            blocks=[COMPLETE_BLOCK] if blocks is None else blocks,
        )
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(stage, "default_deps", lambda timeout: recorder.deps()):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = stage.main(self.cli_args())
        return code, out.getvalue(), err.getvalue()

    def test_stdout_is_machine_report_without_sensitive_text(self):
        code, out, err = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        report = json.loads(out)
        self.assertEqual(
            set(report),
            {
                "schema", "status", "codes", "ocr_status", "pages", "facts",
                "owner_resolved", "model_verified", "vault_writes", "staging_dir", "files",
            },
        )
        self.assertEqual(report["status"], "staged_complete")
        for sentinel in (PATIENT, SECRET, "Глюкоза", "Биохимия", "5,4", "ммоль/л"):
            self.assertNotIn(sentinel, out)
            self.assertNotIn(sentinel, err)

    def test_blocked_cli_prints_fixed_code_only(self):
        payload = json.loads(json.dumps(GOOD_EXTRACTION, ensure_ascii=False))
        payload["owner_name_literal"] = "Другой"
        code, out, err = self.invoke(response=json.dumps(payload, ensure_ascii=False))
        self.assertEqual(code, 2)
        report = json.loads(out)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["codes"], ["owner_unresolved"])
        self.assertEqual(err, "stage: owner_unresolved\n")
        for sentinel in (PATIENT, SECRET, "Глюкоза", "Биохимия", "5,4"):
            self.assertNotIn(sentinel, out + err)


if __name__ == "__main__":
    unittest.main()
