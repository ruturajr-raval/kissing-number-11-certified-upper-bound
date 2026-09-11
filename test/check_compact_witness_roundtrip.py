#!/usr/bin/env python3
"""Check the Julia compact-witness fixture with the independent parser."""

from __future__ import annotations

import os
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "verifier"
TESTS = VERIFIER / "tests"
sys.path.insert(0, str(VERIFIER))
sys.path.insert(0, str(TESTS))

from compact_witness import BlockLayout, read_compact_witness, reconstruct_block
from test_compact_witness import fixture_bytes


path = Path(
    os.environ.get(
        "KN11_COMPACT_FIXTURE",
        ROOT / "build" / "compact-witness-fixture.bin",
    )
)
actual = path.read_bytes()
expected = fixture_bytes()
if actual != expected:
    raise SystemExit("Julia compact witness bytes differ from the canonical fixture")

blocks = []
report = read_compact_witness(
    path,
    (BlockLayout("F/00", 2), BlockLayout("a/00", 1)),
    consumer=blocks.append,
)
if report.rational_count != 4 or report.rank_sum != 3:
    raise SystemExit("compact witness metadata is incorrect")
if reconstruct_block(blocks[0]) != (
    (Fraction(2), Fraction(-2)),
    (Fraction(-2), Fraction(7, 2)),
):
    raise SystemExit("first compact witness block reconstructed incorrectly")
if reconstruct_block(blocks[1]) != ((Fraction(0),),):
    raise SystemExit("zero compact witness block reconstructed incorrectly")
print("compact_witness_roundtrip=pass")
print(f"compact_witness_sha256={report.sha256}")
