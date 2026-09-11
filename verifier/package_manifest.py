#!/usr/bin/env python3
"""Strict package-manifest verification for the compact Project 10 certificate."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence

try:
    from .compact_certificate import (
        CompactCertificateError,
        CompactCertificateReplay,
        CompactCertificateReport,
        canonical_block_layout,
    )
    from .compact_witness import (
        DEFAULT_LIMITS,
        CompactWitnessError,
        MatrixBlock,
        WitnessLimits,
        WitnessReport,
        read_compact_witness_bytes,
    )
except ImportError:
    from compact_certificate import (
        CompactCertificateError,
        CompactCertificateReplay,
        CompactCertificateReport,
        canonical_block_layout,
    )
    from compact_witness import (
        DEFAULT_LIMITS,
        CompactWitnessError,
        MatrixBlock,
        WitnessLimits,
        WitnessReport,
        read_compact_witness_bytes,
    )


SHA256_LENGTH = 64
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_BOUND_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BOUND_BYTES = 256 * 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 20_000
MAX_JSON_INTEGER_DIGITS = 20
MAX_JSON_STRING_BYTES = 64 * 1024
EXPECTED_AUTHOR = "Ruturaj R Raval"
EXPECTED_AFFILIATION = "Independent Researcher"
EXPECTED_ORCID = "0000-0003-4930-8981"
EXPECTED_FORMAT = "kn11-compact-certificate"
EXPECTED_FORMAT_VERSION = 2
EXPECTED_FORMULA_REVISION = "kn11-reduced-dual-coefficients-v2"
EXPECTED_JULIA_VERSION = "1.12.7"
EXPECTED_SOLVER_REVISION = "09ac81aed031bdea714832cf515244f6eb223531"
EXPECTED_SAMPLE_SHA256 = (
    "9b8af0d4133749c485c9e36269d2f606a18427a3c17af7875665c5d293f97351"
)
EXPECTED_WITNESS_FILENAME = "kn11-degree17-witness-v2.bin"
EXPECTED_PROJECTION_CHECKPOINT_SHA256 = (
    "b39c3d218dd5d459018d6f112ef57e9ebe12d083751a594bd7a53bf8b6909826"
)
EXPECTED_VERIFICATION_MODE = (
    "process-isolated-threaded-affine-sequential-arb-cholesky-v2"
)
EXPECTED_AFFINE_CHUNK_SIZE = 100
EXPECTED_AFFINE_WORKER_THREADS = 2

EXPECTED_EVIDENCE_PATHS = (
    "evidence/canonical-samples.json",
    "evidence/cross-language-formulation.json",
    "evidence/explicit-schema-audit.json",
    "evidence/problem-structure.json",
    "evidence/residual-space.json",
    "evidence/sample-unisolvence.json",
)

EXPECTED_SOURCE_PATHS = (
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


class PackageManifestError(Exception):
    """Raised when a compact certificate package is malformed or inconsistent."""


@dataclass(frozen=True)
class ManifestBindingsReport:
    manifest_sha256: str
    problem_descriptor_sha256: str
    witness_path: Path
    witness_bytes: bytes
    witness: WitnessReport
    source_count: int
    evidence_count: int
    source_specification: str
    rounding_specification: str
    verification_specification: str


@dataclass(frozen=True)
class CompactPackageReport:
    bindings: ManifestBindingsReport
    certificate: CompactCertificateReport

    def as_dict(self) -> dict[str, Any]:
        output = self.certificate.as_dict()
        output.update(
            {
                "evidence_count": self.bindings.evidence_count,
                "manifest_sha256": self.bindings.manifest_sha256,
                "problem_descriptor_sha256": (
                    self.bindings.problem_descriptor_sha256
                ),
                "source_count": self.bindings.source_count,
            }
        )
        return output


def _expect_exact_keys(
    value: Any,
    keys: set[str],
    path: str,
) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise PackageManifestError(f"{path} must be an object")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        raise PackageManifestError(
            f"{path} has wrong keys; missing={missing}, extra={extra}"
        )
    return value


def _expect_string(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise PackageManifestError(f"{path} must be a string")
    if not value or len(value.encode("utf-8")) > 16_384:
        raise PackageManifestError(f"{path} has an invalid length")
    return value


def _expect_integer(value: Any, path: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise PackageManifestError(
            f"{path} must be an integer greater than or equal to {minimum}"
        )
    return value


def _expect_sha256(value: Any, path: str) -> str:
    token = _expect_string(value, path)
    if len(token) != SHA256_LENGTH or any(
        character not in "0123456789abcdef" for character in token
    ):
        raise PackageManifestError(f"{path} must be a lowercase SHA-256")
    return token


def _reject_duplicate_pairs(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise PackageManifestError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def _reject_json_constant(value: str) -> None:
    raise PackageManifestError(f"invalid JSON constant: {value}")


def _reject_json_float(value: str) -> None:
    raise PackageManifestError(f"floating-point JSON value is forbidden: {value}")


def _parse_json_integer(value: str) -> int:
    digits = value[1:] if value.startswith("-") else value
    if len(digits) > MAX_JSON_INTEGER_DIGITS:
        raise PackageManifestError("manifest integer has too many digits")
    return int(value)


def _validate_json_tree(value: Any, *, depth: int = 0) -> int:
    if depth > MAX_JSON_DEPTH:
        raise PackageManifestError("manifest JSON nesting is too deep")
    if isinstance(value, str):
        if len(value.encode("utf-8")) > MAX_JSON_STRING_BYTES:
            raise PackageManifestError("manifest JSON string is too long")
        return 1
    if value is None or isinstance(value, (bool, int)):
        return 1
    if isinstance(value, list):
        nodes = 1
        for item in value:
            nodes += _validate_json_tree(item, depth=depth + 1)
            if nodes > MAX_JSON_NODES:
                raise PackageManifestError("manifest JSON has too many nodes")
        return nodes
    if isinstance(value, dict):
        nodes = 1
        for key, item in value.items():
            nodes += _validate_json_tree(key, depth=depth + 1)
            nodes += _validate_json_tree(item, depth=depth + 1)
            if nodes > MAX_JSON_NODES:
                raise PackageManifestError("manifest JSON has too many nodes")
        return nodes
    raise PackageManifestError("manifest contains an unsupported JSON value")


def _stable_file_bytes(path: Path, maximum_bytes: int) -> bytes:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PackageManifestError(f"cannot open {path}: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise PackageManifestError(f"{path} is not a regular file")
        if before.st_size > maximum_bytes:
            raise PackageManifestError(f"{path} exceeds its size limit")
        chunks = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise PackageManifestError(f"{path} changed while reading")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise PackageManifestError(f"{path} changed while reading")
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
        raise PackageManifestError(f"{path} changed while reading")
    return b"".join(chunks)


def _stable_file_sha256(path: Path) -> tuple[str, int]:
    return _stable_file_digest(path, MAX_BOUND_FILE_BYTES)


def _stable_file_digest(
    path: Path,
    maximum_bytes: int,
) -> tuple[str, int]:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PackageManifestError(f"cannot open {path}: {exc}") from exc
    digest = hashlib.sha256()
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise PackageManifestError(f"{path} is not a regular file")
        if before.st_size > maximum_bytes:
            raise PackageManifestError(f"{path} exceeds its size limit")
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise PackageManifestError(f"{path} changed while reading")
            digest.update(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise PackageManifestError(f"{path} changed while reading")
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
        raise PackageManifestError(f"{path} changed while reading")
    return digest.hexdigest(), before.st_size


def _load_manifest(path: Path) -> tuple[Mapping[str, Any], str]:
    data = _stable_file_bytes(path, MAX_MANIFEST_BYTES)
    if not data.endswith(b"\n"):
        raise PackageManifestError("manifest must end with one LF byte")
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise PackageManifestError("manifest must be ASCII JSON") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
            parse_float=_reject_json_float,
            parse_int=_parse_json_integer,
        )
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise PackageManifestError(f"invalid manifest JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise PackageManifestError("manifest root must be an object")
    _validate_json_tree(value)
    return value, hashlib.sha256(data).hexdigest()


def _safe_relative_path(value: Any, path: str) -> str:
    token = _expect_string(value, path)
    if "\\" in token:
        raise PackageManifestError(f"{path} must use POSIX separators")
    relative = PurePosixPath(token)
    if relative.is_absolute() or token != relative.as_posix():
        raise PackageManifestError(f"{path} must be a canonical relative path")
    if any(part in ("", ".", "..") for part in relative.parts):
        raise PackageManifestError(f"{path} contains an unsafe path component")
    return token


def _resolve_bound_path(project_root: Path, token: str) -> Path:
    candidate = project_root.joinpath(*PurePosixPath(token).parts)
    try:
        root_resolved = project_root.resolve(strict=True)
        parent_resolved = candidate.parent.resolve(strict=True)
    except OSError as exc:
        raise PackageManifestError(f"cannot resolve bound path {token}: {exc}") from exc
    if parent_resolved != root_resolved and root_resolved not in parent_resolved.parents:
        raise PackageManifestError(f"bound path escapes project root: {token}")
    return candidate


def _verify_bound_files(
    entries: Any,
    *,
    expected_paths: Sequence[str],
    project_root: Path,
    path: str,
) -> dict[str, str]:
    if not isinstance(entries, list):
        raise PackageManifestError(f"{path} must be an array")
    parsed: list[tuple[str, str]] = []
    for index, raw_entry in enumerate(entries):
        entry = _expect_exact_keys(
            raw_entry,
            {"path", "sha256"},
            f"{path}[{index}]",
        )
        token = _safe_relative_path(entry["path"], f"{path}[{index}].path")
        digest = _expect_sha256(entry["sha256"], f"{path}[{index}].sha256")
        parsed.append((token, digest))
    names = tuple(token for token, _ in parsed)
    if names != tuple(expected_paths):
        raise PackageManifestError(f"{path} does not match the required file list")
    output = {}
    total_bytes = 0
    for token, expected_digest in parsed:
        actual_digest, size_bytes = _stable_file_sha256(
            _resolve_bound_path(project_root, token)
        )
        total_bytes += size_bytes
        if total_bytes > MAX_TOTAL_BOUND_BYTES:
            raise PackageManifestError(
                f"{path} exceeds the aggregate size limit"
            )
        if actual_digest != expected_digest:
            raise PackageManifestError(f"{token}: SHA-256 mismatch")
        output[token] = actual_digest
    return output


def _problem_descriptor_sha256(
    *,
    evidence_hashes: Mapping[str, str],
    source_hashes: Mapping[str, str],
) -> str:
    fields = (
        f"formula_revision={EXPECTED_FORMULA_REVISION}",
        "dimension=11",
        "degree=17",
        "costheta=1/2",
        "fixed_objective=86899/100",
        "formulation=reduced-three-point-dual",
        f"sample_sha256={EXPECTED_SAMPLE_SHA256}",
        "sample_rank_prime=65521",
        "sample_rank=1461",
        (
            "problem_structure_sha256="
            f"{evidence_hashes['evidence/problem-structure.json']}"
        ),
        (
            "residual_space_sha256="
            f"{evidence_hashes['evidence/residual-space.json']}"
        ),
        (
            "theorem_bridge_sha256="
            f"{source_hashes['docs/THEOREM_BRIDGE.md']}"
        ),
    )
    payload = ("\n".join(fields) + "\n").encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _specification_digest(fields: Sequence[str]) -> str:
    payload = ("\n".join(fields) + "\n").encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _source_specification_fields(
    source_hashes: Mapping[str, str],
) -> tuple[str, ...]:
    return (
        "schema_version=1",
        "mode=fixed-objective",
        "dimension=11",
        "costheta=1/2",
        "d2=17",
        "d3=17",
        "fixed_objective=86899/100",
        "precision=384",
        f"solver_revision={EXPECTED_SOLVER_REVISION}",
        f"sample_sha256={EXPECTED_SAMPLE_SHA256}",
        "sample_prime=65521",
        "sample_rank=1461",
        (
            "module_sha256="
            f"{source_hashes['src/KissingNumber11Certificate.jl']}"
        ),
        f"project_sha256={source_hashes['Project.toml']}",
        f"manifest_sha256={source_hashes['Manifest.toml']}",
        (
            "script_sha256="
            f"{source_hashes['scripts/solve_fixed_objective.jl']}"
        ),
    )


def _rounding_specification_fields(
    source_hashes: Mapping[str, str],
    source_specification: str,
) -> tuple[str, ...]:
    return (
        "schema_version=1",
        f"source_specification={source_specification}",
        (
            "fixed_bundle_sha256="
            "ceed3e884625b2ff6365ea6c68eecdcdddd900d8aac0fa4d9955d8f1894f003a"
        ),
        f"julia_version={EXPECTED_JULIA_VERSION}",
        (
            "rounding_script_sha256="
            f"{source_hashes['scripts/round_exact_solution.jl']}"
        ),
        (
            "checkpoint_source_sha256="
            f"{source_hashes['src/CheckpointRecovery.jl']}"
        ),
        (
            "portable_source_sha256="
            f"{source_hashes['src/PortableExactSolution.jl']}"
        ),
        (
            "verification_source_sha256="
            f"{source_hashes['src/StrictInteriorVerification.jl']}"
        ),
        "rounding_mode=strict-interior-direct-projection",
        "projection_encoding=rational-bigint-upper-triangle-v1",
        "rounding_seed=11017",
        "approximation_decimals=60",
        "regularization=1e-50",
        "redundancyfactor=8",
        "pseudo=true",
        "pseudo_columnfactor=1.05",
    )


def _verification_specification_fields(
    source_hashes: Mapping[str, str],
    source_specification: str,
    rounding_specification: str,
) -> tuple[str, ...]:
    return (
        "schema_version=1",
        f"source_specification={source_specification}",
        f"rounding_specification={rounding_specification}",
        (
            "projection_checkpoint_sha256="
            f"{EXPECTED_PROJECTION_CHECKPOINT_SHA256}"
        ),
        f"julia_version={EXPECTED_JULIA_VERSION}",
        (
            "verification_script_sha256="
            f"{source_hashes['scripts/verify_projection_checkpoint.jl']}"
        ),
        (
            "parallel_verification_source_sha256="
            f"{source_hashes['src/ParallelExactVerification.jl']}"
        ),
        (
            "strict_verification_source_sha256="
            f"{source_hashes['src/StrictInteriorVerification.jl']}"
        ),
        (
            "portable_source_sha256="
            f"{source_hashes['src/PortableExactSolution.jl']}"
        ),
        f"verification_mode={EXPECTED_VERIFICATION_MODE}",
        f"affine_chunk_size={EXPECTED_AFFINE_CHUNK_SIZE}",
        f"affine_worker_threads={EXPECTED_AFFINE_WORKER_THREADS}",
    )


def _verify_specification(
    value: Any,
    *,
    expected_fields: Sequence[str],
    expected_published_digest: str | None,
    path: str,
) -> str:
    specification = _expect_exact_keys(value, {"digest", "fields"}, path)
    raw_fields = specification["fields"]
    if not isinstance(raw_fields, list):
        raise PackageManifestError(f"{path}.fields must be an array")
    fields = tuple(
        _expect_string(field, f"{path}.fields[{index}]")
        for index, field in enumerate(raw_fields)
    )
    if fields != tuple(expected_fields):
        raise PackageManifestError(f"{path}.fields are inconsistent")
    digest = _expect_sha256(specification["digest"], f"{path}.digest")
    recomputed = _specification_digest(fields)
    if digest != recomputed:
        raise PackageManifestError(f"{path}.digest is inconsistent")
    if (
        expected_published_digest is not None
        and digest
        != _expect_sha256(
            expected_published_digest,
            f"expected_{path.rsplit('.', 1)[-1]}",
        )
    ):
        raise PackageManifestError(f"{path} does not match published value")
    return digest


def verify_manifest_bindings(
    manifest_path: str | os.PathLike[str],
    *,
    project_root: str | os.PathLike[str] | None = None,
    expected_manifest_sha256: str | None = None,
    expected_witness_sha256: str | None = None,
    expected_source_specification: str | None = None,
    expected_rounding_specification: str | None = None,
    expected_verification_specification: str | None = None,
    witness_consumer: Callable[[MatrixBlock], None] | None = None,
    limits: WitnessLimits = DEFAULT_LIMITS,
) -> ManifestBindingsReport:
    """Verify package metadata, bound files, witness bytes, and descriptor."""

    path = Path(manifest_path)
    root = (
        Path(project_root)
        if project_root is not None
        else path.parent.parent
    )
    manifest, manifest_sha256 = _load_manifest(path)
    if (
        expected_manifest_sha256 is not None
        and manifest_sha256 != _expect_sha256(
            expected_manifest_sha256,
            "expected_manifest_sha256",
        )
    ):
        raise PackageManifestError("manifest SHA-256 does not match published value")

    top = _expect_exact_keys(
        manifest,
        {
            "affiliation",
            "author",
            "blocks",
            "evidence",
            "format",
            "format_version",
            "orcid",
            "problem",
            "provenance",
            "sources",
            "status",
            "verification",
            "witness",
        },
        "manifest",
    )
    if top["author"] != EXPECTED_AUTHOR:
        raise PackageManifestError("manifest author is incorrect")
    if top["affiliation"] != EXPECTED_AFFILIATION:
        raise PackageManifestError("manifest affiliation is incorrect")
    if top["orcid"] != EXPECTED_ORCID:
        raise PackageManifestError("manifest ORCID is incorrect")
    if top["format"] != EXPECTED_FORMAT:
        raise PackageManifestError("manifest format is incorrect")
    if top["format_version"] != EXPECTED_FORMAT_VERSION:
        raise PackageManifestError("manifest format version is incorrect")
    if top["status"] != "candidate-exact-certificate":
        raise PackageManifestError("manifest status is incorrect")

    evidence_hashes = _verify_bound_files(
        top["evidence"],
        expected_paths=EXPECTED_EVIDENCE_PATHS,
        project_root=root,
        path="manifest.evidence",
    )
    source_hashes = _verify_bound_files(
        top["sources"],
        expected_paths=EXPECTED_SOURCE_PATHS,
        project_root=root,
        path="manifest.sources",
    )
    descriptor = _problem_descriptor_sha256(
        evidence_hashes=evidence_hashes,
        source_hashes=source_hashes,
    )

    problem = _expect_exact_keys(
        top["problem"],
        {
            "cos_theta",
            "degree",
            "dimension",
            "fixed_objective",
            "formula_revision",
            "problem_descriptor_sha256",
            "sample_sha256",
            "theorem",
        },
        "manifest.problem",
    )
    expected_problem = {
        "cos_theta": "1/2",
        "degree": 17,
        "dimension": 11,
        "fixed_objective": "86899/100",
        "formula_revision": EXPECTED_FORMULA_REVISION,
        "problem_descriptor_sha256": descriptor,
        "sample_sha256": EXPECTED_SAMPLE_SHA256,
        "theorem": "tau_11 <= 868",
    }
    if dict(problem) != expected_problem:
        raise PackageManifestError("manifest problem descriptor is inconsistent")

    provenance = _expect_exact_keys(
        top["provenance"],
        {
            "rounding_specification",
            "source_specification",
            "verification_specification",
        },
        "manifest.provenance",
    )
    source_fields = _source_specification_fields(source_hashes)
    source_specification = _verify_specification(
        provenance["source_specification"],
        expected_fields=source_fields,
        expected_published_digest=expected_source_specification,
        path="manifest.provenance.source_specification",
    )
    rounding_fields = _rounding_specification_fields(
        source_hashes,
        source_specification,
    )
    rounding_specification = _verify_specification(
        provenance["rounding_specification"],
        expected_fields=rounding_fields,
        expected_published_digest=expected_rounding_specification,
        path="manifest.provenance.rounding_specification",
    )
    verification_fields = _verification_specification_fields(
        source_hashes,
        source_specification,
        rounding_specification,
    )
    verification_specification = _verify_specification(
        provenance["verification_specification"],
        expected_fields=verification_fields,
        expected_published_digest=expected_verification_specification,
        path="manifest.provenance.verification_specification",
    )

    verification = _expect_exact_keys(
        top["verification"],
        {
            "affine_identities_exact",
            "block_count",
            "objective_exact",
            "positive_semidefinite_exact",
        },
        "manifest.verification",
    )
    if (
        verification["affine_identities_exact"] is not True
        or verification["objective_exact"] is not True
        or verification["positive_semidefinite_exact"] is not True
        or _expect_integer(
            verification["block_count"],
            "manifest.verification.block_count",
        )
        != 70
    ):
        raise PackageManifestError("manifest primary-verification record is invalid")

    expected_layout = canonical_block_layout(17)
    raw_blocks = top["blocks"]
    if not isinstance(raw_blocks, list) or len(raw_blocks) != len(expected_layout):
        raise PackageManifestError("manifest block list has the wrong length")
    expected_ranks = []
    for index, (raw_block, layout) in enumerate(zip(raw_blocks, expected_layout)):
        block = _expect_exact_keys(
            raw_block,
            {"dimension", "name", "rank"},
            f"manifest.blocks[{index}]",
        )
        dimension = _expect_integer(
            block["dimension"],
            f"manifest.blocks[{index}].dimension",
            minimum=1,
        )
        if block["name"] != layout.name or dimension != layout.dimension:
            raise PackageManifestError(
                f"manifest.blocks[{index}] does not match canonical layout"
            )
        rank = _expect_integer(block["rank"], f"manifest.blocks[{index}].rank")
        if rank != layout.dimension:
            raise PackageManifestError(
                f"manifest.blocks[{index}].rank must equal its dimension"
            )
        expected_ranks.append(rank)

    witness = _expect_exact_keys(
        top["witness"],
        {
            "filename",
            "maximum_denominator_bits",
            "maximum_numerator_bits",
            "rank_sum",
            "rational_count",
            "sha256",
            "size_bytes",
        },
        "manifest.witness",
    )
    if witness["filename"] != EXPECTED_WITNESS_FILENAME:
        raise PackageManifestError("manifest witness filename is incorrect")
    witness_sha256 = _expect_sha256(
        witness["sha256"],
        "manifest.witness.sha256",
    )
    if (
        expected_witness_sha256 is not None
        and witness_sha256 != _expect_sha256(
            expected_witness_sha256,
            "expected_witness_sha256",
        )
    ):
        raise PackageManifestError("witness SHA-256 does not match published value")
    witness_size = _expect_integer(
        witness["size_bytes"],
        "manifest.witness.size_bytes",
    )
    witness_path = path.parent / EXPECTED_WITNESS_FILENAME
    witness_bytes = _stable_file_bytes(
        witness_path,
        limits.max_bytes,
    )
    actual_witness_sha256 = hashlib.sha256(witness_bytes).hexdigest()
    actual_witness_size = len(witness_bytes)
    if actual_witness_sha256 != witness_sha256 or actual_witness_size != witness_size:
        raise PackageManifestError("manifest witness binding is inconsistent")

    parsed_ranks = []

    def consume_witness_block(block: MatrixBlock) -> None:
        parsed_ranks.append(block.rank)
        if witness_consumer is not None:
            witness_consumer(block)

    try:
        parsed_witness = read_compact_witness_bytes(
            witness_bytes,
            expected_layout,
            consumer=consume_witness_block,
            limits=limits,
        )
    except CompactWitnessError as exc:
        raise PackageManifestError(str(exc)) from exc
    if (
        parsed_witness.sha256 != witness_sha256
        or parsed_witness.size_bytes != witness_size
    ):
        raise PackageManifestError(
            "parsed witness does not match the manifest binding"
        )
    if parsed_ranks != expected_ranks:
        raise PackageManifestError("manifest block ranks do not match witness")
    expected_witness_metadata = {
        "maximum_denominator_bits": parsed_witness.maximum_denominator_bits,
        "maximum_numerator_bits": parsed_witness.maximum_numerator_bits,
        "rank_sum": parsed_witness.rank_sum,
        "rational_count": parsed_witness.rational_count,
        "size_bytes": parsed_witness.size_bytes,
    }
    for field, expected_value in expected_witness_metadata.items():
        actual_value = _expect_integer(
            witness[field],
            f"manifest.witness.{field}",
        )
        if actual_value != expected_value:
            raise PackageManifestError(
                f"manifest.witness.{field} does not match witness"
            )

    return ManifestBindingsReport(
        manifest_sha256=manifest_sha256,
        problem_descriptor_sha256=descriptor,
        witness_path=witness_path,
        witness_bytes=witness_bytes,
        witness=parsed_witness,
        source_count=len(source_hashes),
        evidence_count=len(evidence_hashes),
        source_specification=source_specification,
        rounding_specification=rounding_specification,
        verification_specification=verification_specification,
    )


def verify_compact_package(
    manifest_path: str | os.PathLike[str],
    *,
    project_root: str | os.PathLike[str] | None = None,
    expected_manifest_sha256: str | None = None,
    expected_witness_sha256: str | None = None,
    expected_source_specification: str | None = None,
    expected_rounding_specification: str | None = None,
    expected_verification_specification: str | None = None,
    limits: WitnessLimits = DEFAULT_LIMITS,
) -> CompactPackageReport:
    """Verify every package binding and then replay all exact coefficients."""

    replay = CompactCertificateReplay(
        dimension=11,
        degree=17,
        cos_theta=Fraction(1, 2),
        target_objective=Fraction(86899, 100),
    )
    try:
        bindings = verify_manifest_bindings(
            manifest_path,
            project_root=project_root,
            expected_manifest_sha256=expected_manifest_sha256,
            expected_witness_sha256=expected_witness_sha256,
            expected_source_specification=expected_source_specification,
            expected_rounding_specification=expected_rounding_specification,
            expected_verification_specification=(
                expected_verification_specification
            ),
            witness_consumer=replay.consume,
            limits=limits,
        )
        certificate = replay.finish(bindings.witness)
    except CompactCertificateError as exc:
        raise PackageManifestError(str(exc)) from exc
    if certificate.witness != bindings.witness:
        raise PackageManifestError(
            "witness metadata changed between binding and coefficient replay"
        )
    if (
        certificate.positive_definite_block_count
        != bindings.witness.block_count
        or certificate.exact_psd_fallback_block_count != 0
    ):
        raise PackageManifestError(
            "release witness did not pass strict interval positivity"
        )
    return CompactPackageReport(
        bindings=bindings,
        certificate=certificate,
    )


__all__ = [
    "CompactPackageReport",
    "ManifestBindingsReport",
    "PackageManifestError",
    "verify_compact_package",
    "verify_manifest_bindings",
]
