#!/usr/bin/env python3
"""Merge shared policy and native model routes without replacing local guidance."""

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import stat
import tempfile

import tomlkit
import yaml


START = "<!-- nix-config:agent-instructions:start -->"
END = "<!-- nix-config:agent-instructions:end -->"
CHILD = (
    "Complete the parent's bounded assignment directly, following applicable "
    "instructions and the assignment's restrictions. Return the shared delegation "
    "result contract. Delegate further only when explicitly included in the assignment."
)


def policy_block(original, common, adapter):
    """Keep all unmanaged text intact; put policy before possible runtime truncation."""
    block = f"{START}\n{common.rstrip()}\n\n{adapter.rstrip()}\n{END}\n\n"
    if START not in original and END not in original:
        return block + original
    if original.count(START) != 1 or original.count(END) != 1:
        raise ValueError("Malformed or repeated agent-instructions markers")
    start, end = original.index(START), original.index(END)
    if end < start:
        raise ValueError("Reversed agent-instructions markers")
    # Replace only the block, retaining the exact surrounding bytes.
    return original[:start] + block.rstrip("\n") + original[end + len(END):]


def native_markdown(original, route):
    fields, body = {}, CHILD + "\n"
    if original:
        match = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", original, re.S)
        if not match:
            raise ValueError("Existing OpenCode agent has no YAML frontmatter")
        fields = yaml.safe_load(match[1]) or {}
        body = match[2]
    fields.update(description=route["description"], mode="subagent",
                  model=f"openai/{route['model']}#{route['reasoning_effort']}")
    return "---\n" + yaml.safe_dump(fields, sort_keys=False) + "---\n" + body


def hermes_routes(original, routes):
    config = yaml.safe_load(original) or {}
    delegation = config.setdefault("delegation", {})
    delegation["backend"] = "model_map"
    model_map = delegation.setdefault("backends", {}).setdefault("model_map", {})
    options = model_map.setdefault("options", [])
    for name, route in routes.items():
        existing = next((item for item in options if item.get("name") == name), None)
        if existing is None:
            existing = {"name": name}
            options.append(existing)
        # These belong to the previous route and can override native provider resolution.
        for key in ["base_url", "api_key", "api_mode", "fallback_providers", "service_tier"]:
            existing.pop(key, None)
        existing.update(description=route["description"], provider="openai-codex",
                        model=route["model"], reasoning_effort=route["reasoning_effort"])
    replacement = yaml.safe_dump({"delegation": delegation}, sort_keys=False)
    match = re.search(r"(?m)^delegation:[^\n]*(?:\n(?:[ \t].*|#.*|))*(?:\n|\Z)", original)
    if match:
        result = original[:match.start()] + replacement + original[match.end():]
    else:
        result = original.rstrip("\n") + "\n" + replacement
    # Reject unsupported shapes (e.g. cross-section YAML anchors) before any writes.
    if yaml.safe_load(result) != config:
        raise ValueError("Cannot safely update this Hermes delegation YAML structure")
    return result


def openclaw_aliases(models, routes):
    # Per-agent aliases can shadow defaults, so reconcile reserved aliases there too.
    for model, settings in models.items():
        alias = settings.get("alias")
        if alias in routes and model != f"openai/{routes[alias]['model']}":
            del settings["alias"]
    for name, route in routes.items():
        models.setdefault(f"openai/{route['model']}", {})["alias"] = name


class Sync:
    def __init__(self, home, source, env=None):
        self.home, self.source = Path(home), Path(source)
        self.env = os.environ if env is None else env
        self.routes = json.loads((self.source / "routes.json").read_text())
        self.common = (self.source / "common.md").read_text()
        self.pending = {}
        self.warnings = []

    def read(self, path):
        return Path(path).read_text() if Path(path).exists() else ""

    def put(self, path, content):
        path = Path(path)
        if self.read(path) != content:
            self.pending[path] = content

    def instructions(self, path, app, default=""):
        original = self.read(path) or default
        adapter = (self.source / f"{app}.md").read_text()
        self.put(path, policy_block(original, self.common, adapter))

    def codex(self):
        root = Path(self.env.get("CODEX_HOME", self.home / ".codex"))
        # Codex reads only one global file; preserve an existing override.
        override = root / "AGENTS.override.md"
        target = override if self.read(override).strip() else root / "AGENTS.md"
        self.instructions(target, "codex")
        path = root / "config.toml"
        config = tomlkit.parse(self.read(path))
        config.setdefault("agents", tomlkit.table())["enabled"] = True
        self.put(path, tomlkit.dumps(config))
        for name, route in self.routes.items():
            path = root / "agents" / f"{name}.toml"
            agent = tomlkit.parse(self.read(path))
            agent.update(name=name, description=route["description"], model=route["model"],
                         model_reasoning_effort=route["reasoning_effort"])
            agent.setdefault("developer_instructions", CHILD)
            self.put(path, tomlkit.dumps(agent))

    def opencode(self):
        root = Path(self.env.get("OPENCODE_CONFIG_DIR",
                               Path(self.env.get("XDG_CONFIG_HOME", self.home / ".config")) / "opencode"))
        self.instructions(root / "AGENTS.md", "opencode",
                          (self.source / "opencode-defaults.md").read_text())
        for name, route in self.routes.items():
            path = root / "agents" / f"{name}.md"
            self.put(path, native_markdown(self.read(path), route))

    def hermes(self):
        root = Path(self.env.get("HERMES_HOME", self.home / ".hermes"))
        path = root / "config.yaml"
        if not path.exists():
            return
        if not (root / "plugins" / "advanced-delegation" / "plugin.yaml").exists():
            self.warnings.append(f"Skipped Hermes in {root}: install advanced-delegation first")
            return
        config = yaml.safe_load(self.read(path)) or {}
        if "advanced-delegation" not in config.get("plugins", {}).get("enabled", []):
            self.warnings.append(f"Skipped Hermes in {root}: enable advanced-delegation first")
            return
        self.instructions(root / "SOUL.md", "hermes")
        self.put(path, hermes_routes(self.read(path), self.routes))

    def openclaw(self):
        root = Path(self.env.get("OPENCLAW_STATE_DIR", self.home / ".openclaw"))
        path = Path(self.env.get("OPENCLAW_CONFIG_PATH", root / "openclaw.json"))
        if not path.exists():
            return
        config = json.loads(self.read(path))
        agents = config.setdefault("agents", {})
        defaults = agents.setdefault("defaults", {})
        models = defaults.setdefault("models", {})
        openclaw_aliases(models, self.routes)
        subagents = defaults.setdefault("subagents", {})
        subagents.update(model=f"openai/{self.routes['fast']['model']}",
                         thinking=self.routes["fast"]["reasoning_effort"])
        # Match the default workspace as well as all configured agent workspaces.
        workspaces = {defaults.get("workspace", str(root / "workspace"))}
        entries = agents.get("entries", {})
        for entry in entries.values():
            if "models" in entry:
                openclaw_aliases(entry["models"], self.routes)
            if entry.get("workspace"):
                workspaces.add(entry["workspace"])
        for workspace in sorted(workspaces):
            self.instructions(Path(workspace).expanduser() / "AGENTS.md", "openclaw")
        self.put(path, json.dumps(config, ensure_ascii=False, indent=2) + "\n")

    def plan(self):
        self.codex()
        self.opencode()
        self.hermes()
        self.openclaw()
        return self.pending

    def apply(self):
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        backup = self.home / ".local/state/agent-instructions/backups" / stamp
        for path, content in self.pending.items():
            if path.exists():
                saved = backup / str(path.absolute()).lstrip("/")
                saved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                saved.write_bytes(path.read_bytes())
                saved.chmod(0o600)
            path.parent.mkdir(parents=True, exist_ok=True)
            mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
            # Nix-managed inputs can be read-only; replacements are user-owned files.
            mode |= stat.S_IWUSR
            descriptor, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
            try:
                with os.fdopen(descriptor, "w") as stream:
                    stream.write(content)
                os.chmod(temp, mode)
                os.replace(temp, path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
        return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path,
                        default=Path(__file__).resolve().parents[1] / "dotfiles/agents")
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--check", action="store_true", help="Report drift without writing")
    args = parser.parse_args()
    sync = Sync(args.home, args.source_dir)
    pending = sync.plan()  # Parse every input before changing any files.
    for warning in sync.warnings:
        print(f"Warning: {warning}")
    for path in pending:
        print(f"{'Would update' if args.check else 'Update'} {path}")
    if args.check:
        return int(bool(pending or sync.warnings))
    if pending:
        print(f"Backups: {sync.apply()}")
    else:
        print("Agent instructions and routes are up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
