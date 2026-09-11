#!/usr/bin/env python3
"""Parse the compact witness emitted by the exact-rounding smoke test."""

from __future__ import annotations

import os
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "verifier"))

from compact_certificate import verify_compact_certificate


path = Path(
    os.environ.get(
        "KN11_SMOKE_COMPACT_OUTPUT",
        ROOT / "build" / "smoke-exact-witness.bin",
    )
)
report = verify_compact_certificate(
    path,
    dimension=3,
    degree=2,
    cos_theta=Fraction(1, 2),
    target_objective=Fraction(15),
)
if report.witness.block_count != 16:
    raise SystemExit("smoke compact witness has the wrong block count")
if report.witness.rational_count == 0 or report.witness.rank_sum == 0:
    raise SystemExit("smoke compact witness is unexpectedly empty")
print("smoke_compact_certificate_verify=pass")
print(f"smoke_compact_witness_sha256={report.witness.sha256}")
print(f"smoke_compact_witness_bytes={report.witness.size_bytes}")
print(f"smoke_compact_witness_rank_sum={report.witness.rank_sum}")
