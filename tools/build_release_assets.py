#!/usr/bin/env python3
"""Build and verify release assets against an immutable Git tree."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT / "dist" / "release"
PROJECT = "kissing-number-11-certified-upper-bound"
CERTIFICATE_MANIFEST = "certificates/kn11-degree17-certificate-v2.json"
VERSION_RE = re.compile(r"^version:\s*[\"']?([^\"' \n]+)", re.MULTILINE)
CHECKSUM_RE = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9_.-]+)$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SUPPORTING_CERTIFICATE_PATHS = (
    "CITATION.cff",
    "LICENSE",
    "README.md",
    "THIRD_PARTY_NOTICES.md",
    "docs/CERTIFICATE_FORMAT.md",
    "docs/REPRODUCIBILITY.md",
    "release-manifest.sha256",
    "verifier/README.md",
    "verifier/SCHEMA.md",
)


@dataclass(frozen=True)
class TreeEntry:
    path: str
    mode: int
    object_id: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_output(arguments: list[str]) -> bytes:
    return subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def resolve_ref(reference: str) -> str:
    commit = git_output(
        ["rev-parse", "--verify", f"{reference}^{{commit}}"]
    ).decode("ascii").strip()
    if COMMIT_RE.fullmatch(commit) is None:
        raise ValueError(f"Git reference did not resolve to a commit: {reference}")
    return commit


def tree_entries(reference: str) -> list[TreeEntry]:
    commit = resolve_ref(reference)
    entries: list[TreeEntry] = []
    for record in git_output(["ls-tree", "-r", "-z", commit]).split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode_text, object_type, object_id = metadata.decode("ascii").split()
        path = os.fsdecode(raw_path)
        if (
            object_type != "blob"
            or mode_text not in {"100644", "100755"}
            or Path(path).is_absolute()
            or ".." in Path(path).parts
        ):
            raise ValueError(f"unsupported Git tree entry: {path}")
        entries.append(
            TreeEntry(
                path=path,
                mode=0o755 if mode_text == "100755" else 0o644,
                object_id=object_id,
            )
        )
    return sorted(entries, key=lambda entry: entry.path)


def entry_map(reference: str) -> dict[str, TreeEntry]:
    return {entry.path: entry for entry in tree_entries(reference)}


def blob_bytes(object_id: str) -> bytes:
    return git_output(["cat-file", "blob", object_id])


def bytes_at_ref(reference: str, relative: str) -> bytes:
    entry = entry_map(reference).get(relative)
    if entry is None:
        raise ValueError(f"{relative} is absent from Git reference {reference}")
    return blob_bytes(entry.object_id)


def text_at_ref(reference: str, relative: str) -> str:
    return bytes_at_ref(reference, relative).decode("utf-8")


def project_version(reference: str = "HEAD") -> str:
    match = VERSION_RE.search(text_at_ref(reference, "CITATION.cff"))
    if match is None:
        raise ValueError("CITATION.cff has no version")
    return match.group(1).removeprefix("v")


def validate_tag(reference: str, tag: str, version: str) -> str:
    if tag != f"v{version}":
        raise ValueError(f"release tag {tag!r} does not match version {version}")
    commit = resolve_ref(reference)
    tag_commit = resolve_ref(f"refs/tags/{tag}")
    if tag_commit != commit:
        raise ValueError(
            f"release tag {tag} resolves to {tag_commit}, expected {commit}"
        )
    return commit


def normalized_tar_info(data: bytes, mode: int, name: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = mode
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    return info


def build_archive(
    output: Path,
    prefix: str,
    entries: list[TreeEntry],
) -> None:
    with output.open("wb") as raw_stream:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw_stream,
            compresslevel=9,
            mtime=0,
        ) as gzip_stream:
            with tarfile.open(
                fileobj=gzip_stream,
                mode="w",
                format=tarfile.USTAR_FORMAT,
            ) as archive:
                for entry in entries:
                    data = blob_bytes(entry.object_id)
                    archive.addfile(
                        normalized_tar_info(
                            data,
                            entry.mode,
                            f"{prefix}/{entry.path}",
                        ),
                        io.BytesIO(data),
                    )


def build_source_archive(
    output: Path,
    version: str,
    reference: str,
) -> None:
    build_archive(
        output,
        f"{PROJECT}-v{version}",
        tree_entries(reference),
    )


def _safe_manifest_path(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise ValueError(f"{field} is unsafe")
    return value


def _manifest_bound_paths(
    manifest: dict[str, object],
    field: str,
) -> dict[str, str]:
    raw_entries = manifest.get(field)
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError(f"certificate manifest has no {field}")
    result: dict[str, str] = {}
    for index, raw_entry in enumerate(raw_entries):
        if not isinstance(raw_entry, dict):
            raise ValueError(f"certificate manifest {field}[{index}] is invalid")
        path = _safe_manifest_path(
            raw_entry.get("path"),
            f"{field}[{index}].path",
        )
        digest = raw_entry.get("sha256")
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            raise ValueError(f"certificate manifest {field}[{index}] hash is invalid")
        if path in result:
            raise ValueError(f"duplicate certificate manifest path: {path}")
        result[path] = digest
    return result


def certificate_manifest(reference: str) -> dict[str, object]:
    value = json.loads(text_at_ref(reference, CERTIFICATE_MANIFEST))
    if not isinstance(value, dict):
        raise ValueError("certificate manifest must be a JSON object")
    return value


def certificate_file_paths(reference: str) -> list[str]:
    entries = entry_map(reference)
    manifest = certificate_manifest(reference)
    paths = {CERTIFICATE_MANIFEST, *SUPPORTING_CERTIFICATE_PATHS}
    bound = {
        **_manifest_bound_paths(manifest, "sources"),
        **_manifest_bound_paths(manifest, "evidence"),
    }
    for path, expected_digest in bound.items():
        entry = entries.get(path)
        if entry is None:
            raise ValueError(f"manifest-bound file is absent from Git: {path}")
        observed = hashlib.sha256(blob_bytes(entry.object_id)).hexdigest()
        if observed != expected_digest:
            raise ValueError(f"manifest-bound file hash mismatch: {path}")
        paths.add(path)

    witness = manifest.get("witness")
    if not isinstance(witness, dict):
        raise ValueError("certificate manifest has no witness object")
    filename = _safe_manifest_path(
        witness.get("filename"),
        "witness.filename",
    )
    if len(PurePosixPath(filename).parts) != 1:
        raise ValueError("witness filename must not contain directories")
    witness_path = f"certificates/{filename}"
    witness_entry = entries.get(witness_path)
    if witness_entry is None:
        raise ValueError("certificate witness is absent from Git")
    witness_data = blob_bytes(witness_entry.object_id)
    expected_hash = witness.get("sha256")
    expected_size = witness.get("size_bytes")
    if (
        not isinstance(expected_hash, str)
        or SHA256_RE.fullmatch(expected_hash) is None
        or hashlib.sha256(witness_data).hexdigest() != expected_hash
        or isinstance(expected_size, bool)
        or not isinstance(expected_size, int)
        or len(witness_data) != expected_size
    ):
        raise ValueError("certificate witness does not match its manifest")
    paths.add(witness_path)

    paths.update(
        path for path in entries if path.startswith("verifier/")
    )
    missing = sorted(path for path in paths if path not in entries)
    if missing:
        raise ValueError(f"certificate support files are absent: {missing}")
    return sorted(paths)


def build_certificate_archive(
    output: Path,
    version: str,
    reference: str,
) -> None:
    entries = entry_map(reference)
    selected = [entries[path] for path in certificate_file_paths(reference)]
    build_archive(
        output,
        f"{PROJECT}-certificate-v{version}",
        selected,
    )


def asset_names(version: str) -> dict[str, str]:
    return {
        "certificate": f"{PROJECT}-certificate-v{version}.tar.gz",
        "paper": f"{PROJECT}-paper-v{version}.pdf",
        "source": f"{PROJECT}-source-v{version}.tar.gz",
    }


def expected_release_files(reference: str) -> set[str]:
    return set(asset_names(project_version(reference)).values()) | {
        "SHA256SUMS"
    }


def committed_paper_relative(version: str) -> str:
    return f"paper/{PROJECT}-paper-v{version}.pdf"


def verify_pdf_bytes(data: bytes, label: str) -> None:
    if data[:5] != b"%PDF-":
        raise ValueError(f"{label} is not a PDF")


def write_checksums(directory: Path, names: dict[str, str]) -> None:
    lines = [
        f"{sha256(directory / name)}  {name}\n"
        for name in sorted(names.values())
    ]
    (directory / "SHA256SUMS").write_text("".join(lines), encoding="ascii")


def read_checksums(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line_number, line in enumerate(
        path.read_text(encoding="ascii").splitlines(),
        start=1,
    ):
        match = CHECKSUM_RE.fullmatch(line)
        if match is None:
            raise ValueError(f"invalid checksum line {line_number}")
        digest, name = match.groups()
        if name in entries:
            raise ValueError(f"duplicate checksum entry: {name}")
        entries[name] = digest
    return entries


def build_assets(reference: str, paper: Path, tag: str | None) -> None:
    commit = resolve_ref(reference)
    version = project_version(commit)
    if tag is not None:
        validate_tag(commit, tag, version)
    committed_paper = bytes_at_ref(
        commit,
        committed_paper_relative(version),
    )
    verify_pdf_bytes(committed_paper, "committed release paper")
    if (
        not paper.is_file()
        or paper.is_symlink()
        or paper.read_bytes() != committed_paper
    ):
        raise ValueError("fresh paper build does not match the committed PDF")
    names = asset_names(version)

    RELEASE_DIR.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix="release-assets-", dir=RELEASE_DIR.parent)
    )
    try:
        (staging / names["paper"]).write_bytes(committed_paper)
        build_certificate_archive(
            staging / names["certificate"],
            version,
            commit,
        )
        build_source_archive(staging / names["source"], version, commit)
        for path in staging.iterdir():
            path.chmod(0o644)
        write_checksums(staging, names)
        if RELEASE_DIR.is_symlink():
            raise ValueError("dist/release must not be a symlink")
        if RELEASE_DIR.exists():
            shutil.rmtree(RELEASE_DIR)
        os.replace(staging, RELEASE_DIR)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    print(f"built 4 release files from {commit}")


def verify_archive(
    path: Path,
    prefix: str,
    expected_entries: list[TreeEntry],
) -> None:
    expected = {
        f"{prefix}/{entry.path}": entry for entry in expected_entries
    }
    with tarfile.open(path, mode="r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)):
            raise ValueError("archive contains duplicate members")
        observed = {member.name: member for member in members}
        if set(observed) != set(expected):
            raise ValueError("archive does not match the selected Git tree")
        for name, entry in expected.items():
            member = observed[name]
            if (
                not member.isfile()
                or Path(name).is_absolute()
                or ".." in Path(name).parts
                or member.mode != entry.mode
                or member.mtime != 0
                or member.uid != 0
                or member.gid != 0
                or member.uname != "root"
                or member.gname != "root"
                or bool(member.pax_headers)
                or getattr(member, "sparse", None) is not None
            ):
                raise ValueError(f"unsafe archive member: {name}")
            stream = archive.extractfile(member)
            if stream is None or stream.read() != blob_bytes(entry.object_id):
                raise ValueError(f"archive content mismatch: {name}")


def verify_source_archive(path: Path, version: str, reference: str) -> None:
    verify_archive(
        path,
        f"{PROJECT}-v{version}",
        tree_entries(reference),
    )


def verify_certificate_archive(
    path: Path,
    version: str,
    reference: str,
) -> None:
    entries = entry_map(reference)
    verify_archive(
        path,
        f"{PROJECT}-certificate-v{version}",
        [entries[item] for item in certificate_file_paths(reference)],
    )


def verify_assets(reference: str, paper: Path, tag: str | None) -> None:
    commit = resolve_ref(reference)
    version = project_version(commit)
    if tag is not None:
        validate_tag(commit, tag, version)
    names = asset_names(version)
    expected_files = set(names.values()) | {"SHA256SUMS"}
    if not RELEASE_DIR.is_dir() or RELEASE_DIR.is_symlink():
        raise ValueError("dist/release is missing or unsafe")
    paths = list(RELEASE_DIR.iterdir())
    if (
        {path.name for path in paths} != expected_files
        or any(not path.is_file() or path.is_symlink() for path in paths)
    ):
        raise ValueError("dist/release contains an unexpected asset set")
    checksums = read_checksums(RELEASE_DIR / "SHA256SUMS")
    if set(checksums) != set(names.values()):
        raise ValueError("SHA256SUMS has an unexpected asset set")
    for name, digest in checksums.items():
        if sha256(RELEASE_DIR / name) != digest:
            raise ValueError(f"release asset hash mismatch: {name}")

    committed_paper = bytes_at_ref(
        commit,
        committed_paper_relative(version),
    )
    verify_pdf_bytes(committed_paper, "committed release paper")
    if (
        not paper.is_file()
        or paper.is_symlink()
        or paper.read_bytes() != committed_paper
    ):
        raise ValueError("fresh paper build does not match the committed PDF")
    if (RELEASE_DIR / names["paper"]).read_bytes() != committed_paper:
        raise ValueError("release paper does not match the committed PDF")
    verify_certificate_archive(
        RELEASE_DIR / names["certificate"],
        version,
        commit,
    )
    verify_source_archive(RELEASE_DIR / names["source"], version, commit)
    print(f"verified 4 release files against {commit}")


def validate_remote_release_payload(
    payload: dict[str, object],
    tag: str,
    expected_files: set[str],
    state: str,
    local_directory: Path | None = None,
    require_immutable: bool = False,
) -> None:
    if payload.get("tagName") != tag:
        raise ValueError("remote release tag does not match")
    if payload.get("isDraft") is not (state == "draft"):
        raise ValueError(f"remote release is not in the expected {state} state")
    if require_immutable and payload.get("isImmutable") is not True:
        raise ValueError("published release is not immutable")

    raw_assets = payload.get("assets")
    if not isinstance(raw_assets, list):
        raise ValueError("remote release assets are missing")
    assets: dict[str, dict[str, object]] = {}
    for asset in raw_assets:
        if not isinstance(asset, dict):
            raise ValueError("remote release asset record is invalid")
        name = asset.get("name")
        if not isinstance(name, str) or name in assets:
            raise ValueError("remote release asset names are invalid")
        assets[name] = asset
    if set(assets) != expected_files:
        raise ValueError("remote release does not contain the exact asset set")

    for name, asset in assets.items():
        digest = asset.get("digest")
        size = asset.get("size")
        if asset.get("state") != "uploaded":
            raise ValueError(f"remote release asset is not uploaded: {name}")
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
        ):
            raise ValueError(f"remote release asset has no SHA-256 digest: {name}")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError(f"remote release asset has invalid size: {name}")

    if local_directory is None:
        return
    if not local_directory.is_dir() or local_directory.is_symlink():
        raise ValueError("local release directory is missing or unsafe")
    local_paths = list(local_directory.iterdir())
    if (
        {path.name for path in local_paths} != expected_files
        or any(not path.is_file() or path.is_symlink() for path in local_paths)
    ):
        raise ValueError("local release directory does not match the asset set")
    for name, asset in assets.items():
        path = local_directory / name
        if asset["digest"] != f"sha256:{sha256(path)}":
            raise ValueError(f"remote release asset digest mismatch: {name}")
        if asset["size"] != path.stat().st_size:
            raise ValueError(f"remote release asset size mismatch: {name}")


def check_remote_release(
    repository: str,
    reference: str,
    tag: str,
    state: str,
    compare_local: bool,
    require_immutable: bool,
) -> None:
    commit = resolve_ref(reference)
    version = project_version(commit)
    validate_tag(commit, tag, version)
    output = subprocess.run(
        [
            "gh",
            "release",
            "view",
            tag,
            "--repo",
            repository,
            "--json",
            "tagName,isDraft,isImmutable,assets",
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout
    payload = json.loads(output)
    if not isinstance(payload, dict):
        raise ValueError("remote release response is not an object")
    validate_remote_release_payload(
        payload,
        tag,
        expected_release_files(commit),
        state,
        RELEASE_DIR if compare_local else None,
        require_immutable,
    )
    print(f"verified remote {state} release {tag} against {commit}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--check-remote", action="store_true")
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--tag")
    parser.add_argument(
        "--paper",
        type=Path,
        default=ROOT / "build" / "paper" / "main.pdf",
    )
    parser.add_argument("--repo")
    parser.add_argument(
        "--remote-state",
        choices=("draft", "published"),
    )
    parser.add_argument("--compare-local", action="store_true")
    parser.add_argument("--require-immutable", action="store_true")
    args = parser.parse_args()
    paper = args.paper if args.paper.is_absolute() else ROOT / args.paper
    try:
        if args.check_remote:
            if args.repo is None or args.tag is None or args.remote_state is None:
                raise ValueError(
                    "--check-remote requires --repo, --tag, and --remote-state"
                )
            check_remote_release(
                args.repo,
                args.ref,
                args.tag,
                args.remote_state,
                args.compare_local,
                args.require_immutable,
            )
        elif args.check:
            verify_assets(args.ref, paper, args.tag)
        else:
            build_assets(args.ref, paper, args.tag)
            verify_assets(args.ref, paper, args.tag)
    except (
        json.JSONDecodeError,
        OSError,
        subprocess.CalledProcessError,
        tarfile.TarError,
        UnicodeError,
        ValueError,
    ) as error:
        print(f"release asset error: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
