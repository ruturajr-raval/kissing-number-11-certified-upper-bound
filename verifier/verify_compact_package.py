#!/usr/bin/env python3
"""Command-line verifier for the complete compact Project 10 package."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve(strict=True).parent))

try:
    from .package_manifest import (
        PackageManifestError,
        verify_compact_package,
    )
except ImportError:
    from package_manifest import (
        PackageManifestError,
        verify_compact_package,
    )


SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


def _parse_sha256(value: str) -> str:
    if SHA256_PATTERN.fullmatch(value) is None:
        raise argparse.ArgumentTypeError(
            "expected 64 lowercase hexadecimal SHA-256 characters"
        )
    return value


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the complete dimension-11 compact certificate package, "
            "including every bound file and exact coefficient."
        )
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--project-root",
        type=Path,
        help="project root; defaults to the manifest directory's parent",
    )
    parser.add_argument("--expected-manifest-sha256", type=_parse_sha256)
    parser.add_argument("--expected-witness-sha256", type=_parse_sha256)
    parser.add_argument("--expected-source-specification", type=_parse_sha256)
    parser.add_argument("--expected-rounding-specification", type=_parse_sha256)
    parser.add_argument(
        "--expected-verification-specification",
        type=_parse_sha256,
    )
    parser.add_argument(
        "--release",
        action="store_true",
        help="require every published hash and provenance trust anchor",
    )
    return parser


def cli_main(argv: list[str] | None = None) -> int:
    arguments = _argument_parser().parse_args(argv)
    if arguments.release and any(
        value is None
        for value in (
            arguments.expected_manifest_sha256,
            arguments.expected_witness_sha256,
            arguments.expected_source_specification,
            arguments.expected_rounding_specification,
            arguments.expected_verification_specification,
        )
    ):
        print(
            "verification failed: release mode requires manifest, witness, "
            "source-, rounding-, and verification-specification hashes",
            file=sys.stderr,
        )
        return 2
    try:
        report = verify_compact_package(
            arguments.manifest,
            project_root=arguments.project_root,
            expected_manifest_sha256=arguments.expected_manifest_sha256,
            expected_witness_sha256=arguments.expected_witness_sha256,
            expected_source_specification=(
                arguments.expected_source_specification
            ),
            expected_rounding_specification=(
                arguments.expected_rounding_specification
            ),
            expected_verification_specification=(
                arguments.expected_verification_specification
            ),
        )
    except PackageManifestError as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            report.as_dict(),
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
