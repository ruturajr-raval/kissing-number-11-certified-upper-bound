#!/usr/bin/env python3
"""Export a certificate from descriptor-anchored read-only source copies."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Iterator
import zipfile


ROOT = Path(__file__).resolve().parents[1]
MAX_BOUND_FILE_BYTES = 64 * 1024 * 1024
MAX_EXACT_INPUT_BYTES = 16 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_WITNESS_BYTES = 128 * 1024 * 1024
MAX_COMPRESSED_PACKAGE_BYTES = 45 * 1024 * 1024
EXACT_INPUT_PATH = "build/degree17-exact-86899-over-100.jls"
MANIFEST_FILENAME = "kn11-degree17-certificate-v2.json"
WITNESS_FILENAME = "kn11-degree17-witness-v2.bin"
EXPECTED_JULIA_VERSION = "1.12.7"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
RUNTIME_TREE_FORMAT = b"KN11-RUNTIME-TREE-V1\0"

EVIDENCE_PATHS = (
    "evidence/canonical-samples.json",
    "evidence/cross-language-formulation.json",
    "evidence/explicit-schema-audit.json",
    "evidence/problem-structure.json",
    "evidence/residual-space.json",
    "evidence/sample-unisolvence.json",
)

SOURCE_PATHS = (
    "Manifest.toml",
    "Project.toml",
    "docs/THEOREM_BRIDGE.md",
    "scripts/certify_cross_language_formulation.jl",
    "scripts/export_compact_certificate.jl",
    "scripts/export_compact_certificate_bootstrap.jl",
    "scripts/round_exact_solution.jl",
    "scripts/solve_fixed_objective.jl",
    "scripts/verify_dependency_integrity.jl",
    "scripts/verify_projection_checkpoint.jl",
    "src/CheckpointRecovery.jl",
    "src/CompactWitness.jl",
    "src/KissingNumber11Certificate.jl",
    "src/ParallelExactVerification.jl",
    "src/PortableExactSolution.jl",
    "src/StrictInteriorVerification.jl",
    "test/check_cross_language_formulation.py",
    "tools/export_compact_certificate.py",
    "tools/release_check.py",
    "tools/release_manifest.py",
    "tools/run_with_limits.py",
    "verifier/compact_certificate.py",
    "verifier/compact_witness.py",
    "verifier/cpp/compact_witness.cpp",
    "verifier/cpp/compact_witness.hpp",
    "verifier/formulation.py",
    "verifier/package_manifest.py",
    "verifier/verify_compact_certificate.py",
    "verifier/verify_compact_package.py",
)


def validate_relative_path(token: str) -> tuple[str, ...]:
    relative = PurePosixPath(token)
    if (
        relative.is_absolute()
        or token != relative.as_posix()
        or any(part in ("", ".", "..") for part in relative.parts)
    ):
        raise RuntimeError(f"unsafe bound path: {token}")
    return relative.parts


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


def open_or_create_directory(
    parent_descriptor: int,
    name: str,
    mode: int,
) -> int:
    if "/" in name or name in ("", ".", ".."):
        raise RuntimeError(f"unsafe directory name: {name}")
    try:
        return os.open(name, directory_flags(), dir_fd=parent_descriptor)
    except FileNotFoundError:
        try:
            os.mkdir(name, mode=mode, dir_fd=parent_descriptor)
        except FileExistsError:
            pass
        return os.open(name, directory_flags(), dir_fd=parent_descriptor)


def open_at(root_descriptor: int, token: str, flags: int) -> int:
    parts = validate_relative_path(token)
    parent = os.dup(root_descriptor)
    try:
        for component in parts[:-1]:
            child = os.open(
                component,
                directory_flags(),
                dir_fd=parent,
            )
            os.close(parent)
            parent = child
        return os.open(parts[-1], flags, dir_fd=parent)
    finally:
        os.close(parent)


def open_parent_at(
    root_descriptor: int,
    token: str,
    *,
    create: bool,
) -> tuple[int, str]:
    parts = validate_relative_path(token)
    parent = os.dup(root_descriptor)
    try:
        for component in parts[:-1]:
            child = (
                open_or_create_directory(parent, component, 0o700)
                if create
                else os.open(component, directory_flags(), dir_fd=parent)
            )
            os.close(parent)
            parent = child
        return parent, parts[-1]
    except BaseException:
        os.close(parent)
        raise


def stable_bytes_at(
    root_descriptor: int,
    token: str,
    maximum_bytes: int,
) -> bytes:
    try:
        descriptor = open_at(root_descriptor, token, regular_read_flags())
    except OSError as exc:
        raise RuntimeError(f"cannot open bound path {token}: {exc}") from exc
    chunks: list[bytes] = []
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError(f"bound path is not a regular file: {token}")
        if before.st_size > maximum_bytes:
            raise RuntimeError(f"bound path exceeds size limit: {token}")
        remaining = before.st_size
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            if not block:
                raise RuntimeError(f"bound path changed while reading: {token}")
            chunks.append(block)
            remaining -= len(block)
        if os.read(descriptor, 1):
            raise RuntimeError(f"bound path changed while reading: {token}")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if file_identity(before) != file_identity(after):
        raise RuntimeError(f"bound path changed while reading: {token}")
    return b"".join(chunks)


def write_all(descriptor: int, content: bytes) -> None:
    view = memoryview(content)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise RuntimeError("short write while creating export artifact")
        view = view[written:]


def write_snapshot_file_at(
    snapshot_descriptor: int,
    token: str,
    content: bytes,
) -> None:
    parent, name = open_parent_at(
        snapshot_descriptor,
        token,
        create=True,
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(name, flags, 0o400, dir_fd=parent)
        write_all(descriptor, content)
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o444)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent)


def copy_bound_files(
    root_descriptor: int,
    snapshot_descriptor: int,
) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for token in (*SOURCE_PATHS, *EVIDENCE_PATHS):
        content = stable_bytes_at(
            root_descriptor,
            token,
            MAX_BOUND_FILE_BYTES,
        )
        write_snapshot_file_at(snapshot_descriptor, token, content)
        hashes[token] = hashlib.sha256(content).hexdigest()
    return hashes


def copy_exact_input(
    root_descriptor: int,
    snapshot_descriptor: int,
) -> str | None:
    try:
        source = open_at(
            root_descriptor,
            EXACT_INPUT_PATH,
            regular_read_flags(),
        )
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RuntimeError(
            f"cannot open exact-solution input {EXACT_INPUT_PATH}: {exc}"
        ) from exc

    parent = -1
    target = -1
    name = ""
    completed = False
    digest = hashlib.sha256()
    try:
        parent, name = open_parent_at(
            snapshot_descriptor,
            EXACT_INPUT_PATH,
            create=True,
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        target = os.open(name, flags, 0o400, dir_fd=parent)
        before = os.fstat(source)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError("exact-solution input is not a regular file")
        if before.st_size > MAX_EXACT_INPUT_BYTES:
            raise RuntimeError("exact-solution input exceeds the size limit")
        remaining = before.st_size
        while remaining:
            block = os.read(source, min(8 * 1024 * 1024, remaining))
            if not block:
                raise RuntimeError("exact-solution input changed while copying")
            digest.update(block)
            write_all(target, block)
            remaining -= len(block)
        if os.read(source, 1):
            raise RuntimeError("exact-solution input changed while copying")
        after = os.fstat(source)
        if file_identity(before) != file_identity(after):
            raise RuntimeError("exact-solution input changed while copying")
        os.fsync(target)
        os.fchmod(target, 0o444)
        completed = True
    finally:
        if target >= 0:
            os.close(target)
        os.close(source)
        if parent >= 0:
            if not completed and name:
                try:
                    os.unlink(name, dir_fd=parent)
                except FileNotFoundError:
                    pass
            os.close(parent)
    return digest.hexdigest()


def preflight_binding(hashes: dict[str, str]) -> str:
    lines = [
        *(f"source:{path}={hashes[path]}" for path in SOURCE_PATHS),
        *(f"evidence:{path}={hashes[path]}" for path in EVIDENCE_PATHS),
    ]
    return hashlib.sha256(("\n".join(lines) + "\n").encode("ascii")).hexdigest()


def clear_directory(descriptor: int) -> None:
    for name in os.listdir(descriptor):
        try:
            entry = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(entry.st_mode):
            try:
                os.unlink(name, dir_fd=descriptor)
            except FileNotFoundError:
                pass
            continue

        try:
            child = os.open(name, directory_flags(), dir_fd=descriptor)
        except FileNotFoundError:
            continue
        try:
            opened = os.fstat(child)
            current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if (
                current.st_dev,
                current.st_ino,
            ) != (
                opened.st_dev,
                opened.st_ino,
            ):
                raise RuntimeError("snapshot entry changed during cleanup")
            clear_directory(child)
        finally:
            os.close(child)
        try:
            current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            continue
        if (
            current.st_dev,
            current.st_ino,
        ) != (
            opened.st_dev,
            opened.st_ino,
        ):
            raise RuntimeError("snapshot directory changed during cleanup")
        os.rmdir(name, dir_fd=descriptor)


def make_directories_writable(descriptor: int) -> None:
    os.fchmod(descriptor, 0o700)
    for name in os.listdir(descriptor):
        try:
            entry = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(entry.st_mode):
            continue
        child = os.open(name, directory_flags(), dir_fd=descriptor)
        try:
            make_directories_writable(child)
        finally:
            os.close(child)


@contextmanager
def private_snapshot() -> Iterator[tuple[int, int]]:
    root_descriptor = -1
    build_descriptor = -1
    snapshot_descriptor = -1
    snapshot_identity: tuple[int, int] | None = None
    name = ""
    try:
        root_descriptor = os.open(ROOT, directory_flags())
        build_descriptor = open_or_create_directory(
            root_descriptor,
            "build",
            0o700,
        )
        for _ in range(32):
            candidate = f".kn11-export-{secrets.token_hex(12)}"
            try:
                os.mkdir(candidate, mode=0o700, dir_fd=build_descriptor)
            except FileExistsError:
                continue
            name = candidate
            break
        if not name:
            raise RuntimeError("could not allocate a private export snapshot")
        snapshot_descriptor = os.open(
            name,
            directory_flags(),
            dir_fd=build_descriptor,
        )
        opened = os.fstat(snapshot_descriptor)
        current = os.stat(
            name,
            dir_fd=build_descriptor,
            follow_symlinks=False,
        )
        snapshot_identity = (opened.st_dev, opened.st_ino)
        if (
            not stat.S_ISDIR(current.st_mode)
            or (current.st_dev, current.st_ino) != snapshot_identity
        ):
            raise RuntimeError("private export snapshot identity mismatch")
        yield root_descriptor, snapshot_descriptor
    finally:
        cleanup_error: BaseException | None = None
        try:
            if snapshot_descriptor >= 0:
                try:
                    make_directories_writable(snapshot_descriptor)
                    clear_directory(snapshot_descriptor)
                except BaseException as exc:
                    cleanup_error = exc
                finally:
                    os.close(snapshot_descriptor)
            if name and snapshot_identity is not None:
                try:
                    current = os.stat(
                        name,
                        dir_fd=build_descriptor,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    current = None
                if (
                    current is not None
                    and stat.S_ISDIR(current.st_mode)
                    and (current.st_dev, current.st_ino) == snapshot_identity
                ):
                    os.rmdir(name, dir_fd=build_descriptor)
        finally:
            if build_descriptor >= 0:
                os.close(build_descriptor)
            if root_descriptor >= 0:
                os.close(root_descriptor)
        if cleanup_error is not None:
            raise cleanup_error


def julia_environment(root_descriptor: int) -> dict[str, str]:
    depot = os.open(".julia", directory_flags(), dir_fd=root_descriptor)
    os.close(depot)
    threads = os.environ.get("JULIA_NUM_THREADS", "1")
    if re.fullmatch(r"(?:auto|[1-9][0-9]*(?:,[1-9][0-9]*)?)", threads) is None:
        threads = "1"
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
    environment["JULIA_DEPOT_PATH"] = str(ROOT / ".julia")
    environment["JULIA_LOAD_PATH"] = "@:@stdlib"
    environment["JULIA_NUM_THREADS"] = threads
    environment["JULIA_PKG_OFFLINE"] = "true"
    environment["JULIA_PKG_PRECOMPILE_AUTO"] = "0"
    environment["OPENBLAS_NUM_THREADS"] = "1"
    return environment


def resolve_executable(value: str, environment: dict[str, str]) -> str:
    candidate = Path(value)
    if not candidate.is_absolute():
        located = shutil.which(value, path=environment.get("PATH"))
        if located is None:
            raise RuntimeError(f"Julia executable was not found: {value}")
        candidate = Path(located)
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise RuntimeError(f"Julia executable is not runnable: {resolved}")
    return str(resolved)


@contextmanager
def verified_julia_executable(
    value: str,
    expected_sha256: str,
    expected_tree_sha256: str,
    environment: dict[str, str],
) -> Iterator[str]:
    if SHA256_PATTERN.fullmatch(expected_sha256) is None:
        raise RuntimeError("expected Julia SHA-256 is missing or malformed")
    if SHA256_PATTERN.fullmatch(expected_tree_sha256) is None:
        raise RuntimeError(
            "expected Julia runtime-tree SHA-256 is missing or malformed"
        )
    source = Path(resolve_executable(value, environment))
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
        yield str(launcher)


def anchored_command(
    snapshot_descriptor: int,
    command: list[str],
) -> list[str]:
    launcher = (
        "import os,sys; "
        "fd=int(sys.argv[1]); "
        "os.fchdir(fd); "
        "os.set_inheritable(fd,False); "
        "os.execve(sys.argv[2],sys.argv[2:],os.environ)"
    )
    return [
        sys.executable,
        "-I",
        "-S",
        "-c",
        launcher,
        str(snapshot_descriptor),
        *command,
    ]


def seal_snapshot(snapshot_descriptor: int) -> None:
    for name in os.listdir(snapshot_descriptor):
        entry = os.stat(
            name,
            dir_fd=snapshot_descriptor,
            follow_symlinks=False,
        )
        if not stat.S_ISDIR(entry.st_mode):
            continue
        child = os.open(name, directory_flags(), dir_fd=snapshot_descriptor)
        try:
            if name in {"certificates", "verification"}:
                os.fchmod(child, 0o700)
            else:
                seal_snapshot(child)
                os.fchmod(child, 0o500)
        finally:
            os.close(child)
    os.fchmod(snapshot_descriptor, 0o500)


def stage_output(
    directory_descriptor: int,
    final_name: str,
    content: bytes,
) -> str:
    temporary = f".{final_name}.{secrets.token_hex(12)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    completed = False
    try:
        descriptor = os.open(
            temporary,
            flags,
            0o644,
            dir_fd=directory_descriptor,
        )
        write_all(descriptor, content)
        os.fsync(descriptor)
        completed = True
        return temporary
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if not completed:
            try:
                os.unlink(temporary, dir_fd=directory_descriptor)
            except FileNotFoundError:
                pass


@contextmanager
def certificate_publication_lock(
    directory_descriptor: int,
) -> Iterator[None]:
    name = ".kn11-certificate-publication.lock"
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(
        name,
        flags,
        0o600,
        dir_fd=directory_descriptor,
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("certificate publication lock is not regular")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def validate_publish_target(
    directory_descriptor: int,
    name: str,
) -> None:
    try:
        current = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    if not (stat.S_ISREG(current.st_mode) or stat.S_ISLNK(current.st_mode)):
        raise RuntimeError(f"refusing to replace non-file certificate path: {name}")


def validate_generated_pair(witness: bytes, manifest: bytes) -> None:
    if not manifest.endswith(b"\n"):
        raise RuntimeError("generated certificate manifest lacks a final LF")
    try:
        document = json.loads(manifest.decode("ascii"))
        witness_record = document["witness"]
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError("generated certificate manifest is malformed") from exc
    if witness_record.get("filename") != WITNESS_FILENAME:
        raise RuntimeError("generated manifest names the wrong witness")
    if witness_record.get("size_bytes") != len(witness):
        raise RuntimeError("generated manifest records the wrong witness size")
    if witness_record.get("sha256") != hashlib.sha256(witness).hexdigest():
        raise RuntimeError("generated manifest records the wrong witness hash")


def compressed_package_metadata(
    witness: bytes,
    manifest: bytes,
) -> tuple[int, str]:
    """Measure a deterministic compressed certificate package."""

    validate_generated_pair(witness, manifest)
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        for filename, content in (
            (WITNESS_FILENAME, witness),
            (MANIFEST_FILENAME, manifest),
        ):
            info = zipfile.ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(
                info,
                content,
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )
    content = buffer.getvalue()
    if len(content) > MAX_COMPRESSED_PACKAGE_BYTES:
        raise RuntimeError(
            "compressed certificate package exceeds the 45 MiB acceptance limit"
        )
    return len(content), hashlib.sha256(content).hexdigest()


def capture_generated_pair(
    snapshot_descriptor: int,
) -> tuple[bytes, bytes]:
    witness = stable_bytes_at(
        snapshot_descriptor,
        f"certificates/{WITNESS_FILENAME}",
        MAX_WITNESS_BYTES,
    )
    manifest = stable_bytes_at(
        snapshot_descriptor,
        f"certificates/{MANIFEST_FILENAME}",
        MAX_MANIFEST_BYTES,
    )
    validate_generated_pair(witness, manifest)
    return witness, manifest


def publish_outputs(
    root_descriptor: int,
    witness: bytes,
    manifest: bytes,
) -> None:
    validate_generated_pair(witness, manifest)
    certificates = open_or_create_directory(
        root_descriptor,
        "certificates",
        0o755,
    )
    try:
        with certificate_publication_lock(certificates):
            staged: list[str] = []
            try:
                validate_publish_target(certificates, WITNESS_FILENAME)
                validate_publish_target(certificates, MANIFEST_FILENAME)
                staged_witness = stage_output(
                    certificates,
                    WITNESS_FILENAME,
                    witness,
                )
                staged.append(staged_witness)
                staged_manifest = stage_output(
                    certificates,
                    MANIFEST_FILENAME,
                    manifest,
                )
                staged.append(staged_manifest)
                os.replace(
                    staged_witness,
                    WITNESS_FILENAME,
                    src_dir_fd=certificates,
                    dst_dir_fd=certificates,
                )
                staged.remove(staged_witness)
                os.fsync(certificates)
                os.replace(
                    staged_manifest,
                    MANIFEST_FILENAME,
                    src_dir_fd=certificates,
                    dst_dir_fd=certificates,
                )
                staged.remove(staged_manifest)
                os.fsync(certificates)
            finally:
                for name in staged:
                    try:
                        os.unlink(name, dir_fd=certificates)
                    except FileNotFoundError:
                        pass
    finally:
        os.close(certificates)

    print(f"published_witness=certificates/{WITNESS_FILENAME}")
    print(f"published_witness_sha256={hashlib.sha256(witness).hexdigest()}")
    print(f"published_witness_bytes={len(witness)}")
    print(f"published_manifest=certificates/{MANIFEST_FILENAME}")
    print(f"published_manifest_sha256={hashlib.sha256(manifest).hexdigest()}")


def require_isolated_interpreter() -> None:
    if not (
        sys.flags.isolated
        and sys.flags.ignore_environment
        and sys.flags.no_user_site
    ):
        raise RuntimeError(
            "certificate export requires Python flags -I -E -s"
        )


def verification_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {
            "HOME",
            "LANG",
            "LC_ALL",
            "LC_CTYPE",
            "TERM",
            "TMPDIR",
            "TZ",
        }
    }
    environment["PATH"] = (
        "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin"
    )
    return environment


def verify_snapshot_package(
    snapshot_descriptor: int,
    witness: bytes,
    manifest: bytes,
) -> tuple[int, str]:
    validate_generated_pair(witness, manifest)
    compressed_metadata = compressed_package_metadata(witness, manifest)
    write_snapshot_file_at(
        snapshot_descriptor,
        f"verification/{WITNESS_FILENAME}",
        witness,
    )
    write_snapshot_file_at(
        snapshot_descriptor,
        f"verification/{MANIFEST_FILENAME}",
        manifest,
    )
    verification = os.open(
        "verification",
        directory_flags(),
        dir_fd=snapshot_descriptor,
    )
    try:
        os.fchmod(verification, 0o500)
    finally:
        os.close(verification)
    bootstrap = (
        "import runpy,sys;"
        "sys.path.insert(0,'verifier');"
        "sys.argv=['verifier/verify_compact_package.py',"
        f"'verification/{MANIFEST_FILENAME}','--project-root','.'];"
        "runpy.run_path('verifier/verify_compact_package.py',run_name='__main__')"
    )
    command = [
        sys.executable,
        "-I",
        "-S",
        "-B",
        "-c",
        bootstrap,
    ]
    subprocess.run(
        anchored_command(snapshot_descriptor, command),
        env=verification_environment(),
        pass_fds=(snapshot_descriptor,),
        check=True,
    )
    return compressed_metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--julia", default=os.environ.get("JULIA", "julia"))
    parser.add_argument(
        "--expected-julia-sha256",
        default=os.environ.get("KN11_EXPECTED_JULIA_SHA256", ""),
    )
    parser.add_argument(
        "--expected-julia-tree-sha256",
        default=os.environ.get("KN11_EXPECTED_JULIA_TREE_SHA256", ""),
    )
    parser.add_argument(
        "--expected-exact-input-sha256",
        default=os.environ.get("KN11_EXPECTED_EXACT_INPUT_SHA256", ""),
    )
    args = parser.parse_args()
    require_isolated_interpreter()
    with private_snapshot() as (root_descriptor, snapshot_descriptor):
        hashes = copy_bound_files(root_descriptor, snapshot_descriptor)
        exact_input_sha256 = copy_exact_input(
            root_descriptor,
            snapshot_descriptor,
        )
        if exact_input_sha256 is not None:
            if (
                SHA256_PATTERN.fullmatch(args.expected_exact_input_sha256)
                is None
            ):
                raise RuntimeError(
                    "expected exact-input SHA-256 is missing or malformed"
                )
            if exact_input_sha256 != args.expected_exact_input_sha256:
                raise RuntimeError(
                    "exact-solution input does not match its trust anchor"
                )
        for name in ("certificates", "verification"):
            directory = open_or_create_directory(
                snapshot_descriptor,
                name,
                0o700,
            )
            os.close(directory)
        environment = julia_environment(root_descriptor)
        environment["KN11_EXPORT_PREFLIGHT_SHA256"] = preflight_binding(hashes)
        if exact_input_sha256 is not None:
            environment["KN11_EXPECTED_EXACT_INPUT_SHA256"] = (
                exact_input_sha256
            )
        with verified_julia_executable(
            args.julia,
            args.expected_julia_sha256,
            args.expected_julia_tree_sha256,
            environment,
        ) as julia:
            seal_snapshot(snapshot_descriptor)
            julia_process = [
                julia,
                "--startup-file=no",
                "--history-file=no",
                "--compiled-modules=no",
                "--project=.",
                "scripts/export_compact_certificate_bootstrap.jl",
            ]
            result = subprocess.run(
                anchored_command(snapshot_descriptor, julia_process),
                env=environment,
                pass_fds=(snapshot_descriptor,),
            )
            if result.returncode != 0:
                return result.returncode
            witness, manifest = capture_generated_pair(snapshot_descriptor)
            compressed_size, compressed_sha256 = verify_snapshot_package(
                snapshot_descriptor,
                witness,
                manifest,
            )
            publish_outputs(root_descriptor, witness, manifest)
            print(f"compressed_package_bytes={compressed_size}")
            print(f"compressed_package_sha256={compressed_sha256}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
