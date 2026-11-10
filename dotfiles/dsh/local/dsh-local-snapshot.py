#!/usr/bin/python3
"""Read-only local-state archiving with a self-contained npm dependency graph.

archive_state(state, archive_path) publishes a new, mode-0600 uncompressed tar
(root: ``state``), or raises ValueError/OSError/tarfile.TarError without publishing
an incomplete archive. The caller creates the destination directory, stops state
writers, and prevents concurrent npm cache installs/cleanup. No source is changed.
Only absolute package-root links directly in profiles/node_modules (including
scopes) may refer outside state, and only into the canonical sibling HOME's
.npm/_npx/<hex>/node_modules. Every referenced node_modules is embedded in full.
The existing VM restore filter remains unchanged; it needs no external-link bypass.
"""

from collections import deque
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
import tempfile


_RESERVED = ".dsh-local-package-cache"
_HEX = re.compile(r"[0-9a-f]+\Z")
_PACKAGE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._~-]*\Z")


def _fail(message):
    raise ValueError("Local archiver cannot create a restorable snapshot: " + message)


def _package_parts(parts):
    """Consume one npm package name (unscoped or scoped)."""
    if not parts:
        return 0
    if parts[0].startswith("@"):
        return (2 if len(parts) >= 2 and _PACKAGE.fullmatch(parts[0][1:])
                and _PACKAGE.fullmatch(parts[1]) else 0)
    return 1 if _PACKAGE.fullmatch(parts[0]) else 0


def _external_root(source, state, link):
    relative = source.relative_to(state).parts
    package = relative[2:] if relative[:2] == ("profiles", "node_modules") else ()
    if not package or _package_parts(package) != len(package):
        _fail("absolute/external link is not a shared profile package root")
    target = Path(link)
    # Compare the spelling as well as the resolved path: no traversal, aliases,
    # alternate HOME, or symlinked cache ancestors are an allowlist match.
    if not target.is_absolute() or str(target) != link or ".." in target.parts:
        _fail("non-canonical external package target")
    prefix = state.parent / ".npm" / "_npx"
    try:
        parts = target.relative_to(prefix).parts
    except ValueError:
        _fail("external package target is outside the canonical HOME npm cache")
    if len(parts) < 3 or not _HEX.fullmatch(parts[0]) or parts[1] != "node_modules":
        _fail("external package target is not an allowlisted npx package")
    rest = parts[2:]
    while rest:
        count = _package_parts(rest)
        if not count:
            _fail("external target is not a package-root path")
        rest = rest[count:]
        if rest:
            if rest[0] != "node_modules" or len(rest) == 1:
                _fail("external target is not a package-root path")
            rest = rest[1:]
    root = prefix / parts[0] / "node_modules"
    if target.resolve(strict=True) != target or not target.is_dir():
        _fail("external package target has a symlink ancestor or is not a directory")
    # The target check above also covers every ancestor of node_modules.
    return root, PurePosixPath("state", _RESERVED, "npx-" + parts[0], "node_modules", *parts[2:])


def _scan(root, archive_root):
    """List lstat-only entries, never descending through directory symlinks."""
    entries = []
    pending = deque([(root, archive_root)])
    while pending:
        source, name = pending.popleft()
        info = source.lstat()
        if stat.S_ISLNK(info.st_mode):
            link = os.readlink(source)
        elif stat.S_ISDIR(info.st_mode):
            link = None
            pending.extend((child, name / child.name) for child in sorted(source.iterdir()))
        elif stat.S_ISREG(info.st_mode):
            link = None
        else:
            _fail("source contains a special file")
        entries.append((source, name, info, link))
    return entries


def _resolved_link(name, links, boundary):
    """Resolve the complete archive's virtual link graph, including forward links."""
    def resolve(base, parts, active):
        for part in parts:
            if part in ("", "."):
                continue
            if part == "..":
                if len(base) <= len(boundary.parts):
                    _fail("archive link escapes its state/cache root")
                base = base[:-1]
                continue
            base = base + (part,)
            key = PurePosixPath(*base)
            if key in links:
                if key in active:
                    _fail("source contains a symlink cycle")
                target = PurePosixPath(links[key])
                if target.is_absolute():
                    _fail("source contains an unsupported absolute link")
                base = resolve(base[:-1], target.parts, active | {key})
        return base

    result = PurePosixPath(*resolve(name.parent.parts, PurePosixPath(links[name]).parts, {name}))
    if not result.is_relative_to(boundary):
        _fail("archive link escapes its state/cache root")


def archive_state(state: Path, archive_path: Path) -> None:
    """Publish a private, strictly restorable tar without modifying live state.

    Existing embedded caches are ordinary state on later snapshots. A newly
    needed npx-<hex> destination must not already exist (even if its bytes appear
    identical); ambiguous reserved-name collisions fail closed. Existing archive
    destinations are never replaced. Failed writes leave no published archive.
    """
    state = Path(state).absolute()
    archive_path = Path(archive_path).absolute()
    if state.is_symlink() or not state.is_dir() or state.resolve(strict=True) != state:
        _fail("state must be an existing canonical real directory")
    if archive_path.exists() or archive_path.is_symlink():
        raise FileExistsError("Snapshot archive destination already exists")
    destination = archive_path.parent.resolve(strict=True) / archive_path.name
    if destination.is_relative_to(state):
        _fail("archive destination must be outside live state")
    reserved = state / _RESERVED
    if reserved.is_symlink() or (reserved.exists() and not reserved.is_dir()):
        _fail("reserved package-cache destination is not a real directory")

    entries = _scan(state, PurePosixPath("state"))
    links = {}
    roots = {}
    for source, name, info, link in entries:
        if link is None:
            continue
        if Path(link).is_absolute():
            root, embedded = _external_root(source, state, link)
            roots[root] = PurePosixPath("state", _RESERVED, "npx-" + root.parent.name, "node_modules")
            links[name] = os.path.relpath(str(embedded), str(name.parent))
        else:
            links[name] = link

    # Validate every byte-bearing cache tree, not just directly linked packages:
    # hoisted/unlinked optional native packages and nested versions are essential.
    cache_entries = []
    synthetic = []
    if roots and not reserved.exists():
        synthetic.append(PurePosixPath("state", _RESERVED))
    for root, embedded in sorted(roots.items()):
        cache_destination = state / _RESERVED / embedded.parent.name
        if cache_destination.exists() or cache_destination.is_symlink():
            _fail("reserved npx package-cache destination already exists")
        if root.is_symlink() or not root.is_dir() or root.resolve(strict=True) != root:
            _fail("npx node_modules root must be a canonical real directory")
        if destination.is_relative_to(root):
            _fail("archive destination must be outside the source npm cache")
        synthetic.append(embedded.parent)
        scanned = _scan(root, embedded)
        for source, name, info, link in scanned:
            if link is None:
                continue
            if Path(link).is_absolute():
                _fail("npm cache contains an absolute symlink")
            links[name] = link
        cache_entries.extend(scanned)

    for name, link in links.items():
        if PurePosixPath(link).is_absolute():
            _fail("source contains an unsupported absolute link")
        boundary = PurePosixPath("state")
        for embedded in roots.values():
            if name.is_relative_to(embedded):
                boundary = embedded
                break
        _resolved_link(name, links, boundary)

    # Publish only the finished archive, exclusively. tempfile creates mode 0600
    # from the outset, regardless of the process umask. Its context removes only
    # this helper's temporary file, never any state or npm cache path.
    with tempfile.NamedTemporaryFile(prefix=".dsh-local-state-", suffix=".tar",
                                     dir=archive_path.parent) as temporary:
        with tarfile.open(fileobj=temporary, mode="w", dereference=False) as archive:
            for name in synthetic:
                member = tarfile.TarInfo(str(name))
                member.type = tarfile.DIRTYPE
                member.mode = 0o700
                archive.addfile(member)
            for source, name, before, link in entries + cache_entries:
                now = source.lstat()
                if ((now.st_dev, now.st_ino, now.st_mode) !=
                        (before.st_dev, before.st_ino, before.st_mode)):
                    _fail("source changed during snapshot")
                # Store each regular file's payload instead of synthesizing
                # hardlinks across the live-state/cache boundary.
                archive.inodes.clear()
                member = archive.gettarinfo(str(source), arcname=str(name))
                if link is not None:
                    if not member.issym() or os.readlink(source) != link:
                        _fail("source link changed during snapshot")
                    member.linkname = links[name]
                    archive.addfile(member)
                elif member.isfile():
                    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
                    with os.fdopen(fd, "rb") as payload:
                        opened = os.fstat(payload.fileno())
                        if ((opened.st_dev, opened.st_ino, opened.st_mode, opened.st_size) !=
                                (now.st_dev, now.st_ino, now.st_mode, member.size)):
                            _fail("source file changed during snapshot")
                        archive.addfile(member, payload)
                elif member.isdir():
                    archive.addfile(member)
                else:
                    _fail("source type changed during snapshot")
        temporary.flush()
        os.fsync(temporary.fileno())
        os.link(temporary.name, archive_path, follow_symlinks=False)
