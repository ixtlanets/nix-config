# Password Migration Analyzer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only analyzer that compares Apple Passwords CSV, 1Password `.1pux`, and optional `pass` entry names, then writes redacted migration reports plus a sensitive `safe-import.csv`.

**Architecture:** Implement a single Python CLI with small pure functions for parsing, normalization, matching, classification, `pass` scanning, and report writing. Keep secret-bearing values in memory except for the intentionally sensitive `safe-import.csv`; all review reports contain only redacted evidence and booleans.

**Tech Stack:** Python 3 standard library (`argparse`, `csv`, `dataclasses`, `hashlib`, `json`, `pathlib`, `tempfile`, `urllib.parse`, `zipfile`), pytest for tests.

---

## File Structure

- Create `scripts/password-migration-analyze.py`: executable CLI and importable module. Responsibilities: parse inputs, classify records, write reports.
- Create `tests/test_password_migration_analyze.py`: pytest suite that imports the script by path and builds tiny Apple CSV / 1PUX fixtures.
- Modify no Nix host config in this phase. The analyzer is run directly with `python3`.

## Task 1: Core Models, Normalization, And Apple CSV Parsing

**Files:**
- Create: `scripts/password-migration-analyze.py`
- Create: `tests/test_password_migration_analyze.py`

- [ ] **Step 1: Write failing tests for normalization and Apple CSV parsing**

Create `tests/test_password_migration_analyze.py` with:

```python
import csv
import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "password-migration-analyze.py"
spec = importlib.util.spec_from_file_location("password_migration_analyze", MODULE_PATH)
analyzer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyzer)


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["Title", "URL", "Username", "Password", "Notes", "OTPAuth"],
        )
        writer.writeheader()
        writer.writerows(rows)


def test_normalize_domain_strips_scheme_path_and_www():
    assert analyzer.normalize_domain("https://www.GitHub.com/settings?x=1") == "github.com"
    assert analyzer.normalize_domain("  accounts.google.com/login  ") == "accounts.google.com"


def test_parse_apple_csv_maps_required_fields(tmp_path):
    csv_path = tmp_path / "apple.csv"
    write_csv(
        csv_path,
        [
            {
                "Title": "GitHub",
                "URL": "https://github.com/login",
                "Username": "User@Example.COM ",
                "Password": "secret-password",
                "Notes": "private note",
                "OTPAuth": "otpauth://totp/GitHub:user?secret=ABC",
            }
        ],
    )

    records = analyzer.parse_apple_csv(csv_path)

    assert len(records) == 1
    record = records[0]
    assert record.source == "apple"
    assert record.title == "GitHub"
    assert record.url == "https://github.com/login"
    assert record.domain == "github.com"
    assert record.username == "user@example.com"
    assert record.password == "secret-password"
    assert record.otp == "otpauth://totp/GitHub:user?secret=ABC"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m pytest tests/test_password_migration_analyze.py::test_normalize_domain_strips_scheme_path_and_www tests/test_password_migration_analyze.py::test_parse_apple_csv_maps_required_fields -v
```

Expected: FAIL because `scripts/password-migration-analyze.py` does not exist.

- [ ] **Step 3: Implement models, normalization, and Apple CSV parsing**

Create `scripts/password-migration-analyze.py` with:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import stat
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


APPLE_FIELDS = ["Title", "URL", "Username", "Password", "Notes", "OTPAuth"]
NON_LOGIN_NAMESPACES = {"api", "cards", "notes", "ssh", "server", "secrets", "hosts", "software"}


@dataclass(frozen=True)
class LoginRecord:
    source: str
    title: str = ""
    url: str = ""
    username: str = ""
    password: str = ""
    notes: str = ""
    otp: str = ""
    urls: tuple[str, ...] = field(default_factory=tuple)
    vault: str = ""
    item_id: str = ""

    @property
    def domain(self) -> str:
        return normalize_domain(self.url)

    @property
    def key(self) -> tuple[str, str]:
        return (self.domain, self.username)

    @property
    def has_otp(self) -> bool:
        return bool(self.otp.strip())


@dataclass(frozen=True)
class PassEntry:
    path: str
    domain_hint: str
    username_hint: str
    namespace: str
    is_likely_login: bool


@dataclass(frozen=True)
class ClassifiedRecord:
    onepassword: LoginRecord
    category: str
    apple: LoginRecord | None = None
    reason: str = ""
    pass_path: str = ""


def normalize_username(value: str) -> str:
    return (value or "").strip().lower()


def normalize_domain(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or raw.split("/", 1)[0]).strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host.rstrip(".")


def short_hash(value: str) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def redact_username(value: str) -> str:
    value = normalize_username(value)
    if not value:
        return ""
    if "@" in value:
        local, domain = value.split("@", 1)
        if len(local) <= 2:
            local_part = local[:1] + "*"
        else:
            local_part = local[:2] + "***" + local[-1:]
        return f"{local_part}@{domain}"
    if len(value) <= 3:
        return value[:1] + "***"
    return value[:2] + "***" + value[-1:]


def parse_apple_csv(path: Path) -> list[LoginRecord]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [field for field in APPLE_FIELDS if field not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"Apple CSV is missing required columns: {', '.join(missing)}")
        records = []
        for row in reader:
            url = (row.get("URL") or "").strip()
            records.append(
                LoginRecord(
                    source="apple",
                    title=(row.get("Title") or "").strip(),
                    url=url,
                    username=normalize_username(row.get("Username") or ""),
                    password=row.get("Password") or "",
                    notes=row.get("Notes") or "",
                    otp=(row.get("OTPAuth") or "").strip(),
                    urls=(url,) if url else tuple(),
                )
            )
        return records
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python3 -m pytest tests/test_password_migration_analyze.py::test_normalize_domain_strips_scheme_path_and_www tests/test_password_migration_analyze.py::test_parse_apple_csv_maps_required_fields -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/password-migration-analyze.py tests/test_password_migration_analyze.py
git commit -m "feat: parse Apple passwords export"
```

## Task 2: 1Password 1PUX Parsing

**Files:**
- Modify: `scripts/password-migration-analyze.py`
- Modify: `tests/test_password_migration_analyze.py`

- [ ] **Step 1: Write failing tests for 1PUX parsing**

Append to `tests/test_password_migration_analyze.py`:

```python
import json
import zipfile


def write_1pux(path, payload):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("export.data", json.dumps(payload))


def test_parse_1pux_extracts_login_password_username_url_and_totp(tmp_path):
    onepux = tmp_path / "onepassword.1pux"
    write_1pux(
        onepux,
        {
            "accounts": [
                {
                    "attrs": {"accountName": "Personal"},
                    "vaults": [
                        {
                            "attrs": {"name": "Private"},
                            "items": [
                                {
                                    "uuid": "item-1",
                                    "categoryUuid": "001",
                                    "overview": {
                                        "title": "GitHub",
                                        "url": "https://github.com/login",
                                        "urls": [
                                            {"url": "https://github.com/login"},
                                            {"url": "https://gist.github.com"},
                                        ],
                                    },
                                    "details": {
                                        "loginFields": [
                                            {
                                                "designation": "username",
                                                "value": "User@Example.com",
                                            },
                                            {
                                                "designation": "password",
                                                "value": "secret-password",
                                            },
                                        ],
                                        "sections": [
                                            {
                                                "fields": [
                                                    {
                                                        "k": "concealed",
                                                        "t": "one-time password",
                                                        "v": "otpauth://totp/GitHub:user?secret=ABC",
                                                    }
                                                ]
                                            }
                                        ],
                                        "notesPlain": "private note",
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        },
    )

    records = analyzer.parse_1pux(onepux)

    assert len(records) == 1
    record = records[0]
    assert record.source == "1password"
    assert record.title == "GitHub"
    assert record.url == "https://github.com/login"
    assert record.urls == ("https://github.com/login", "https://gist.github.com")
    assert record.username == "user@example.com"
    assert record.password == "secret-password"
    assert record.otp == "otpauth://totp/GitHub:user?secret=ABC"
    assert record.vault == "Private"
    assert record.item_id == "item-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m pytest tests/test_password_migration_analyze.py::test_parse_1pux_extracts_login_password_username_url_and_totp -v
```

Expected: FAIL because `parse_1pux` is not defined.

- [ ] **Step 3: Implement 1PUX parsing**

Append these functions to `scripts/password-migration-analyze.py`:

```python
def _load_1pux_json(path: Path) -> dict:
    with zipfile.ZipFile(path) as zf:
        preferred = ["export.data", "export.json"]
        names = zf.namelist()
        for name in preferred:
            if name in names:
                return json.loads(zf.read(name).decode("utf-8"))
        for name in names:
            if name.endswith(".json") or name.endswith(".data"):
                return json.loads(zf.read(name).decode("utf-8"))
    raise ValueError(f"No JSON export data found in {path}")


def _field_text(field: dict) -> str:
    for key in ("value", "v"):
        value = field.get(key)
        if isinstance(value, str):
            return value
    return ""


def _extract_login_fields(details: dict) -> tuple[str, str, str]:
    username = ""
    password = ""
    otp = ""
    for field in details.get("loginFields") or []:
        designation = field.get("designation")
        value = _field_text(field)
        if designation == "username" and value:
            username = value
        elif designation == "password" and value:
            password = value
    for section in details.get("sections") or []:
        for field in section.get("fields") or []:
            label = " ".join(
                str(field.get(k, "")) for k in ("designation", "name", "title", "t", "label")
            ).lower()
            value = _field_text(field).strip()
            if value.lower().startswith("otpauth://"):
                otp = value
            elif "one-time" in label and value:
                otp = value
    return normalize_username(username), password, otp


def _extract_urls(overview: dict) -> tuple[str, ...]:
    urls = []
    primary = overview.get("url")
    if isinstance(primary, str) and primary.strip():
        urls.append(primary.strip())
    for item in overview.get("urls") or []:
        value = item.get("url") if isinstance(item, dict) else item
        if isinstance(value, str) and value.strip() and value.strip() not in urls:
            urls.append(value.strip())
    return tuple(urls)


def _is_login_item(item: dict) -> bool:
    category = str(item.get("categoryUuid") or item.get("category") or "").lower()
    if category in {"001", "login", "password"}:
        return True
    details = item.get("details") or {}
    return bool(details.get("loginFields"))


def parse_1pux(path: Path) -> list[LoginRecord]:
    data = _load_1pux_json(path)
    records: list[LoginRecord] = []
    for account in data.get("accounts") or []:
        for vault in account.get("vaults") or []:
            vault_name = ((vault.get("attrs") or {}).get("name") or "").strip()
            for item in vault.get("items") or []:
                if not _is_login_item(item):
                    continue
                overview = item.get("overview") or {}
                details = item.get("details") or {}
                urls = _extract_urls(overview)
                username, password, otp = _extract_login_fields(details)
                title = str(overview.get("title") or item.get("title") or "").strip()
                records.append(
                    LoginRecord(
                        source="1password",
                        title=title,
                        url=urls[0] if urls else "",
                        username=username,
                        password=password,
                        notes=details.get("notesPlain") or "",
                        otp=otp,
                        urls=urls,
                        vault=vault_name,
                        item_id=str(item.get("uuid") or ""),
                    )
                )
    return records
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python3 -m pytest tests/test_password_migration_analyze.py::test_parse_1pux_extracts_login_password_username_url_and_totp -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/password-migration-analyze.py tests/test_password_migration_analyze.py
git commit -m "feat: parse 1Password export"
```

## Task 3: Matching And Conflict Classification

**Files:**
- Modify: `scripts/password-migration-analyze.py`
- Modify: `tests/test_password_migration_analyze.py`

- [ ] **Step 1: Write failing tests for classifications**

Append to `tests/test_password_migration_analyze.py`:

```python
def rec(source, title, url, username, password, otp=""):
    return analyzer.LoginRecord(
        source=source,
        title=title,
        url=url,
        username=analyzer.normalize_username(username),
        password=password,
        otp=otp,
        urls=(url,),
    )


def categories(results):
    return [item.category for item in results]


def test_classify_records_detects_safe_present_password_and_otp_conflicts():
    apple = [
        rec("apple", "GitHub", "https://github.com", "user@example.com", "same", "otpauth://totp/a?secret=1"),
        rec("apple", "Google", "https://accounts.google.com", "user@example.com", "old"),
        rec("apple", "Stripe", "https://stripe.com", "user@example.com", "same"),
        rec("apple", "Slack", "https://slack.com", "user@example.com", "same", "otpauth://totp/a?secret=old"),
    ]
    onepassword = [
        rec("1password", "GitHub", "https://github.com/login", "USER@example.com", "same", "otpauth://totp/a?secret=1"),
        rec("1password", "Google", "https://accounts.google.com", "user@example.com", "new"),
        rec("1password", "Stripe", "https://stripe.com", "user@example.com", "same", "otpauth://totp/a?secret=2"),
        rec("1password", "Slack", "https://slack.com", "user@example.com", "same", "otpauth://totp/a?secret=new"),
        rec("1password", "New", "https://new.example.com", "user@example.com", "pw"),
    ]

    results = analyzer.classify_records(apple, onepassword, [])

    assert categories(results) == [
        "already_present",
        "password_differs",
        "apple_missing_otp",
        "otp_differs",
        "safe_import",
    ]


def test_classify_records_marks_missing_username_match_as_ambiguous():
    apple = [rec("apple", "GitHub", "https://github.com", "", "pw")]
    onepassword = [rec("1password", "GitHub", "https://github.com", "user@example.com", "pw")]

    results = analyzer.classify_records(apple, onepassword, [])

    assert results[0].category == "ambiguous_match"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m pytest tests/test_password_migration_analyze.py::test_classify_records_detects_safe_present_password_and_otp_conflicts tests/test_password_migration_analyze.py::test_classify_records_marks_missing_username_match_as_ambiguous -v
```

Expected: FAIL because `classify_records` is not defined.

- [ ] **Step 3: Implement classification**

Append to `scripts/password-migration-analyze.py`:

```python
def index_by_key(records: list[LoginRecord]) -> dict[tuple[str, str], list[LoginRecord]]:
    index: dict[tuple[str, str], list[LoginRecord]] = {}
    for record in records:
        index.setdefault(record.key, []).append(record)
    return index


def find_ambiguous_domain_match(record: LoginRecord, apple_records: list[LoginRecord]) -> LoginRecord | None:
    if not record.domain:
        return None
    for apple in apple_records:
        if apple.domain == record.domain:
            return apple
    return None


def classify_pair(onepassword: LoginRecord, apple: LoginRecord) -> tuple[str, str]:
    if onepassword.password != apple.password:
        return "password_differs", "matching domain and username but password differs"
    if onepassword.has_otp and not apple.has_otp:
        return "apple_missing_otp", "Apple item lacks OTPAuth present in 1Password"
    if onepassword.has_otp and apple.has_otp and onepassword.otp != apple.otp:
        return "otp_differs", "matching item has different OTPAuth"
    return "already_present", "matching item appears equivalent"


def classify_records(
    apple_records: list[LoginRecord],
    onepassword_records: list[LoginRecord],
    pass_entries: list[PassEntry],
) -> list[ClassifiedRecord]:
    apple_index = index_by_key(apple_records)
    pass_index = {(entry.domain_hint, entry.username_hint): entry for entry in pass_entries}
    results: list[ClassifiedRecord] = []
    for record in onepassword_records:
        pass_entry = pass_index.get(record.key)
        pass_path = pass_entry.path if pass_entry else ""
        if not record.domain:
            results.append(
                ClassifiedRecord(record, "unsupported_item", None, "record has no usable URL", pass_path)
            )
            continue
        if not record.username:
            ambiguous = find_ambiguous_domain_match(record, apple_records)
            category = "ambiguous_match" if ambiguous else "safe_import"
            reason = "missing username prevents strong match" if ambiguous else "no Apple match found"
            results.append(ClassifiedRecord(record, category, ambiguous, reason, pass_path))
            continue
        exact = apple_index.get(record.key) or []
        if exact:
            category, reason = classify_pair(record, exact[0])
            results.append(ClassifiedRecord(record, category, exact[0], reason, pass_path))
            continue
        ambiguous = find_ambiguous_domain_match(record, apple_records)
        if ambiguous:
            results.append(
                ClassifiedRecord(
                    record,
                    "ambiguous_match",
                    ambiguous,
                    "domain exists in Apple but username differs or is missing",
                    pass_path,
                )
            )
            continue
        results.append(ClassifiedRecord(record, "safe_import", None, "no Apple match found", pass_path))
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python3 -m pytest tests/test_password_migration_analyze.py::test_classify_records_detects_safe_present_password_and_otp_conflicts tests/test_password_migration_analyze.py::test_classify_records_marks_missing_username_match_as_ambiguous -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/password-migration-analyze.py tests/test_password_migration_analyze.py
git commit -m "feat: classify password migration conflicts"
```

## Task 4: Pass Store Name Scanner

**Files:**
- Modify: `scripts/password-migration-analyze.py`
- Modify: `tests/test_password_migration_analyze.py`

- [ ] **Step 1: Write failing tests for pass scanning**

Append to `tests/test_password_migration_analyze.py`:

```python
def touch_pass_entry(root, name):
    path = root / f"{name}.gpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("encrypted", encoding="utf-8")


def test_scan_pass_store_uses_paths_without_decrypting(tmp_path):
    store = tmp_path / ".password-store"
    touch_pass_entry(store, "github.com/user@example.com")
    touch_pass_entry(store, "api/openai/metaarena")
    touch_pass_entry(store, "notes/appleid-recovery")

    entries = analyzer.scan_pass_store(store)

    by_path = {entry.path: entry for entry in entries}
    assert by_path["github.com/user@example.com"].domain_hint == "github.com"
    assert by_path["github.com/user@example.com"].username_hint == "user@example.com"
    assert by_path["github.com/user@example.com"].is_likely_login is True
    assert by_path["api/openai/metaarena"].namespace == "api"
    assert by_path["api/openai/metaarena"].is_likely_login is False
    assert by_path["notes/appleid-recovery"].namespace == "notes"
    assert by_path["notes/appleid-recovery"].is_likely_login is False
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m pytest tests/test_password_migration_analyze.py::test_scan_pass_store_uses_paths_without_decrypting -v
```

Expected: FAIL because `scan_pass_store` is not defined.

- [ ] **Step 3: Implement pass store scanner**

Append to `scripts/password-migration-analyze.py`:

```python
def scan_pass_store(root: Path) -> list[PassEntry]:
    if not root.exists():
        raise ValueError(f"pass store does not exist: {root}")
    entries: list[PassEntry] = []
    for path in sorted(root.rglob("*.gpg")):
        rel = path.relative_to(root).with_suffix("")
        parts = rel.parts
        if not parts:
            continue
        namespace = parts[0]
        is_likely_login = namespace not in NON_LOGIN_NAMESPACES
        domain_hint = normalize_domain(parts[0]) if is_likely_login else ""
        username_hint = normalize_username(parts[1]) if is_likely_login and len(parts) >= 2 else ""
        if is_likely_login and len(parts) == 1:
            username_hint = ""
        entries.append(
            PassEntry(
                path="/".join(parts),
                domain_hint=domain_hint,
                username_hint=username_hint,
                namespace=namespace,
                is_likely_login=is_likely_login,
            )
        )
    return entries
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python3 -m pytest tests/test_password_migration_analyze.py::test_scan_pass_store_uses_paths_without_decrypting -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/password-migration-analyze.py tests/test_password_migration_analyze.py
git commit -m "feat: scan pass store names"
```

## Task 5: Redacted Report Writers And Sensitive Safe Import CSV

**Files:**
- Modify: `scripts/password-migration-analyze.py`
- Modify: `tests/test_password_migration_analyze.py`

- [ ] **Step 1: Write failing tests for report output and redaction**

Append to `tests/test_password_migration_analyze.py`:

```python
def test_write_reports_redacts_conflicts_but_keeps_safe_import_sensitive(tmp_path):
    out = tmp_path / "report"
    onepassword = [
        rec("1password", "New", "https://new.example.com", "user@example.com", "new-secret", "otpauth://totp/New:user?secret=ABC"),
        rec("1password", "GitHub", "https://github.com", "user@example.com", "onepassword-secret"),
    ]
    apple = [rec("apple", "GitHub", "https://github.com", "user@example.com", "apple-secret")]
    results = analyzer.classify_records(apple, onepassword, [])

    analyzer.write_reports(out, apple, onepassword, [], results)

    summary = (out / "summary.md").read_text(encoding="utf-8")
    conflicts = (out / "conflicts.csv").read_text(encoding="utf-8")
    safe_import = (out / "safe-import.csv").read_text(encoding="utf-8")
    review = (out / "review.md").read_text(encoding="utf-8")

    assert "safe_import: 1" in summary
    assert "password_differs: 1" in summary
    assert "onepassword-secret" not in conflicts
    assert "apple-secret" not in conflicts
    assert "otpauth://totp/New:user?secret=ABC" not in conflicts
    assert "onepassword-secret" not in review
    assert "new-secret" in safe_import
    assert "otpauth://totp/New:user?secret=ABC" in safe_import
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m pytest tests/test_password_migration_analyze.py::test_write_reports_redacts_conflicts_but_keeps_safe_import_sensitive -v
```

Expected: FAIL because `write_reports` is not defined.

- [ ] **Step 3: Implement report writers**

Append to `scripts/password-migration-analyze.py`:

```python
def ensure_private_report_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, stat.S_IRWXU)
    except PermissionError:
        pass


def count_by_category(results: list[ClassifiedRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.category] = counts.get(result.category, 0) + 1
    return dict(sorted(counts.items()))


def report_row(result: ClassifiedRecord) -> dict[str, str | int | bool]:
    onep = result.onepassword
    apple = result.apple
    return {
        "category": result.category,
        "reason": result.reason,
        "title": onep.title,
        "domain": onep.domain,
        "username": redact_username(onep.username),
        "username_hash": short_hash(onep.username),
        "onepassword_vault": onep.vault,
        "onepassword_item_id": onep.item_id,
        "onepassword_has_otp": onep.has_otp,
        "apple_has_otp": apple.has_otp if apple else False,
        "password_same": (onep.password == apple.password) if apple else False,
        "otp_same": (onep.otp == apple.otp) if apple else False,
        "onepassword_password_len": len(onep.password),
        "apple_password_len": len(apple.password) if apple else 0,
        "onepassword_url_count": len(onep.urls),
        "pass_path": result.pass_path,
    }


def write_safe_import(path: Path, results: list[ClassifiedRecord]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=APPLE_FIELDS)
        writer.writeheader()
        for result in results:
            if result.category != "safe_import":
                continue
            record = result.onepassword
            writer.writerow(
                {
                    "Title": record.title,
                    "URL": record.url,
                    "Username": record.username,
                    "Password": record.password,
                    "Notes": record.notes,
                    "OTPAuth": record.otp,
                }
            )


def write_conflicts(path: Path, results: list[ClassifiedRecord]) -> None:
    fields = [
        "category",
        "reason",
        "title",
        "domain",
        "username",
        "username_hash",
        "onepassword_vault",
        "onepassword_item_id",
        "onepassword_has_otp",
        "apple_has_otp",
        "password_same",
        "otp_same",
        "onepassword_password_len",
        "apple_password_len",
        "onepassword_url_count",
        "pass_path",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for result in results:
            if result.category == "safe_import":
                continue
            writer.writerow(report_row(result))


def write_pass_coverage(path: Path, pass_entries: list[PassEntry]) -> None:
    fields = ["path", "namespace", "is_likely_login", "domain_hint", "username_hint_hash", "username_hint"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for entry in pass_entries:
            writer.writerow(
                {
                    "path": entry.path,
                    "namespace": entry.namespace,
                    "is_likely_login": entry.is_likely_login,
                    "domain_hint": entry.domain_hint,
                    "username_hint_hash": short_hash(entry.username_hint),
                    "username_hint": redact_username(entry.username_hint),
                }
            )


def write_summary(path: Path, apple: list[LoginRecord], onep: list[LoginRecord], pass_entries: list[PassEntry], results: list[ClassifiedRecord]) -> None:
    counts = count_by_category(results)
    lines = [
        "# Password Migration Report",
        "",
        "## Inputs",
        "",
        f"- Apple records: {len(apple)}",
        f"- 1Password login records: {len(onep)}",
        f"- pass entries scanned: {len(pass_entries)}",
        "",
        "## Classification Counts",
        "",
    ]
    for category, count in counts.items():
        lines.append(f"- {category}: {count}")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `safe-import.csv` is plaintext-sensitive and contains passwords and OTPAuth URLs.",
            "- `conflicts.csv`, `pass-coverage.csv`, and `review.md` are redacted review artifacts.",
            "- No Apple Passwords, 1Password, or pass data was modified by this analyzer.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_review(path: Path, results: list[ClassifiedRecord]) -> None:
    lines = ["# Migration Review", ""]
    for category in sorted({result.category for result in results}):
        lines.extend([f"## {category}", ""])
        for result in [item for item in results if item.category == category][:100]:
            row = report_row(result)
            lines.append(
                f"- {row['domain']} `{row['username']}`: {row['reason']} "
                f"(1P OTP={row['onepassword_has_otp']}, Apple OTP={row['apple_has_otp']}, pass={row['pass_path'] or 'no'})"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_reports(
    out_dir: Path,
    apple: list[LoginRecord],
    onep: list[LoginRecord],
    pass_entries: list[PassEntry],
    results: list[ClassifiedRecord],
) -> None:
    ensure_private_report_dir(out_dir)
    write_summary(out_dir / "summary.md", apple, onep, pass_entries, results)
    write_safe_import(out_dir / "safe-import.csv", results)
    write_conflicts(out_dir / "conflicts.csv", results)
    write_pass_coverage(out_dir / "pass-coverage.csv", pass_entries)
    write_review(out_dir / "review.md", results)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python3 -m pytest tests/test_password_migration_analyze.py::test_write_reports_redacts_conflicts_but_keeps_safe_import_sensitive -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/password-migration-analyze.py tests/test_password_migration_analyze.py
git commit -m "feat: write migration analysis reports"
```

## Task 6: CLI, Repository Output Guard, And End-To-End Test

**Files:**
- Modify: `scripts/password-migration-analyze.py`
- Modify: `tests/test_password_migration_analyze.py`

- [ ] **Step 1: Write failing end-to-end CLI tests**

Append to `tests/test_password_migration_analyze.py`:

```python
def test_main_generates_report_with_optional_pass_store(tmp_path):
    apple_csv = tmp_path / "apple.csv"
    onepux = tmp_path / "onepassword.1pux"
    pass_store = tmp_path / ".password-store"
    out = tmp_path / "out"

    write_csv(
        apple_csv,
        [
            {
                "Title": "GitHub",
                "URL": "https://github.com",
                "Username": "user@example.com",
                "Password": "old",
                "Notes": "",
                "OTPAuth": "",
            }
        ],
    )
    write_1pux(
        onepux,
        {
            "accounts": [
                {
                    "vaults": [
                        {
                            "attrs": {"name": "Private"},
                            "items": [
                                {
                                    "uuid": "item-1",
                                    "categoryUuid": "001",
                                    "overview": {"title": "GitHub", "url": "https://github.com"},
                                    "details": {
                                        "loginFields": [
                                            {"designation": "username", "value": "user@example.com"},
                                            {"designation": "password", "value": "new"},
                                        ]
                                    },
                                },
                                {
                                    "uuid": "item-2",
                                    "categoryUuid": "001",
                                    "overview": {"title": "New", "url": "https://new.example.com"},
                                    "details": {
                                        "loginFields": [
                                            {"designation": "username", "value": "user@example.com"},
                                            {"designation": "password", "value": "pw"},
                                        ]
                                    },
                                },
                            ],
                        }
                    ]
                }
            ]
        },
    )
    touch_pass_entry(pass_store, "github.com/user@example.com")

    exit_code = analyzer.main(
        [
            "--apple-csv",
            str(apple_csv),
            "--onepassword-1pux",
            str(onepux),
            "--pass-store",
            str(pass_store),
            "--out",
            str(out),
        ]
    )

    assert exit_code == 0
    assert (out / "summary.md").exists()
    assert (out / "safe-import.csv").exists()
    assert (out / "conflicts.csv").exists()
    assert (out / "pass-coverage.csv").exists()


def test_main_refuses_output_inside_repo_without_override(tmp_path, monkeypatch):
    apple_csv = tmp_path / "apple.csv"
    onepux = tmp_path / "onepassword.1pux"
    write_csv(apple_csv, [])
    write_1pux(onepux, {"accounts": []})
    repo_out = REPO_ROOT / "tmp-password-report-test"

    try:
        exit_code = analyzer.main(
            [
                "--apple-csv",
                str(apple_csv),
                "--onepassword-1pux",
                str(onepux),
                "--out",
                str(repo_out),
            ]
        )
        assert exit_code == 2
    finally:
        if repo_out.exists():
            for child in repo_out.iterdir():
                child.unlink()
            repo_out.rmdir()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m pytest tests/test_password_migration_analyze.py::test_main_generates_report_with_optional_pass_store tests/test_password_migration_analyze.py::test_main_refuses_output_inside_repo_without_override -v
```

Expected: FAIL because `main` and output guard are not implemented.

- [ ] **Step 3: Implement CLI**

Append to `scripts/password-migration-analyze.py`:

```python
def path_is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze 1Password to Apple Passwords migration conflicts.")
    parser.add_argument("--apple-csv", required=True, type=Path, help="Apple Passwords CSV export")
    parser.add_argument("--onepassword-1pux", required=True, type=Path, help="1Password .1pux export")
    parser.add_argument("--pass-store", type=Path, help="Optional pass store path, default not scanned")
    parser.add_argument("--out", required=True, type=Path, help="Output report directory outside the repository")
    parser.add_argument(
        "--allow-repo-output",
        action="store_true",
        help="Allow writing report output inside the current repository",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    if path_is_inside(args.out, repo_root) and not args.allow_repo_output:
        print(
            f"error: refusing to write report inside repository: {args.out}",
            file=sys.stderr,
        )
        print("use --allow-repo-output to override", file=sys.stderr)
        return 2

    apple = parse_apple_csv(args.apple_csv.expanduser())
    onep = parse_1pux(args.onepassword_1pux.expanduser())
    pass_entries = scan_pass_store(args.pass_store.expanduser()) if args.pass_store else []
    results = classify_records(apple, onep, pass_entries)
    write_reports(args.out.expanduser(), apple, onep, pass_entries, results)

    counts = count_by_category(results)
    print(f"Wrote report to {args.out}")
    for category, count in counts.items():
        print(f"{category}: {count}")
    print("warning: safe-import.csv is plaintext-sensitive")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
python3 -m pytest tests/test_password_migration_analyze.py::test_main_generates_report_with_optional_pass_store tests/test_password_migration_analyze.py::test_main_refuses_output_inside_repo_without_override -v
```

Expected: PASS.

- [ ] **Step 5: Run the full test suite for the analyzer**

Run:

```bash
python3 -m pytest tests/test_password_migration_analyze.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/password-migration-analyze.py tests/test_password_migration_analyze.py
git commit -m "feat: add password migration analyzer cli"
```

## Task 7: Real Export Smoke Test

**Files:**
- No code changes expected.
- Read local export files supplied by the user.
- Write reports outside the repository.

- [ ] **Step 1: Confirm sensitive export paths exist without printing contents**

Run:

```bash
ls -l ~/tmp/Passwords.csv ~/tmp/1password.1pux
```

Expected: both files exist. Do not print file contents.

- [ ] **Step 2: Run analyzer against real exports**

Run:

```bash
python3 scripts/password-migration-analyze.py \
  --apple-csv ~/tmp/Passwords.csv \
  --onepassword-1pux ~/tmp/1password.1pux \
  --pass-store ~/.password-store \
  --out ~/tmp/password-migration-report
```

Expected: command exits 0, prints category counts, and warns that `safe-import.csv` is plaintext-sensitive.

- [ ] **Step 3: Inspect only redacted report surfaces**

Run:

```bash
sed -n '1,160p' ~/tmp/password-migration-report/summary.md
wc -l ~/tmp/password-migration-report/conflicts.csv ~/tmp/password-migration-report/pass-coverage.csv ~/tmp/password-migration-report/safe-import.csv
```

Expected: summary contains aggregate counts. `wc -l` shows output sizes without printing secrets.

- [ ] **Step 4: Check that redacted reports do not contain raw OTPAuth URLs**

Run:

```bash
rg 'otpauth://' ~/tmp/password-migration-report/summary.md ~/tmp/password-migration-report/conflicts.csv ~/tmp/password-migration-report/review.md ~/tmp/password-migration-report/pass-coverage.csv
```

Expected: no matches. It is expected that `safe-import.csv` may contain `otpauth://`.

- [ ] **Step 5: Commit any smoke-test fixes**

If code changes were needed:

```bash
git add scripts/password-migration-analyze.py tests/test_password_migration_analyze.py
git commit -m "fix: handle real password export shape"
```

If no code changes were needed, do not commit.

## Self-Review

- Spec coverage: required Apple CSV and 1Password 1PUX inputs are parsed; optional `pass` store scanning is default non-decrypting; report files match the spec; output guard prevents accidental repository reports; no Apple import or `pass` mutation is included.
- Placeholder scan: no task uses unfinished-work markers; each task has exact files, commands, and expected results.
- Type consistency: `LoginRecord`, `PassEntry`, and `ClassifiedRecord` are introduced before use; function names are consistent across tests and implementation steps.
