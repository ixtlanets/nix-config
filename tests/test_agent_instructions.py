"""Verify preservation and routing before the updater touches live configuration."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

import yaml


REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("agent_sync", REPO / "scripts/sync-agent-instructions.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.source = REPO / "dotfiles/agents"

    def write(self, name, content):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def planner(self):
        return sync.Sync(self.home, self.source, env={})

    def fixture(self):
        self.write(".codex/config.toml", '# keep comment\nmodel = "parent-model"\n[features]\nhooks = true\n')
        self.write(".codex/AGENTS.md", "Original Codex guidance.\n")
        self.write(".config/opencode/AGENTS.md", "Original OpenCode guidance.\n")
        self.write(".hermes/SOUL.md", "Keep my persona and coding orchestration.\n")
        self.write(".hermes/plugins/advanced-delegation/plugin.yaml", "name: advanced-delegation\n")
        self.write(".hermes/config.yaml", """# keep global comment
model:
  default: parent-model
plugins:
  enabled: [advanced-delegation]
delegation:
  max_concurrent: 2
  backends:
    profile_routes:
      default: researcher
    model_map:
      options:
        - name: local
          model: local-model
          provider: custom
webapp:
  port: 9120
""")
        self.write("workspace/AGENTS.md", "Original workspace rules.\n")
        self.write("other/AGENTS.md", "Original specialist rules.\n")
        self.write(".openclaw/openclaw.json", json.dumps({
            "gateway": {"auth": {"token": "test-secret"}},
            "agents": {
                "defaults": {"workspace": str(self.home / "workspace"),
                             "model": {"primary": "original-model"},
                             "subagents": {"maxConcurrent": 2},
                             "models": {"openai/gpt-6.1-sol": {"params": {"temperature": 0.5}}}},
                "entries": {"specialist": {"workspace": str(self.home / "other"),
                                           "tools": {"deny": ["image_generate"]}}},
            },
        }))

    def test_preserves_guidance_settings_and_backups_and_is_idempotent(self):
        self.fixture()
        originals = {p: p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        job = self.planner()
        job.plan()
        backup = job.apply()
        for path, content in originals.items():
            if path in job.pending:
                saved = backup / str(path.absolute()).lstrip("/")
                self.assertEqual(saved.read_bytes(), content)
                self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
            if path.name in ["AGENTS.md", "SOUL.md"]:
                self.assertTrue(path.read_bytes().endswith(content))
                self.assertEqual(path.read_text().count(sync.START), 1)
        codex = tomllib.loads((self.home / ".codex/config.toml").read_text())
        self.assertEqual(codex["model"], "parent-model")
        self.assertTrue(codex["features"]["hooks"])
        self.assertTrue(codex["agents"]["enabled"])
        self.assertIn("# keep comment", (self.home / ".codex/config.toml").read_text())
        hermes_text = (self.home / ".hermes/config.yaml").read_text()
        hermes = yaml.safe_load(hermes_text)
        self.assertTrue(hermes_text.startswith("# keep global comment\n"))
        self.assertEqual(hermes["model"]["default"], "parent-model")
        self.assertEqual(hermes["webapp"]["port"], 9120)
        self.assertEqual(hermes["delegation"]["max_concurrent"], 2)
        self.assertEqual(hermes["delegation"]["backends"]["profile_routes"]["default"], "researcher")
        routes = hermes["delegation"]["backends"]["model_map"]["options"]
        self.assertEqual(routes[0]["name"], "local")
        claw = json.loads((self.home / ".openclaw/openclaw.json").read_text())
        self.assertEqual(claw["gateway"]["auth"]["token"], "test-secret")
        self.assertEqual(claw["agents"]["defaults"]["model"]["primary"], "original-model")
        self.assertEqual(claw["agents"]["defaults"]["subagents"]["maxConcurrent"], 2)
        self.assertEqual(claw["agents"]["entries"]["specialist"]["tools"]["deny"], ["image_generate"])
        self.assertEqual(self.planner().plan(), {})

    def test_dsh_is_optional_and_requires_an_existing_directory(self):
        root = self.home / ".dsh"
        pending = self.planner().plan()
        self.assertNotIn(root / "AGENTS.md", pending)
        self.assertFalse(root.exists())
        self.assertEqual(self.planner().plan(["dsh"]), {})
        root.write_text("Not a DSH directory.\n")
        self.assertEqual(self.planner().plan(["dsh"]), {})
        self.assertEqual(root.read_text(), "Not a DSH directory.\n")

    def test_dsh_home_override_does_not_fall_back_to_default(self):
        default = self.write(".dsh/AGENTS.md", "Default DSH guidance.\n")
        root = self.home / "custom-dsh"
        env = {"DSH_HOME": str(root)}
        self.assertEqual(sync.Sync(self.home, self.source, env=env).plan(["dsh"]), {})
        target = self.write("custom-dsh/AGENTS.md", "Custom DSH guidance.\n")
        pending = sync.Sync(self.home, self.source, env=env).plan(["dsh"])
        self.assertEqual(set(pending), {target})
        self.assertTrue(pending[target].endswith("Custom DSH guidance.\n"))
        self.assertEqual(default.read_text(), "Default DSH guidance.\n")

    def test_blank_dsh_home_uses_default_not_working_directory(self):
        target = self.write(".dsh/AGENTS.md", "Default DSH guidance.\n")
        for override in ["", "  \t "]:
            with self.subTest(override=override):
                job = sync.Sync(self.home, self.source, env={"DSH_HOME": override})
                self.assertEqual(set(job.plan(["dsh"])), {target})

    def test_dsh_preserves_surroundings_backups_and_unrelated_configuration(self):
        self.fixture()
        original = f"Personal prefix.\n{sync.START}\nOld DSH policy\n{sync.END}\nPersonal suffix."
        target = self.write(".dsh/AGENTS.md", original)
        self.write(".agents/AGENTS.md", "Independent global guidance.\n")
        self.write(".dsh/profiles/default.json", '{"permissions": "keep"}\n')
        self.write(".dsh/models.json", '{"allowlist": ["keep"]}\n')
        self.write(".dsh/permissions.json", '{"edit": "deny"}\n')
        originals = {p: p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        job = self.planner()
        pending = job.plan(["dsh"])
        self.assertEqual(set(pending), {target})
        self.assertTrue(pending[target].startswith("Personal prefix.\n"))
        self.assertTrue(pending[target].endswith("\nPersonal suffix."))
        self.assertNotIn("Old DSH policy", pending[target])
        self.assertEqual(pending[target].count(sync.START), 1)
        self.assertEqual(pending[target].count(sync.END), 1)
        backup = job.apply()
        saved = backup / str(target.absolute()).lstrip("/")
        self.assertEqual(saved.read_text(), original)
        self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
        for path, content in originals.items():
            if path != target:
                self.assertEqual(path.read_bytes(), content)
        self.assertEqual(self.planner().plan(["dsh"]), {})

    def test_dsh_only_ignores_invalid_other_app_inputs(self):
        target = self.write(".dsh/AGENTS.md", "Personal DSH guidance.\n")
        self.write(".codex/config.toml", "invalid = [")
        self.write(".config/opencode/agents/fast.md", "No frontmatter")
        self.write(".hermes/config.yaml", "invalid: [")
        self.write(".hermes/plugins/advanced-delegation/plugin.yaml", "name: advanced-delegation\n")
        self.write(".openclaw/openclaw.json", "not json")
        originals = {p: p.read_bytes() for p in self.home.rglob("*") if p.is_file()}
        pending = self.planner().plan(["dsh"])
        self.assertEqual(set(pending), {target})
        for path, content in originals.items():
            self.assertEqual(path.read_bytes(), content)

    def test_dsh_user_context_is_first_and_does_not_leak_into_other_apps(self):
        self.fixture()
        self.write(".dsh/AGENTS.md", "Personal DSH guidance.\n")
        source = self.home / "source"
        shutil.copytree(self.source, source)
        (source / "dsh-user.md").write_text("DSH-ONLY style and personal context.\n")
        (source / "common.md").write_text("Common policy sentinel.\n")
        (source / "dsh.md").write_text("DSH adapter sentinel.\n\n{{routes}}\n")
        pending = sync.Sync(self.home, source, env={}).plan()
        target = self.home / ".dsh/AGENTS.md"
        text = pending[target]
        self.assertLess(text.index("DSH-ONLY"), text.index("Common policy sentinel."))
        self.assertLess(text.index("Common policy sentinel."), text.index("DSH adapter sentinel."))
        self.assertNotIn("{{routes}}", text)
        for path, content in pending.items():
            if path != target:
                self.assertNotIn("DSH-ONLY", content, str(path))

    def test_all_dsh_policy_source_edits_propagate(self):
        target = self.write(".dsh/AGENTS.md", "Keep personal rules.\n")
        source = self.home / "source"
        shutil.copytree(self.source, source)
        job = sync.Sync(self.home, source, env={})
        job.plan(["dsh"])
        job.apply()
        for name in ["dsh-user.md", "common.md", "dsh.md"]:
            with self.subTest(source=name):
                marker = f"Updated {name} rule."
                with (source / name).open("a") as stream:
                    stream.write(f"\n{marker}\n")
                job = sync.Sync(self.home, source, env={})
                pending = job.plan(["dsh"])
                self.assertEqual(set(pending), {target})
                self.assertIn(marker, pending[target])
                self.assertTrue(pending[target].endswith("Keep personal rules.\n"))
                job.apply()
                self.assertEqual(sync.Sync(self.home, source, env={}).plan(["dsh"]), {})

    def test_dsh_route_table_tracks_shared_models_and_efforts(self):
        target = self.write(".dsh/AGENTS.md", "Personal DSH guidance.\n")
        source = self.home / "source"
        shutil.copytree(self.source, source)
        job = sync.Sync(self.home, source, env={})
        text = job.plan(["dsh"])[target]
        self.assertNotIn("{{routes}}", text)
        for name, route in job.routes.items():
            self.assertTrue(any(all(value in line for value in
                                    [name, "openai-codex", route["model"], route["reasoning_effort"]])
                                for line in text.splitlines()), name)
        job.apply()
        routes = json.loads((source / "routes.json").read_text())
        routes["fast"].update(model="test-updated-model", reasoning_effort="low")
        (source / "routes.json").write_text(json.dumps(routes))
        pending = sync.Sync(self.home, source, env={}).plan(["dsh"])
        self.assertEqual(set(pending), {target})
        self.assertTrue(any(all(value in line for value in
                                ["fast", "openai-codex", "test-updated-model", "low"])
                            for line in pending[target].splitlines()))
        self.assertNotIn(routes["fast"]["model"], target.read_text())

    def test_cli_dsh_check_accepts_repeated_app_and_never_writes(self):
        target = self.write(".dsh/AGENTS.md", "Personal DSH guidance.\n")
        invalid = self.write(".openclaw/openclaw.json", "not json")
        env = dict(os.environ, HOME=str(self.home), DSH_HOME=str(target.parent),
                   CODEX_HOME=str(self.home / ".codex"),
                   OPENCODE_CONFIG_DIR=str(self.home / ".config/opencode"),
                   HERMES_HOME=str(self.home / ".hermes"),
                   OPENCLAW_STATE_DIR=str(invalid.parent), OPENCLAW_CONFIG_PATH=str(invalid),
                   PYTHONDONTWRITEBYTECODE="1")
        command = [sys.executable, str(REPO / "scripts/sync-agent-instructions.py"),
                   "--home", str(self.home), "--source-dir", str(self.source),
                   "--check", "--app", "dsh", "--app", "dsh"]
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(f"Would update {target}", result.stdout)
        self.assertEqual(target.read_text(), "Personal DSH guidance.\n")
        self.assertEqual(invalid.read_text(), "not json")
        self.assertFalse((self.home / ".local").exists())
        job = self.planner()
        job.plan(["dsh"])
        job.apply()
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Would update", result.stdout)

    def test_native_routes_agree_across_apps(self):
        self.fixture()
        job = self.planner()
        job.plan()
        job.apply()
        hermes = yaml.safe_load((self.home / ".hermes/config.yaml").read_text())
        options = {r["name"]: r for r in hermes["delegation"]["backends"]["model_map"]["options"]}
        defaults = json.loads((self.home / ".openclaw/openclaw.json").read_text())["agents"]["defaults"]
        for name, route in job.routes.items():
            codex = tomllib.loads((self.home / f".codex/agents/{name}.toml").read_text())
            self.assertEqual(codex["model"], route["model"])
            self.assertEqual(codex["model_reasoning_effort"], route["reasoning_effort"])
            md = (self.home / f".config/opencode/agents/{name}.md").read_text()
            opencode = yaml.safe_load(md.split("---")[1])
            self.assertEqual(opencode["mode"], "subagent")
            self.assertEqual(opencode["model"], f"openai/{route['model']}#{route['reasoning_effort']}")
            self.assertEqual(options[name]["model"], route["model"])
            self.assertEqual(options[name]["provider"], "openai-codex")
            self.assertEqual(defaults["models"][f"openai/{route['model']}"]["alias"], name)

    def test_override_is_the_effective_codex_target(self):
        self.write(".codex/AGENTS.md", "Base stays intact.\n")
        override = self.write(".codex/AGENTS.override.md", "Personal override.\n")
        pending = self.planner().plan()
        self.assertNotIn(self.home / ".codex/AGENTS.md", pending)
        self.assertTrue(pending[override].endswith("Personal override.\n"))

    def test_existing_custom_agent_instructions_and_permissions_survive(self):
        self.write(".codex/agents/fast.toml", 'developer_instructions = "Custom worker rules"\n')
        self.write(".config/opencode/agents/fast.md", "---\npermissions:\n  - action: edit\n    resource: '*'\n    effect: deny\n---\nCustom worker body.\n")
        pending = self.planner().plan()
        codex = tomllib.loads(pending[self.home / ".codex/agents/fast.toml"])
        self.assertEqual(codex["developer_instructions"], "Custom worker rules")
        md = pending[self.home / ".config/opencode/agents/fast.md"]
        self.assertTrue(md.endswith("Custom worker body.\n"))
        self.assertEqual(yaml.safe_load(md.split("---")[1])["permissions"][0]["effect"], "deny")

    def test_bad_inputs_fail_before_any_writes(self):
        bad = self.write(".openclaw/openclaw.json", "not json")
        with self.assertRaises(ValueError):
            self.planner().plan()
        self.assertEqual([p for p in self.home.rglob("*") if p.is_file()], [bad])
        self.assertFalse((self.home / ".codex").exists())

    def test_optional_hermes_without_plugin_does_not_block_other_apps(self):
        config = self.write(".hermes/config.yaml", "model:\n  default: original\n")
        job = self.planner()
        pending = job.plan()
        self.assertTrue(job.warnings)
        self.assertNotIn(config, pending)
        self.assertIn(self.home / ".codex/AGENTS.md", pending)

    def test_policy_source_edits_propagate_and_unrelated_common_file_is_untouched(self):
        import shutil
        source = self.home / "source"
        shutil.copytree(self.source, source)
        existing = self.write(".agents/AGENTS.md", "Independent user guidance.\n")
        job = sync.Sync(self.home, source, env={})
        job.plan()
        job.apply()
        with (source / "common.md").open("a") as stream:
            stream.write("\nUpdated common rule.\n")
        with (source / "codex.md").open("a") as stream:
            stream.write("\nUpdated Codex rule.\n")
        pending = sync.Sync(self.home, source, env={}).plan()
        self.assertNotIn(existing, pending)
        self.assertEqual(existing.read_text(), "Independent user guidance.\n")
        self.assertIn("Updated common rule.", pending[self.home / ".codex/AGENTS.md"])
        self.assertIn("Updated Codex rule.", pending[self.home / ".codex/AGENTS.md"])
        self.assertIn("Updated common rule.", pending[self.home / ".config/opencode/AGENTS.md"])

    def test_policy_refresh_keeps_surrounding_text_and_rejects_bad_markers(self):
        original = "Personal text without a trailing newline"
        first = sync.policy_block(original, "Old policy", "Adapter")
        updated = sync.policy_block(first, "New policy", "Adapter")
        self.assertTrue(updated.endswith(original))
        self.assertNotIn("Old policy", updated)
        self.assertEqual(sync.policy_block(updated, "New policy", "Adapter"), updated)
        for text in [sync.START, sync.END, sync.END + sync.START, first + first]:
            with self.assertRaises(ValueError):
                sync.policy_block(text, "Policy", "Adapter")

    def test_native_hermes_routes_replace_old_endpoint_and_keep_other_options(self):
        original = """delegation:
  backends:
    model_map:
      options:
        - name: fast
          base_url: https://old-custom-endpoint.invalid/v1
          api_key: old-key
          api_mode: chat_completions
          fallback_providers: [custom]
          service_tier: fast
        - name: local
          base_url: http://localhost:8080/v1
"""
        routes = self.planner().routes
        updated = yaml.safe_load(sync.hermes_routes(original, routes))
        options = updated["delegation"]["backends"]["model_map"]["options"]
        self.assertEqual(options[0], {"name": "fast", "description": routes["fast"]["description"],
                                      "provider": "openai-codex", "model": routes["fast"]["model"],
                                      "reasoning_effort": "high"})
        self.assertEqual(options[1]["base_url"], "http://localhost:8080/v1")

    def test_cross_section_yaml_anchor_is_rejected_before_writes(self):
        self.fixture()
        original = "plugins:\n  enabled: [advanced-delegation]\ndelegation: &child_settings\n  max_concurrent: 2\nother: *child_settings\n"
        config = self.write(".hermes/config.yaml", original)
        with self.assertRaises((ValueError, yaml.YAMLError)):
            self.planner().plan()
        self.assertEqual(config.read_text(), original)
        self.assertNotIn(sync.START, (self.home / ".codex/AGENTS.md").read_text())

    def test_old_openclaw_alias_cannot_shadow_the_new_route(self):
        self.fixture()
        path = self.home / ".openclaw/openclaw.json"
        config = json.loads(path.read_text())
        config["agents"]["defaults"]["models"]["other/model"] = {"alias": "fast", "params": {"x": 1}}
        config["agents"]["entries"]["specialist"]["models"] = {
            "specialist/model": {"alias": "deep", "params": {"x": 2}}
        }
        path.write_text(json.dumps(config))
        pending = self.planner().plan()
        models = json.loads(pending[path])["agents"]["defaults"]["models"]
        self.assertEqual(models["other/model"], {"params": {"x": 1}})
        self.assertEqual(models["openai/gpt-6.1-terra"]["alias"], "fast")
        specialist = json.loads(pending[path])["agents"]["entries"]["specialist"]["models"]
        self.assertEqual(specialist["specialist/model"], {"params": {"x": 2}})
        self.assertEqual(specialist["openai/gpt-6.1-sol"]["alias"], "deep")


if __name__ == "__main__":
    unittest.main()
