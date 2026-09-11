#!/usr/bin/env python3
"""Command-line entry point for exact compact coefficient verification."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from .compact_certificate import (
        CompactCertificateError,
        verify_kn11_compact_certificate,
    )
except ImportError:
    from compact_certificate import (
        CompactCertificateError,
        verify_kn11_compact_certificate,
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
            "Verify the compact exact certificate for the dimension-11, "
            "degree-17 kissing-number target using only rational arithmetic."
        )
    )
    parser.add_argument("witness", type=Path)
    parser.add_argument(
        "--expected-sha256",
        type=_parse_sha256,
        help="also require the published witness SHA-256",
    )
    return parser


def cli_main(argv: list[str] | None = None) -> int:
    arguments = _argument_parser().parse_args(argv)
    try:
        report = verify_kn11_compact_certificate(arguments.witness)
    except CompactCertificateError as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        return 1
    if (
        arguments.expected_sha256 is not None
        and report.witness.sha256 != arguments.expected_sha256
    ):
        print(
            "verification failed: witness SHA-256 does not match the "
            "published value",
            file=sys.stderr,
        )
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
