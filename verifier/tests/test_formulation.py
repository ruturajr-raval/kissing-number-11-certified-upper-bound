"""Tests for exact coefficient-formulation utilities."""

from __future__ import annotations

import sys
import unittest
from fractions import Fraction
from itertools import permutations
from pathlib import Path


TEST_DIRECTORY = Path(__file__).resolve().parent
VERIFIER_DIRECTORY = TEST_DIRECTORY.parent
sys.path.insert(0, str(VERIFIER_DIRECTORY))

from formulation import (  # noqa: E402
    alternating_representation_kernel,
    chebyshev_basis,
    domain_weights,
    elementary_symmetric_exponents,
    evaluate_elementary_symmetric,
    expand_elementary_symmetric,
    invariant_total_degree,
    normalized_gegenbauer_basis,
    reduce_symmetric_polynomial,
    representation_kernels,
    standard_representation_kernel,
    trivial_representation_kernel,
    trivariate_add,
    trivariate_constant,
    trivariate_evaluate,
    trivariate_is_symmetric,
    trivariate_multiply,
    trivariate_permute,
    trivariate_power,
    trivariate_scale,
    trivariate_subtract,
    trivariate_total_degree,
    trivariate_variable,
    univariate_add,
    univariate_evaluate,
    univariate_multiply,
    univariate_power,
)


F = Fraction


class UnivariatePolynomialTests(unittest.TestCase):
    def test_add_multiply_and_power_are_exact(self) -> None:
        self.assertEqual(
            univariate_add((1, 2, 0), (F(-1, 2), -2, 3)),
            (F(1, 2), F(0), F(3)),
        )
        self.assertEqual(
            univariate_multiply((1, 1), (1, -1)),
            (F(1), F(0), F(-1)),
        )
        self.assertEqual(
            univariate_power((1, 1), 4),
            (F(1), F(4), F(6), F(4), F(1)),
        )
        self.assertEqual(
            univariate_evaluate((F(1, 3), F(-2, 5), F(7, 11)), F(3, 7)),
            F(1, 3) - F(6, 35) + F(63, 539),
        )

    def test_chebyshev_known_formulas_and_normalization(self) -> None:
        basis = chebyshev_basis(5)
        self.assertEqual(basis[0], (F(1),))
        self.assertEqual(basis[1], (F(0), F(1)))
        self.assertEqual(basis[2], (F(-1), F(0), F(2)))
        self.assertEqual(basis[3], (F(0), F(-3), F(0), F(4)))
        self.assertEqual(basis[4], (F(1), F(0), F(-8), F(0), F(8)))
        self.assertEqual(
            basis[5],
            (F(0), F(5), F(0), F(-20), F(0), F(16)),
        )
        self.assertTrue(
            all(univariate_evaluate(polynomial, 1) == 1 for polynomial in basis)
        )

    def test_normalized_gegenbauer_known_dimensions(self) -> None:
        self.assertEqual(normalized_gegenbauer_basis(7, 2), chebyshev_basis(7))
        legendre = normalized_gegenbauer_basis(4, 3)
        self.assertEqual(legendre[2], (F(-1, 2), F(0), F(3, 2)))
        self.assertEqual(legendre[3], (F(0), F(-3, 2), F(0), F(5, 2)))
        dimension_eleven = normalized_gegenbauer_basis(8, 11)
        self.assertEqual(
            dimension_eleven[2],
            (F(-1, 10), F(0), F(11, 10)),
        )
        self.assertEqual(
            dimension_eleven[3],
            (F(0), F(-3, 10), F(0), F(13, 10)),
        )
        for degree, polynomial in enumerate(dimension_eleven):
            self.assertEqual(univariate_evaluate(polynomial, 1), 1)
            self.assertTrue(
                all(
                    coefficient == 0
                    for power, coefficient in enumerate(polynomial)
                    if (degree - power) % 2
                )
            )

    def test_invalid_univariate_inputs_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            univariate_power((1, 1), -1)
        with self.assertRaisesRegex(ValueError, "at least 2"):
            normalized_gegenbauer_basis(3, 1)
        with self.assertRaisesRegex(TypeError, "exact rationals"):
            univariate_add((1.0,), (1,))


class SparseTrivariatePolynomialTests(unittest.TestCase):
    def test_sparse_operations_and_evaluation(self) -> None:
        u, v, t = (trivariate_variable(index) for index in range(3))
        expression = trivariate_power(
            trivariate_add(
                trivariate_subtract(u, trivariate_scale(v, 2)),
                trivariate_scale(t, F(1, 3)),
            ),
            3,
        )
        point = (F(2, 3), F(-1, 2), F(3, 5))
        expected = (point[0] - 2 * point[1] + point[2] / 3) ** 3
        self.assertEqual(trivariate_evaluate(expression, point), expected)
        self.assertEqual(trivariate_total_degree(expression), 3)
        self.assertEqual(trivariate_total_degree({}), -1)
        self.assertEqual(
            trivariate_multiply(expression, trivariate_constant(0)),
            {},
        )

    def test_permutation_renames_variables(self) -> None:
        u = trivariate_variable(0)
        v = trivariate_variable(1)
        self.assertEqual(trivariate_permute(u, (1, 0, 2)), v)
        with self.assertRaisesRegex(ValueError, "exactly once"):
            trivariate_permute(u, (0, 0, 2))


class SymmetricReductionTests(unittest.TestCase):
    def test_elementary_basis_counts_and_degree_order(self) -> None:
        degree_seventeen = elementary_symmetric_exponents(17)
        degree_thirty_four = elementary_symmetric_exponents(34)
        self.assertEqual(len(degree_seventeen), 237)
        self.assertEqual(len(degree_thirty_four), 1461)
        weighted_degrees = [
            a_exponent + 2 * b_exponent + 3 * c_exponent
            for a_exponent, b_exponent, c_exponent in degree_thirty_four
        ]
        self.assertEqual(weighted_degrees, sorted(weighted_degrees))
        self.assertEqual(max(weighted_degrees), 34)
        self.assertEqual(len(set(degree_thirty_four)), 1461)

    def test_power_sum_reductions_match_newton_identities(self) -> None:
        u, v, t = (trivariate_variable(index) for index in range(3))
        square_sum = trivariate_add(
            trivariate_add(trivariate_power(u, 2), trivariate_power(v, 2)),
            trivariate_power(t, 2),
        )
        cube_sum = trivariate_add(
            trivariate_add(trivariate_power(u, 3), trivariate_power(v, 3)),
            trivariate_power(t, 3),
        )
        self.assertEqual(
            reduce_symmetric_polynomial(square_sum),
            {(2, 0, 0): F(1), (0, 1, 0): F(-2)},
        )
        self.assertEqual(
            reduce_symmetric_polynomial(cube_sum),
            {
                (3, 0, 0): F(1),
                (1, 1, 0): F(-3),
                (0, 0, 1): F(3),
            },
        )

    def test_reduction_round_trip_is_exact(self) -> None:
        invariant = {
            (0, 0, 0): F(7, 13),
            (5, 0, 0): F(-2, 9),
            (1, 2, 0): F(11, 17),
            (2, 0, 2): F(-5, 8),
            (0, 1, 2): F(19, 23),
        }
        expanded = expand_elementary_symmetric(invariant)
        self.assertTrue(trivariate_is_symmetric(expanded))
        self.assertEqual(reduce_symmetric_polynomial(expanded), invariant)
        self.assertEqual(invariant_total_degree(invariant), 8)
        for point in (
            (F(-1), F(-1, 2), F(1, 3)),
            (F(2, 5), F(3, 7), F(-4, 9)),
            (F(1, 2), F(1, 2), F(1, 2)),
        ):
            self.assertEqual(
                trivariate_evaluate(expanded, point),
                evaluate_elementary_symmetric(invariant, point),
            )

    def test_nonsymmetric_polynomial_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not symmetric"):
            reduce_symmetric_polynomial(trivariate_variable(0))


class DomainWeightTests(unittest.TestCase):
    def test_canonical_weights_have_expected_degrees_and_formulas(self) -> None:
        weights = domain_weights(F(1, 2))
        self.assertEqual(
            [trivariate_total_degree(weight) for weight in weights],
            [0, 2, 4, 6, 3],
        )
        self.assertTrue(all(trivariate_is_symmetric(weight) for weight in weights))
        self.assertEqual(
            reduce_symmetric_polynomial(weights[1]),
            {
                (0, 0, 0): F(3, 2),
                (1, 0, 0): F(-1, 2),
                (2, 0, 0): F(-1),
                (0, 1, 0): F(2),
            },
        )
        self.assertEqual(
            reduce_symmetric_polynomial(weights[4]),
            {
                (0, 0, 0): F(1),
                (2, 0, 0): F(-1),
                (0, 1, 0): F(2),
                (0, 0, 1): F(2),
            },
        )

    def test_product_weight_matches_endpoint_factorization(self) -> None:
        weights = domain_weights(F(1, 2))
        plus_factor = expand_elementary_symmetric(
            {
                (0, 0, 0): F(1),
                (1, 0, 0): F(1),
                (0, 1, 0): F(1),
                (0, 0, 1): F(1),
            }
        )
        upper_factor = expand_elementary_symmetric(
            {
                (0, 0, 0): F(1, 8),
                (1, 0, 0): F(-1, 4),
                (0, 1, 0): F(1, 2),
                (0, 0, 1): F(-1),
            }
        )
        self.assertEqual(
            weights[3],
            trivariate_multiply(plus_factor, upper_factor),
        )

    def test_weight_reductions_agree_at_exact_points(self) -> None:
        for weight in domain_weights(F(1, 2)):
            reduced = reduce_symmetric_polynomial(weight)
            self.assertEqual(
                expand_elementary_symmetric(reduced),
                weight,
            )
            self.assertLessEqual(invariant_total_degree(reduced), 6)
            for point in (
                (F(-1), F(-1), F(1)),
                (F(-1, 2), F(0), F(1, 2)),
                (F(1, 7), F(-2, 9), F(3, 11)),
            ):
                self.assertEqual(
                    trivariate_evaluate(weight, point),
                    evaluate_elementary_symmetric(reduced, point),
                )


class RepresentationKernelTests(unittest.TestCase):
    def test_kernel_shapes_and_registry(self) -> None:
        trivial = trivial_representation_kernel()
        alternating = alternating_representation_kernel()
        standard = standard_representation_kernel()
        self.assertEqual((len(trivial), len(trivial[0])), (1, 1))
        self.assertEqual((len(alternating), len(alternating[0])), (1, 1))
        self.assertEqual(
            (len(standard), tuple(len(row) for row in standard)),
            (2, (2, 2)),
        )
        self.assertEqual(
            set(representation_kernels()),
            {"trivial", "alternating", "standard"},
        )
        self.assertEqual(standard[0][1], standard[1][0])

    def test_trivial_and_alternating_closed_forms(self) -> None:
        trivial = trivial_representation_kernel()[0][0]
        alternating = alternating_representation_kernel()[0][0]
        self.assertEqual(
            reduce_symmetric_polynomial(trivial),
            {(0, 0, 0): F(1)},
        )
        self.assertEqual(
            reduce_symmetric_polynomial(alternating),
            {
                (2, 2, 0): F(1),
                (0, 3, 0): F(-4),
                (3, 0, 1): F(-4),
                (0, 0, 2): F(-27),
                (1, 1, 1): F(18),
            },
        )
        self.assertEqual(trivariate_total_degree(alternating), 6)

    def test_standard_kernel_closed_forms(self) -> None:
        kernel = standard_representation_kernel()
        expected = (
            {
                (2, 0, 0): F(2),
                (0, 1, 0): F(-6),
            },
            {
                (0, 0, 1): F(9),
                (1, 1, 0): F(-1),
            },
            {
                (0, 2, 0): F(2),
                (1, 0, 1): F(-6),
            },
        )
        self.assertEqual(reduce_symmetric_polynomial(kernel[0][0]), expected[0])
        self.assertEqual(reduce_symmetric_polynomial(kernel[0][1]), expected[1])
        self.assertEqual(reduce_symmetric_polynomial(kernel[1][1]), expected[2])
        self.assertEqual(
            [
                trivariate_total_degree(kernel[0][0]),
                trivariate_total_degree(kernel[0][1]),
                trivariate_total_degree(kernel[1][1]),
            ],
            [2, 3, 4],
        )

    def test_all_kernel_entries_are_symmetric_and_evaluate_consistently(self) -> None:
        points = (
            (F(-1), F(0), F(1, 2)),
            (F(1, 3), F(-2, 5), F(4, 7)),
        )
        for matrix in representation_kernels().values():
            for row in matrix:
                for polynomial in row:
                    self.assertTrue(trivariate_is_symmetric(polynomial))
                    reduced = reduce_symmetric_polynomial(polynomial)
                    for point in points:
                        expected = trivariate_evaluate(polynomial, point)
                        self.assertEqual(
                            evaluate_elementary_symmetric(reduced, point),
                            expected,
                        )
                        for permutation in permutations(range(3)):
                            permuted_point = tuple(
                                point[index] for index in permutation
                            )
                            self.assertEqual(
                                trivariate_evaluate(polynomial, permuted_point),
                                expected,
                            )


if __name__ == "__main__":
    unittest.main()
