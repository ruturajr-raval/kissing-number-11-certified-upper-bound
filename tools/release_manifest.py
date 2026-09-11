#!/usr/bin/env python3
"""Generate or verify the repository release manifest."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import secrets
import stat
import subprocess


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "release-manifest.sha256"
GIT_EXECUTABLE = Path("/usr/bin/git")
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
EXCLUDED_PARTS = {
    ".git",
    ".julia",
    ".pytest_cache",
    "__pycache__",
    "build",
}
EXCLUDED_PATHS = {
    "release-manifest.sha256",
}


def configure_root(value: str | os.PathLike[str]) -> None:
    global ROOT, MANIFEST
    root = Path(value).resolve(strict=True)
    if not root.is_dir():
        raise RuntimeError(f"repository root is not a directory: {root}")
    ROOT = root
    MANIFEST = ROOT / "release-manifest.sha256"


def git_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["GIT_CONFIG_GLOBAL"] = "/dev/null"
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    return environment


def git_run(
    arguments: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    if not GIT_EXECUTABLE.is_file():
        raise RuntimeError(f"Git executable does not exist: {GIT_EXECUTABLE}")
    return subprocess.run(
        [
            str(GIT_EXECUTABLE),
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "-c",
            "core.useReplaceRefs=false",
            *arguments,
        ],
        cwd=ROOT,
        env=git_environment(),
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def git_bytes(arguments: list[str]) -> bytes:
    return git_run(arguments).stdout


def git_returncode(arguments: list[str]) -> int:
    return git_run(arguments, check=False).returncode


def git_paths(arguments: list[str]) -> tuple[str, ...]:
    return tuple(
        item.decode("utf-8")
        for item in git_bytes(arguments).split(b"\0")
        if item
    )


def eligible(name: str) -> bool:
    relative = Path(name)
    return not (
        any(part in EXCLUDED_PARTS for part in relative.parts)
        or relative.parts[:2] == ("dist", "release")
        or name in EXCLUDED_PATHS
        or name == ".DS_Store"
    )


def manifest_paths() -> tuple[str, ...]:
    untracked = tuple(
        name
        for name in git_paths(
            ["ls-files", "-z", "--others", "--exclude-standard"]
        )
        if eligible(name)
    )
    if untracked:
        listing = "\n".join(f"  {name}" for name in sorted(untracked))
        raise RuntimeError(
            "release-relevant files are not tracked by Git:\n" + listing
        )
    return tuple(
        sorted(
            name
            for name in git_paths(["ls-files", "-z"])
            if eligible(name)
        )
    )


def resolve_path(name: str) -> Path:
    relative = PurePosixPath(name)
    if (
        relative.is_absolute()
        or name != relative.as_posix()
        or any(part in ("", ".", "..") for part in relative.parts)
    ):
        raise RuntimeError(f"tracked release path is unsafe: {name}")
    candidate = ROOT.joinpath(*relative.parts)
    root = ROOT.resolve(strict=True)
    try:
        parent = candidate.parent.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(f"cannot resolve tracked release path {name}: {exc}") from exc
    if parent != root and root not in parent.parents:
        raise RuntimeError(f"tracked release path escapes repository: {name}")
    return candidate


def digest(name: str) -> str:
    path = resolve_path(name)
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(f"cannot open tracked release path {name}: {exc}") from exc
    hasher = hashlib.sha256()
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError(f"tracked release path is not regular: {name}")
        remaining = before.st_size
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            if not block:
                raise RuntimeError(f"tracked release path changed while reading: {name}")
            hasher.update(block)
            remaining -= len(block)
        if os.read(descriptor, 1):
            raise RuntimeError(f"tracked release path changed while reading: {name}")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if identity_before != identity_after:
        raise RuntimeError(f"tracked release path changed while reading: {name}")
    return hasher.hexdigest()


def expected() -> str:
    return "".join(
        f"{digest(name)}  {name}\n"
        for name in manifest_paths()
    )


def validate_commit(value: str) -> str:
    if len(value) != 40 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise RuntimeError("expected release commit must be a lowercase Git SHA-1")
    return value


def require_repository_root() -> None:
    try:
        value = git_bytes(["rev-parse", "--show-toplevel"]).decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise RuntimeError("Git returned a non-UTF-8 repository root") from exc
    try:
        actual = Path(value).resolve(strict=True)
        expected_root = ROOT.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError(f"cannot resolve Git repository root: {exc}") from exc
    if actual != expected_root:
        raise RuntimeError(
            f"Git repository root mismatch: expected {expected_root}, got {actual}"
        )


def current_commit() -> str:
    try:
        value = git_bytes(["rev-parse", "HEAD"]).decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise RuntimeError("Git returned a non-ASCII release commit") from exc
    return validate_commit(value)


def require_clean_commit(expected_commit: str) -> str:
    expected_value = validate_commit(expected_commit)
    require_repository_root()
    before = current_commit()
    if before != expected_value:
        raise RuntimeError(
            f"release commit mismatch: expected {expected_value}, got {before}"
        )
    status = git_bytes(
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"]
    )
    if status:
        raise RuntimeError("release worktree is not clean")
    difference = git_returncode(
        ["diff", "--no-ext-diff", "--quiet", expected_value, "--"]
    )
    if difference == 1:
        raise RuntimeError("release worktree differs from the expected commit")
    if difference != 0:
        raise RuntimeError(
            f"Git could not compare the release worktree, exit code {difference}"
        )
    after = current_commit()
    if after != expected_value:
        raise RuntimeError(
            f"release commit changed during verification: {after}"
        )
    return expected_value


def commit_tree_entries(commit: str) -> tuple[tuple[str, str], ...]:
    output: list[tuple[str, str]] = []
    records = git_bytes(
        ["ls-tree", "-r", "-z", "--full-tree", validate_commit(commit)]
    )
    for record in records.split(b"\0"):
        if not record:
            continue
        try:
            metadata, encoded_name = record.split(b"\t", 1)
            mode, object_type, object_id = metadata.split(b" ", 2)
            name = encoded_name.decode("utf-8")
            object_token = object_id.decode("ascii")
        except (UnicodeDecodeError, ValueError) as exc:
            raise RuntimeError("Git returned a malformed commit-tree entry") from exc
        if not eligible(name):
            continue
        if (
            object_type != b"blob"
            or mode not in (b"100644", b"100755")
            or "\n" in name
            or "\r" in name
        ):
            raise RuntimeError(f"unsupported release tree entry: {name}")
        output.append((name, object_token))
    return tuple(sorted(output))


def expected_from_commit(commit: str) -> str:
    lines = []
    for name, object_id in commit_tree_entries(commit):
        content = git_bytes(["cat-file", "blob", object_id])
        lines.append(f"{hashlib.sha256(content).hexdigest()}  {name}\n")
    return "".join(lines)


def read_manifest() -> str:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(MANIFEST, flags)
    except OSError as exc:
        raise RuntimeError(f"cannot open release manifest: {exc}") from exc
    chunks: list[bytes] = []
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError("release manifest is not a regular file")
        if before.st_size > MAX_MANIFEST_BYTES:
            raise RuntimeError("release manifest exceeds its size limit")
        remaining = before.st_size
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            if not block:
                raise RuntimeError("release manifest changed while reading")
            chunks.append(block)
            remaining -= len(block)
        if os.read(descriptor, 1):
            raise RuntimeError("release manifest changed while reading")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise RuntimeError("release manifest changed while reading")
    try:
        return b"".join(chunks).decode("ascii")
    except UnicodeDecodeError as exc:
        raise RuntimeError("release manifest must be ASCII") from exc


def write_all(descriptor: int, content: bytes) -> None:
    view = memoryview(content)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise RuntimeError("short write while creating release manifest")
        view = view[written:]


def write_manifest(content: str) -> None:
    encoded = content.encode("ascii")
    temporary = ROOT / (
        f".release-manifest.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o644)
    try:
        write_all(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(temporary, MANIFEST)
        root_descriptor = os.open(
            ROOT,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(root_descriptor)
        finally:
            os.close(root_descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=ROOT,
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument("--expected-commit")
    args = parser.parse_args()
    configure_root(args.repository_root)
    if args.require_clean != bool(args.expected_commit):
        parser.error("--require-clean and --expected-commit must be used together")
    if args.require_clean and not args.check:
        parser.error("clean commit verification requires --check")

    if args.check:
        commit = (
            require_clean_commit(args.expected_commit)
            if args.require_clean
            else None
        )
        content = (
            expected_from_commit(commit)
            if commit is not None
            else expected()
        )
        if commit is not None and expected() != content:
            raise RuntimeError(
                "working-tree release files differ from the expected commit tree"
            )
        if read_manifest() != content:
            print("release-manifest.sha256 is stale")
            return 1
        if commit is not None:
            require_clean_commit(commit)
            if expected() != content:
                raise RuntimeError(
                    "working-tree release files changed during verification"
                )
        suffix = f" at commit {commit}" if commit else ""
        print(f"verified {content.count(chr(10))} manifest entries{suffix}")
        return 0

    content = expected()
    write_manifest(content)
    print(f"wrote {content.count(chr(10))} manifest entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
