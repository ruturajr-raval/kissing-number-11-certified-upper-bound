#!/usr/bin/env python3
"""Cross-check Julia problem coefficients with the independent Python formulas."""

from __future__ import annotations

import hashlib
import json
import sys
from fractions import Fraction
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "verifier"))

from compact_certificate import (  # noqa: E402
    _CertificateAccumulator,
    _parameters,
)
from compact_witness import LDLBlock  # noqa: E402
from formulation import (  # noqa: E402
    evaluate_elementary_symmetric,
    normalized_gegenbauer_basis,
    trivariate_evaluate,
    univariate_evaluate,
)


EVIDENCE = ROOT / "evidence" / "cross-language-formulation.json"


def rational(token: str) -> Fraction:
    numerator, denominator = token.split("/")
    return Fraction(int(numerator), int(denominator))


def rank_one_block(record: dict[str, object]) -> LDLBlock:
    dimension = int(record["dimension"])
    column = tuple(rational(token) for token in record["column"])
    if len(column) != dimension:
        raise SystemExit(f"{record['name']}: column length mismatch")
    return LDLBlock(
        name=str(record["name"]),
        dimension=dimension,
        rank=1,
        permutation=tuple(range(dimension)),
        diagonal=(Fraction(1),),
        columns=(column,),
    )


data = json.loads(EVIDENCE.read_text(encoding="ascii"))
dimension = int(data["dimension"])
full_degree = int(data["full_degree"])
sos_degree = int(data["sos_degree"])
cos_theta = rational(data["cos_theta"])
w = rational(data["w"])
sample = tuple(rational(token) for token in data["sample"])
if (dimension, full_degree, sos_degree, cos_theta) != (
    11,
    17,
    6,
    Fraction(1, 2),
):
    raise SystemExit("cross-language evidence has the wrong fixed parameters")
if w == 0 or any(value == 0 for value in sample) or len(set(sample)) != 3:
    raise SystemExit("cross-language evaluation points are degenerate")

gegenbauer = normalized_gegenbauer_basis(2 * full_degree, dimension)
for record in data["a"]:
    degree = int(record["degree"])
    actual = univariate_evaluate(gegenbauer[degree], w)
    expected = rational(record["value"])
    if actual != expected:
        raise SystemExit(f"a/{degree:02d}: Julia and Python values differ")

full_parameters = _parameters(
    dimension,
    full_degree,
    cos_theta,
    Fraction(0),
)
f_check_counts = {degree: 0 for degree in range(full_degree + 1)}
for record in data["f"]:
    degree = int(record["degree"])
    f_check_counts[degree] += 1
    named_record = dict(record)
    named_record["name"] = f"F/{degree:02d}"
    block = rank_one_block(named_record)
    accumulator = _CertificateAccumulator(full_parameters)
    accumulator.univariate = (Fraction(0),)
    accumulator.trivariate_f = {}
    accumulator._consume_f(block)
    actual_univariate = univariate_evaluate(accumulator.univariate, w)
    actual_trivariate = trivariate_evaluate(accumulator.trivariate_f, sample)
    if actual_univariate != rational(record["univariate"]):
        raise SystemExit(f"F/{degree:02d}: univariate value differs")
    if actual_trivariate != rational(record["trivariate"]):
        raise SystemExit(f"F/{degree:02d}: trivariate value differs")
if set(f_check_counts.values()) != {3}:
    raise SystemExit("each F block must have three cross-language checks")

sos_parameters = _parameters(
    dimension,
    sos_degree,
    cos_theta,
    Fraction(0),
)
univariate_check_counts: dict[str, int] = {}
for record in data["univariate_sos"]:
    block = rank_one_block(record)
    univariate_check_counts[block.name] = (
        univariate_check_counts.get(block.name, 0) + 1
    )
    accumulator = _CertificateAccumulator(sos_parameters)
    accumulator.univariate = (Fraction(0),)
    accumulator._consume_univariate_sos(
        block,
        weighted=block.name.endswith("/2"),
    )
    actual = univariate_evaluate(accumulator.univariate, w)
    if actual != rational(record["value"]):
        raise SystemExit(f"{block.name}: Julia and Python values differ")
if univariate_check_counts != {
    "univariatesos/1": 3,
    "univariatesos/2": 3,
}:
    raise SystemExit("each univariate SOS block must have three checks")

seen_trivariate = set()
trivariate_check_counts: dict[str, int] = {}
for record in data["trivariate_sos"]:
    block = rank_one_block(record)
    trivariate_check_counts[block.name] = (
        trivariate_check_counts.get(block.name, 0) + 1
    )
    accumulator = _CertificateAccumulator(sos_parameters)
    accumulator.trivariate_sos = {}
    accumulator._consume_trivariate_sos(block)
    actual = evaluate_elementary_symmetric(
        accumulator.trivariate_sos,
        sample,
    )
    if actual != rational(record["value"]):
        raise SystemExit(f"{block.name}: Julia and Python values differ")
    seen_trivariate.add(block.name)

if len(seen_trivariate) != 15:
    raise SystemExit("cross-language evidence does not cover all 15 SOS families")
if set(trivariate_check_counts.values()) != {3}:
    raise SystemExit("each three-point SOS family must have three checks")

digest = hashlib.sha256(EVIDENCE.read_bytes()).hexdigest()
print("cross_language_formulation=pass")
print(f"cross_language_formulation_sha256={digest}")
print(f"cross_language_a_terms={len(data['a'])}")
print(f"cross_language_f_checks={len(data['f'])}")
print(f"cross_language_trivariate_sos_checks={len(data['trivariate_sos'])}")
