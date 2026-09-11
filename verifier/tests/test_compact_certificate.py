"""Exact coefficient tests for compact rational matrix certificates."""

from __future__ import annotations

import math
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path


TEST_DIRECTORY = Path(__file__).resolve().parent
VERIFIER_DIRECTORY = TEST_DIRECTORY.parent
PROJECT_ROOT = VERIFIER_DIRECTORY.parent
FIXTURE = TEST_DIRECTORY / "fixtures" / "smoke-exact-witness-v2.bin"
sys.path.insert(0, str(VERIFIER_DIRECTORY))

from compact_certificate import (  # noqa: E402
    CompactCertificateError,
    _f_trivariate_column,
    _gegenbauer_kernel,
    _original_column,
    _sos_component_exponents,
    _CertificateAccumulator,
    _parameters,
    _rigorous_positive_definite,
    _rigorous_positive_semidefinite,
    canonical_block_layout,
    verify_compact_certificate,
)
from compact_witness import LDLBlock, MatrixBlock, read_compact_witness  # noqa: E402
from formulation import (  # noqa: E402
    domain_weights,
    expand_elementary_symmetric,
    reduce_symmetric_polynomial,
    trivariate_add,
    trivariate_constant,
    trivariate_is_symmetric,
    trivariate_multiply,
    trivariate_power,
    trivariate_scale,
    trivariate_subtract,
    trivariate_variable,
)


F = Fraction


def _uleb128(value: int) -> bytes:
    output = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        output.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(output)


def _magnitude(value: int) -> bytes:
    data = value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big")
    return _uleb128(len(data)) + data


def _tamper_first_a_numerator(data: bytes) -> bytes:
    blocks = []
    read_compact_witness(
        FIXTURE,
        canonical_block_layout(2),
        consumer=blocks.append,
    )
    scalar = next(block for block in blocks if block.name == "a/00")
    value = scalar.matrix[0][0]
    replacement = value.numerator + 1
    while (
        replacement.bit_length() != value.numerator.bit_length()
        or math.gcd(replacement, value.denominator) != 1
    ):
        replacement += 1
    old = _magnitude(value.numerator)
    new = _magnitude(replacement)
    if len(old) != len(new) or data.count(old) != 1:
        raise AssertionError("fixture numerator is not uniquely replaceable")
    return data.replace(old, new, 1)


def _direct_sos_polynomial(
    degree: int,
    costheta: Fraction,
    weight_index: int,
    representation_index: int,
    column: tuple[Fraction, ...],
):
    components = _sos_component_exponents(
        degree,
        weight_index,
        representation_index,
    )
    invariant_components = []
    offset = 0
    for exponents in components:
        next_offset = offset + len(exponents)
        invariant_components.append(
            {
                exponent: value
                for exponent, value in zip(
                    exponents,
                    column[offset:next_offset],
                )
                if value
            }
        )
        offset = next_offset
    expanded = [
        expand_elementary_symmetric(polynomial)
        for polynomial in invariant_components
    ]
    u, v, t = (trivariate_variable(index) for index in range(3))
    one = trivariate_constant(1)
    alternating = trivariate_multiply(
        trivariate_multiply(
            trivariate_subtract(u, v),
            trivariate_subtract(v, t),
        ),
        trivariate_subtract(t, u),
    )
    rows = {
        1: ((one,),),
        2: ((alternating,),),
        3: (
            (
                trivariate_subtract(
                    trivariate_scale(u, 2),
                    trivariate_add(v, t),
                ),
                trivariate_subtract(
                    trivariate_scale(trivariate_multiply(v, t), 2),
                    trivariate_add(
                        trivariate_multiply(u, t),
                        trivariate_multiply(u, v),
                    ),
                ),
            ),
            (
                trivariate_subtract(v, t),
                trivariate_subtract(
                    trivariate_multiply(u, t),
                    trivariate_multiply(u, v),
                ),
            ),
        ),
    }
    factors = {
        1: (F(1),),
        2: (F(1),),
        3: (F(1, 2), F(3, 2)),
    }
    output = {}
    for factor, row in zip(
        factors[representation_index],
        rows[representation_index],
    ):
        expression = {}
        for equivariant, invariant in zip(row, expanded):
            expression = trivariate_add(
                expression,
                trivariate_multiply(equivariant, invariant),
            )
        output = trivariate_add(
            output,
            trivariate_scale(trivariate_power(expression, 2), factor),
        )
    return trivariate_multiply(
        domain_weights(costheta)[weight_index - 1],
        output,
    )


class CompactCertificateLayoutTests(unittest.TestCase):
    def test_smoke_layout_is_canonical(self) -> None:
        self.assertEqual(
            [(block.name, block.dimension) for block in canonical_block_layout(2)],
            [
                ("F/00", 3),
                ("F/01", 2),
                ("F/02", 1),
                ("a/00", 1),
                ("a/01", 1),
                ("a/02", 1),
                ("a/03", 1),
                ("a/04", 1),
                ("trivariatesos/1/1", 4),
                ("trivariatesos/1/3", 3),
                ("trivariatesos/2/1", 2),
                ("trivariatesos/2/3", 1),
                ("trivariatesos/3/1", 1),
                ("trivariatesos/5/1", 1),
                ("univariatesos/1", 3),
                ("univariatesos/2", 2),
            ],
        )

    def test_dimension_eleven_layout_has_all_seventy_blocks(self) -> None:
        layout = canonical_block_layout(17)
        self.assertEqual(len(layout), 70)
        trivariate = {
            block.name: block.dimension
            for block in layout
            if block.name.startswith("trivariatesos/")
        }
        self.assertEqual(
            trivariate,
            {
                "trivariatesos/1/1": 237,
                "trivariatesos/1/2": 147,
                "trivariatesos/1/3": 378,
                "trivariatesos/2/1": 204,
                "trivariatesos/2/2": 123,
                "trivariatesos/2/3": 321,
                "trivariatesos/3/1": 174,
                "trivariatesos/3/2": 102,
                "trivariatesos/3/3": 270,
                "trivariatesos/4/1": 147,
                "trivariatesos/4/2": 83,
                "trivariatesos/4/3": 225,
                "trivariatesos/5/1": 174,
                "trivariatesos/5/2": 102,
                "trivariatesos/5/3": 270,
            },
        )

    def test_original_coordinate_column_undoes_permutation(self) -> None:
        block = LDLBlock(
            name="F/00",
            dimension=3,
            rank=1,
            permutation=(2, 0, 1),
            diagonal=(F(2),),
            columns=((F(1), F(3), F(4)),),
        )
        self.assertEqual(
            _original_column(block, block.columns[0]),
            (F(3), F(4), F(1)),
        )

    def test_direct_matrix_block_retains_exact_entries(self) -> None:
        matrix = ((F(2), F(-1)), (F(-1), F(3)))
        block = MatrixBlock("F/00", 2, matrix)
        self.assertEqual(block.matrix, matrix)


class PositiveDefinitenessTests(unittest.TestCase):
    def test_interval_cholesky_accepts_positive_definite_matrix(self) -> None:
        _rigorous_positive_definite(
            ((F(2), F(-1)), (F(-1), F(3))),
            precision_bits=64,
        )

    def test_interval_cholesky_rejects_indefinite_matrix(self) -> None:
        with self.assertRaisesRegex(
            CompactCertificateError,
            "failed at pivot",
        ):
            _rigorous_positive_definite(
                ((F(1), F(2)), (F(2), F(1))),
                precision_bits=64,
            )

    def test_interval_cholesky_rejects_unsupported_precision(self) -> None:
        with self.assertRaisesRegex(
            CompactCertificateError,
            "outside the supported range",
        ):
            _rigorous_positive_definite(((F(1),),), precision_bits=63)

    def test_exact_fallback_accepts_singular_psd_matrix(self) -> None:
        self.assertFalse(
            _rigorous_positive_semidefinite(
                ((F(1), F(1)), (F(1), F(1))),
                precision_bits=64,
            )
        )

    def test_exact_fallback_rejects_indefinite_matrix(self) -> None:
        with self.assertRaisesRegex(
            CompactCertificateError,
            "exact PSD fallback",
        ):
            _rigorous_positive_semidefinite(
                ((F(1), F(2)), (F(2), F(1))),
                precision_bits=64,
            )


class ExactFormulaTests(unittest.TestCase):
    def test_degree_two_gegenbauer_kernel_is_exact(self) -> None:
        u, v, t = (trivariate_variable(index) for index in range(3))
        kernel = _gegenbauer_kernel(2, 2, u, v, t)
        expected = trivariate_subtract(
            trivariate_scale(
                trivariate_power(
                    trivariate_subtract(
                        t,
                        trivariate_multiply(u, v),
                    ),
                    2,
                ),
                2,
            ),
            trivariate_multiply(
                trivariate_subtract(
                    trivariate_constant(1),
                    trivariate_power(u, 2),
                ),
                trivariate_subtract(
                    trivariate_constant(1),
                    trivariate_power(v, 2),
                ),
            ),
        )
        self.assertEqual(kernel, expected)

    def test_f_column_contraction_matches_explicit_degree_one_formula(self) -> None:
        u, v, t = (trivariate_variable(index) for index in range(3))
        column = (F(2), F(-3))
        c_u = trivariate_add(
            trivariate_constant(column[0]),
            trivariate_scale(u, column[1]),
        )
        c_v = trivariate_add(
            trivariate_constant(column[0]),
            trivariate_scale(v, column[1]),
        )
        c_t = trivariate_add(
            trivariate_constant(column[0]),
            trivariate_scale(t, column[1]),
        )
        q_uvt = trivariate_subtract(t, trivariate_multiply(u, v))
        q_tuv = trivariate_subtract(v, trivariate_multiply(t, u))
        q_tvu = trivariate_subtract(u, trivariate_multiply(t, v))
        explicit = trivariate_scale(
            trivariate_add(
                trivariate_add(
                    trivariate_multiply(
                        q_uvt,
                        trivariate_multiply(c_u, c_v),
                    ),
                    trivariate_multiply(
                        q_tuv,
                        trivariate_multiply(c_u, c_t),
                    ),
                ),
                trivariate_multiply(
                    q_tvu,
                    trivariate_multiply(c_v, c_t),
                ),
            ),
            F(1, 3),
        )
        contracted = _f_trivariate_column(3, 1, column)
        self.assertEqual(contracted, explicit)
        self.assertTrue(trivariate_is_symmetric(contracted))

    def test_all_fifteen_sos_families_match_direct_expansion(self) -> None:
        degree = 17
        accumulator = _CertificateAccumulator(
            _parameters(11, degree, F(1, 2), F(86899, 100))
        )
        checked = 0
        for weight_index in range(1, 6):
            for representation_index in range(1, 4):
                components = _sos_component_exponents(
                    degree,
                    weight_index,
                    representation_index,
                )
                dimension = sum(len(component) for component in components)
                self.assertGreater(dimension, 0)
                column = [F(0)] * dimension
                offset = 0
                for component_index, component in enumerate(components):
                    column[offset] = F(component_index + 1, component_index + 2)
                    offset += len(component)
                block = LDLBlock(
                    name=(
                        f"trivariatesos/{weight_index}/"
                        f"{representation_index}"
                    ),
                    dimension=dimension,
                    rank=1,
                    permutation=tuple(range(dimension)),
                    diagonal=(F(1),),
                    columns=(tuple(column),),
                )
                accumulator.trivariate_sos = {}
                accumulator._consume_trivariate_sos(block)
                direct = reduce_symmetric_polynomial(
                    _direct_sos_polynomial(
                        degree,
                        F(1, 2),
                        weight_index,
                        representation_index,
                        tuple(column),
                    )
                )
                self.assertEqual(accumulator.trivariate_sos, direct)
                checked += 1
        self.assertEqual(checked, 15)


class EndToEndCompactCertificateTests(unittest.TestCase):
    def test_solver_produced_smoke_witness_verifies(self) -> None:
        report = verify_compact_certificate(
            FIXTURE,
            dimension=3,
            degree=2,
            cos_theta=F(1, 2),
            target_objective=F(15),
        )
        self.assertEqual(report.objective_value, F(15))
        self.assertEqual(report.witness.block_count, 16)
        self.assertEqual(
            report.witness.rank_sum,
            sum(block.dimension for block in canonical_block_layout(2)),
        )
        self.assertEqual(report.positive_semidefinite_block_count, 16)
        self.assertGreater(report.exact_psd_fallback_block_count, 0)
        self.assertEqual(report.positivity_precision_bits, 896)
        self.assertEqual(report.univariate_coefficient_count, 5)
        self.assertEqual(report.trivariate_coefficient_count, 11)

    def test_cli_is_pinned_to_the_dimension_eleven_target(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(VERIFIER_DIRECTORY / "verify_compact_certificate.py"),
                str(FIXTURE),
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("expected 70 blocks", completed.stderr)

    def test_wrong_target_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            CompactCertificateError,
            "objective mismatch",
        ):
            verify_compact_certificate(
                FIXTURE,
                dimension=3,
                degree=2,
                cos_theta=F(1, 2),
                target_objective=F(14),
            )

    def test_mathematical_witness_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "tampered.bin"
            path.write_bytes(_tamper_first_a_numerator(FIXTURE.read_bytes()))
            with self.assertRaises(CompactCertificateError):
                verify_compact_certificate(
                    path,
                    dimension=3,
                    degree=2,
                    cos_theta=F(1, 2),
                    target_objective=F(15),
                )

    def test_missing_or_extra_blocks_are_rejected(self) -> None:
        original = FIXTURE.read_bytes()
        for block_count in (15, 17):
            with self.subTest(block_count=block_count):
                with tempfile.TemporaryDirectory() as temporary:
                    path = Path(temporary) / "layout-tamper.bin"
                    path.write_bytes(
                        original[:8]
                        + block_count.to_bytes(4, "little")
                        + original[12:]
                    )
                    with self.assertRaisesRegex(
                        CompactCertificateError,
                        "expected 16 blocks",
                    ):
                        verify_compact_certificate(
                            path,
                            dimension=3,
                            degree=2,
                            cos_theta=F(1, 2),
                            target_objective=F(15),
                        )

    def test_trailing_bytes_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trailing.bin"
            path.write_bytes(FIXTURE.read_bytes() + b"\x00")
            with self.assertRaisesRegex(
                CompactCertificateError,
                "trailing bytes",
            ):
                verify_compact_certificate(
                    path,
                    dimension=3,
                    degree=2,
                    cos_theta=F(1, 2),
                    target_objective=F(15),
                )


if __name__ == "__main__":
    unittest.main()
