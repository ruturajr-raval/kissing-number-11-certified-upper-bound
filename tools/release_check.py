#!/usr/bin/env python3
"""Run the Project 10 release gate without shell-composed trust anchors."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Iterator


ROOT = Path(__file__).resolve().parents[1]
MAKE_EXECUTABLE = Path("/usr/bin/make")
GIT_EXECUTABLE = Path("/usr/bin/git")
SAFE_PATH = re.compile(r"[/A-Za-z0-9._+-]+\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SHA1 = re.compile(r"[0-9a-f]{40}\Z")
EXPECTED_JULIA_VERSION = "1.12.7"
RUNTIME_TREE_FORMAT = b"KN11-RUNTIME-TREE-V1\0"

MANIFEST_ENV = "KN11_EXPECTED_MANIFEST_SHA256"
WITNESS_ENV = "KN11_EXPECTED_WITNESS_SHA256"
SOURCE_ENV = "KN11_EXPECTED_SOURCE_SPECIFICATION"
ROUNDING_ENV = "KN11_EXPECTED_ROUNDING_SPECIFICATION"
VERIFICATION_ENV = "KN11_EXPECTED_VERIFICATION_SPECIFICATION"
COMMIT_ENV = "KN11_EXPECTED_RELEASE_COMMIT"
JULIA_ENV = "KN11_EXPECTED_JULIA_SHA256"
JULIA_TREE_ENV = "KN11_EXPECTED_JULIA_TREE_SHA256"


@dataclass(frozen=True)
class ReleaseAnchors:
    manifest: str
    witness: str
    source_specification: str
    rounding_specification: str
    verification_specification: str
    commit: str | None
    julia: str | None
    julia_tree: str | None


def configure_root(value: str | os.PathLike[str]) -> None:
    global ROOT
    root = Path(value).resolve(strict=True)
    if not root.is_dir():
        raise RuntimeError(f"repository root is not a directory: {root}")
    ROOT = root


def required_hex(name: str, pattern: re.Pattern[str]) -> str:
    value = os.environ.get(name, "")
    if pattern.fullmatch(value) is None:
        raise RuntimeError(f"{name} is missing or malformed")
    return value


def load_anchors(
    *,
    require_commit: bool,
    require_julia: bool,
) -> ReleaseAnchors:
    return ReleaseAnchors(
        manifest=required_hex(MANIFEST_ENV, SHA256),
        witness=required_hex(WITNESS_ENV, SHA256),
        source_specification=required_hex(SOURCE_ENV, SHA256),
        rounding_specification=required_hex(ROUNDING_ENV, SHA256),
        verification_specification=required_hex(VERIFICATION_ENV, SHA256),
        commit=required_hex(COMMIT_ENV, SHA1) if require_commit else None,
        julia=required_hex(JULIA_ENV, SHA256) if require_julia else None,
        julia_tree=(
            required_hex(JULIA_TREE_ENV, SHA256)
            if require_julia
            else None
        ),
    )


def resolve_executable(value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        located = shutil.which(value)
        if located is None:
            raise RuntimeError(f"required executable was not found: {value}")
        candidate = Path(located)
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise RuntimeError(f"required executable is not runnable: {resolved}")
    if SAFE_PATH.fullmatch(str(resolved)) is None:
        raise RuntimeError(f"executable path is unsafe for release use: {resolved}")
    return resolved


def directory_flags() -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    return flags


def regular_read_flags() -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    return flags


def file_identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def directory_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def digest_record(digest: "hashlib._Hash", *fields: bytes) -> None:
    for field in fields:
        digest.update(len(field).to_bytes(8, "big"))
        digest.update(field)


def stable_regular_sha256_at(
    parent_descriptor: int,
    name: str,
    expected: os.stat_result,
) -> bytes:
    descriptor = os.open(
        name,
        regular_read_flags(),
        dir_fd=parent_descriptor,
    )
    digest = hashlib.sha256()
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or (before.st_dev, before.st_ino)
            != (expected.st_dev, expected.st_ino)
        ):
            raise RuntimeError(f"runtime file identity mismatch: {name}")
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    current = os.stat(
        name,
        dir_fd=parent_descriptor,
        follow_symlinks=False,
    )
    if (
        file_identity(before) != file_identity(after)
        or file_identity(after) != file_identity(current)
    ):
        raise RuntimeError(f"runtime file changed while hashing: {name}")
    return digest.digest()


def update_runtime_tree_digest(
    digest: "hashlib._Hash",
    directory_descriptor: int,
    prefix: bytes,
) -> None:
    before = os.fstat(directory_descriptor)
    names = sorted(os.listdir(directory_descriptor), key=os.fsencode)
    for name in names:
        if "/" in name or "\0" in name:
            raise RuntimeError("runtime tree contains an unsafe path component")
        encoded_name = os.fsencode(name)
        relative = encoded_name if not prefix else prefix + b"/" + encoded_name
        entry = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        mode = oct(stat.S_IMODE(entry.st_mode)).encode("ascii")
        if stat.S_ISDIR(entry.st_mode):
            digest_record(digest, b"D", relative, mode)
            child = os.open(
                name,
                directory_flags(),
                dir_fd=directory_descriptor,
            )
            try:
                opened = os.fstat(child)
                if (opened.st_dev, opened.st_ino) != (
                    entry.st_dev,
                    entry.st_ino,
                ):
                    raise RuntimeError(
                        f"runtime directory identity mismatch: {name}"
                    )
                update_runtime_tree_digest(digest, child, relative)
            finally:
                os.close(child)
        elif stat.S_ISREG(entry.st_mode):
            content = stable_regular_sha256_at(
                directory_descriptor,
                name,
                entry,
            )
            digest_record(
                digest,
                b"F",
                relative,
                mode,
                str(entry.st_size).encode("ascii"),
                content,
            )
        elif stat.S_ISLNK(entry.st_mode):
            target = os.fsencode(
                os.readlink(name, dir_fd=directory_descriptor)
            )
            current = os.stat(
                name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            if file_identity(entry) != file_identity(current):
                raise RuntimeError(f"runtime symlink changed while hashing: {name}")
            digest_record(digest, b"L", relative, mode, target)
        else:
            raise RuntimeError(f"unsupported runtime tree entry: {name}")
    after_names = sorted(os.listdir(directory_descriptor), key=os.fsencode)
    after = os.fstat(directory_descriptor)
    if names != after_names or directory_identity(before) != directory_identity(after):
        raise RuntimeError("runtime directory changed while hashing")


def stable_runtime_tree_sha256(root: Path) -> str:
    resolved = root.resolve(strict=True)
    descriptor = os.open(resolved, directory_flags())
    digest = hashlib.sha256()
    digest.update(RUNTIME_TREE_FORMAT)
    try:
        update_runtime_tree_digest(digest, descriptor, b"")
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def write_all(descriptor: int, content: bytes) -> None:
    view = memoryview(content)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise RuntimeError("short write while copying Julia executable")
        view = view[written:]


def release_environment() -> dict[str, str]:
    allowed = {
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "TMPDIR",
        "TZ",
    }
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in allowed
    }
    environment["PATH"] = (
        "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin"
    )
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONHASHSEED"] = "0"
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONSAFEPATH"] = "1"
    environment["JULIA_DEPOT_PATH"] = str(ROOT / ".julia")
    environment["JULIA_LOAD_PATH"] = "@:@stdlib"
    environment["JULIA_HISTORY"] = str(ROOT / "build" / "release-history.jl")
    environment["JULIA_NUM_THREADS"] = "auto"
    environment["JULIA_PKG_OFFLINE"] = "true"
    environment["JULIA_PKG_PRECOMPILE_AUTO"] = "0"
    environment["OPENBLAS_NUM_THREADS"] = "1"
    return environment


def python_command(*arguments: str) -> list[str]:
    return [sys.executable, "-I", "-E", "-s", *arguments]


def git_environment(
    environment: dict[str, str],
) -> dict[str, str]:
    output = {
        key: value
        for key, value in environment.items()
        if not key.startswith("GIT_")
    }
    output["GIT_CONFIG_NOSYSTEM"] = "1"
    output["GIT_CONFIG_GLOBAL"] = "/dev/null"
    output["GIT_NO_REPLACE_OBJECTS"] = "1"
    return output


def expected_commit_file(
    commit: str,
    path: str,
    environment: dict[str, str],
) -> bytes:
    if SHA1.fullmatch(commit) is None:
        raise RuntimeError("expected release commit is malformed")
    if not GIT_EXECUTABLE.is_file():
        raise RuntimeError(f"required executable was not found: {GIT_EXECUTABLE}")
    result = subprocess.run(
        [
            str(GIT_EXECUTABLE),
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "-c",
            "core.useReplaceRefs=false",
            "show",
            f"{commit}:{path}",
        ],
        cwd=ROOT,
        env=git_environment(environment),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def run_commit_manifest_check(
    commit: str,
    environment: dict[str, str],
) -> None:
    script = expected_commit_file(
        commit,
        "tools/release_manifest.py",
        environment,
    )
    subprocess.run(
        python_command(
            "-",
            "--repository-root",
            str(ROOT),
            "--check",
            "--require-clean",
            "--expected-commit",
            commit,
        ),
        cwd=ROOT,
        env=environment,
        input=script,
        check=True,
    )


def worktree_manifest_check_command() -> list[str]:
    return python_command(
        "tools/release_manifest.py",
        "--check",
    )


def julia_command(julia: Path, script: str) -> list[str]:
    return [
        str(julia),
        "--startup-file=no",
        "--history-file=no",
        "--compiled-modules=no",
        "--project=.",
        script,
    ]


def repository_check_commands(julia: Path) -> list[list[str]]:
    if not MAKE_EXECUTABLE.is_file():
        raise RuntimeError(f"required executable was not found: {MAKE_EXECUTABLE}")
    return [
        julia_command(julia, "scripts/verify_dependency_integrity.jl"),
        julia_command(julia, "test/runtests.jl"),
        [
            *python_command(),
            "-m",
            "unittest",
            "discover",
            "-s",
            "test",
            "-p",
            "test_*.py",
            "-v",
        ],
        [
            *python_command(),
            "-m",
            "unittest",
            "discover",
            "-s",
            "verifier/tests",
            "-v",
        ],
        julia_command(julia, "test/write_compact_witness_fixture.jl"),
        python_command("test/check_compact_witness_roundtrip.py"),
        [
            str(MAKE_EXECUTABLE),
            "-C",
            "verifier/cpp",
            "clean",
            "test",
            "test-external",
        ],
        julia_command(julia, "scripts/certify_samples.jl"),
        julia_command(julia, "scripts/certify_structure.jl"),
        julia_command(julia, "scripts/certify_residual_space.jl"),
        julia_command(julia, "scripts/certify_cross_language_formulation.jl"),
        python_command("test/check_cross_language_formulation.py"),
        julia_command(julia, "scripts/audit_explicit_schema.jl"),
        julia_command(julia, "scripts/smoke_solve.jl"),
        julia_command(julia, "scripts/smoke_exact_rounding.jl"),
        python_command("test/check_smoke_compact_witness.py"),
        julia_command(julia, "scripts/verify_dependency_integrity.jl"),
        worktree_manifest_check_command(),
    ]


def certificate_check_command(anchors: ReleaseAnchors) -> list[str]:
    return python_command(
        "tools/run_with_limits.py",
        "--wall-seconds",
        "7200",
        "--rss-gib",
        "16",
        "--log",
        "logs/degree17-release-verification.log",
        "--",
        *python_command(),
        "verifier/verify_compact_package.py",
        "certificates/kn11-degree17-certificate-v2.json",
        "--release",
        "--expected-manifest-sha256",
        anchors.manifest,
        "--expected-witness-sha256",
        anchors.witness,
        "--expected-source-specification",
        anchors.source_specification,
        "--expected-rounding-specification",
        anchors.rounding_specification,
        "--expected-verification-specification",
        anchors.verification_specification,
    )


def stable_sha256(path: Path) -> str:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    digest = hashlib.sha256()
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError(f"release path is not a regular file: {path}")
        remaining = before.st_size
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            if not block:
                raise RuntimeError(f"release path changed while reading: {path}")
            digest.update(block)
            remaining -= len(block)
        if os.read(descriptor, 1):
            raise RuntimeError(f"release path changed while reading: {path}")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if identity_before != identity_after:
        raise RuntimeError(f"release path changed while reading: {path}")
    return digest.hexdigest()


def verify_certificate_files(anchors: ReleaseAnchors) -> None:
    manifest = ROOT / "certificates" / "kn11-degree17-certificate-v2.json"
    witness = ROOT / "certificates" / "kn11-degree17-witness-v2.bin"
    if stable_sha256(manifest) != anchors.manifest:
        raise RuntimeError("certificate manifest no longer matches its trust anchor")
    if stable_sha256(witness) != anchors.witness:
        raise RuntimeError("certificate witness no longer matches its trust anchor")


@contextmanager
def verified_julia(
    value: str,
    expected_sha256: str,
    expected_tree_sha256: str,
    environment: dict[str, str],
) -> Iterator[Path]:
    if SHA256.fullmatch(expected_sha256) is None:
        raise RuntimeError("expected Julia SHA-256 is missing or malformed")
    if SHA256.fullmatch(expected_tree_sha256) is None:
        raise RuntimeError(
            "expected Julia runtime-tree SHA-256 is missing or malformed"
        )
    source = resolve_executable(value)
    if source.parent.name != "bin":
        raise RuntimeError("Julia executable is not inside a bin directory")
    runtime_root = source.parent.parent.resolve(strict=True)
    if stable_runtime_tree_sha256(runtime_root) != expected_tree_sha256:
        raise RuntimeError("Julia runtime tree does not match its trust anchor")

    build = ROOT / "build"
    build.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".kn11-julia-launch-",
        dir=build,
    ) as temporary:
        launcher_root = Path(temporary)
        launcher_bin = launcher_root / "bin"
        launcher_bin.mkdir(mode=0o700)
        launcher = launcher_bin / "julia"

        source_descriptor = os.open(source, regular_read_flags())
        target_descriptor = os.open(
            launcher,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o500,
        )
        digest = hashlib.sha256()
        try:
            before = os.fstat(source_descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise RuntimeError("Julia executable is not a regular file")
            while True:
                block = os.read(source_descriptor, 1024 * 1024)
                if not block:
                    break
                digest.update(block)
                write_all(target_descriptor, block)
            after = os.fstat(source_descriptor)
            if file_identity(before) != file_identity(after):
                raise RuntimeError("Julia executable changed while copying")
            if digest.hexdigest() != expected_sha256:
                raise RuntimeError(
                    "Julia executable does not match its trust anchor"
                )
            os.fsync(target_descriptor)
            os.fchmod(target_descriptor, 0o555)
        finally:
            os.close(target_descriptor)
            os.close(source_descriptor)

        for entry in runtime_root.iterdir():
            if entry.name == "bin":
                continue
            (launcher_root / entry.name).symlink_to(
                entry,
                target_is_directory=entry.is_dir(),
            )
        for entry in source.parent.iterdir():
            if entry.name == source.name:
                continue
            (launcher_bin / entry.name).symlink_to(
                entry,
                target_is_directory=entry.is_dir(),
            )

        result = subprocess.run(
            [
                str(launcher),
                "--startup-file=no",
                "--history-file=no",
                "-e",
                "print(VERSION)",
            ],
            cwd=ROOT,
            env=environment,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.stdout != EXPECTED_JULIA_VERSION:
            raise RuntimeError(
                "Julia version mismatch: "
                f"expected {EXPECTED_JULIA_VERSION}, got {result.stdout!r}"
            )
        yield launcher


def run_checked(command: list[str], environment: dict[str, str]) -> None:
    subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        check=True,
    )


def run_certificate_check(
    anchors: ReleaseAnchors,
    environment: dict[str, str],
) -> None:
    verify_certificate_files(anchors)
    run_checked(certificate_check_command(anchors), environment)
    verify_certificate_files(anchors)


def run_full_release_check(
    anchors: ReleaseAnchors,
    environment: dict[str, str],
) -> None:
    if anchors.commit is None:
        raise RuntimeError("full release check requires the expected commit")
    if anchors.julia is None:
        raise RuntimeError("full release check requires the Julia trust anchor")
    if anchors.julia_tree is None:
        raise RuntimeError(
            "full release check requires the Julia runtime-tree trust anchor"
        )
    with verified_julia(
        os.environ.get("JULIA", "julia"),
        anchors.julia,
        anchors.julia_tree,
        environment,
    ) as julia:
        run_commit_manifest_check(anchors.commit, environment)
        for command in repository_check_commands(julia):
            run_checked(command, environment)
        run_certificate_check(anchors, environment)
        run_commit_manifest_check(anchors.commit, environment)
        verify_certificate_files(anchors)


def require_isolated_interpreter() -> None:
    if not (
        sys.flags.isolated
        and sys.flags.ignore_environment
        and sys.flags.no_user_site
    ):
        raise RuntimeError(
            "release check requires Python flags -I -E -s"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--certificate-only", action="store_true")
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=ROOT,
    )
    arguments = parser.parse_args()
    try:
        require_isolated_interpreter()
        configure_root(arguments.repository_root)
        anchors = load_anchors(
            require_commit=not arguments.certificate_only,
            require_julia=not arguments.certificate_only,
        )
        environment = release_environment()
        if arguments.certificate_only:
            run_certificate_check(anchors, environment)
        else:
            run_full_release_check(anchors, environment)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"release check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
