#!/usr/bin/env python3
"""Exact coefficient verifier for compact rational matrix certificates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    from .compact_witness import (
        DEFAULT_LIMITS,
        BlockLayout,
        CompactWitnessError,
        LDLBlock,
        MatrixBlock,
        WitnessLimits,
        WitnessReport,
        read_compact_witness,
        read_compact_witness_bytes,
        reconstruct_block,
    )
    from .formulation import (
        InvariantPolynomial,
        TrivariatePolynomial,
        UnivariatePolynomial,
        chebyshev_basis,
        domain_weights,
        elementary_symmetric_exponents,
        normalized_gegenbauer_basis,
        reduce_symmetric_polynomial,
        representation_kernels,
        trivariate_add,
        trivariate_constant,
        trivariate_is_symmetric,
        trivariate_multiply,
        trivariate_power,
        trivariate_scale,
        trivariate_subtract,
        trivariate_total_degree,
        trivariate_variable,
        univariate_add,
        univariate_evaluate,
        univariate_multiply,
        univariate_power,
        univariate_scale,
    )
except ImportError:
    from compact_witness import (
        DEFAULT_LIMITS,
        BlockLayout,
        CompactWitnessError,
        LDLBlock,
        MatrixBlock,
        WitnessLimits,
        WitnessReport,
        read_compact_witness,
        read_compact_witness_bytes,
        reconstruct_block,
    )
    from formulation import (
        InvariantPolynomial,
        TrivariatePolynomial,
        UnivariatePolynomial,
        chebyshev_basis,
        domain_weights,
        elementary_symmetric_exponents,
        normalized_gegenbauer_basis,
        reduce_symmetric_polynomial,
        representation_kernels,
        trivariate_add,
        trivariate_constant,
        trivariate_is_symmetric,
        trivariate_multiply,
        trivariate_power,
        trivariate_scale,
        trivariate_subtract,
        trivariate_total_degree,
        trivariate_variable,
        univariate_add,
        univariate_evaluate,
        univariate_multiply,
        univariate_power,
        univariate_scale,
    )


ZERO = Fraction(0)
ONE = Fraction(1)
THREE_POINT_WEIGHT_DEGREES = (0, 2, 4, 6, 3)
EQUIVARIANT_DEGREES = {
    1: (0,),
    2: (3,),
    3: (1, 2),
}
POSITIVITY_PRECISION_BITS = 896
EXACT_PSD_FALLBACK_MAX_DIMENSION = 32
EXACT_PSD_FALLBACK_MAX_INPUT_BITS = 4096
EXACT_PSD_FALLBACK_MAX_INTERMEDIATE_BITS = 131_072


class CompactCertificateError(Exception):
    """Raised when an exact compact certificate does not verify."""


@dataclass(frozen=True)
class CompactCertificateParameters:
    dimension: int
    degree: int
    cos_theta: Fraction
    target_objective: Fraction


@dataclass(frozen=True)
class CompactCertificateReport:
    dimension: int
    degree: int
    cos_theta: Fraction
    target_objective: Fraction
    objective_value: Fraction
    positive_definite_block_count: int
    positive_semidefinite_block_count: int
    exact_psd_fallback_block_count: int
    positivity_precision_bits: int
    univariate_coefficient_count: int
    trivariate_coefficient_count: int
    witness: WitnessReport

    def as_dict(self) -> dict[str, Any]:
        return {
            "block_count": self.witness.block_count,
            "cos_theta": _rational_token(self.cos_theta),
            "degree": self.degree,
            "dimension": self.dimension,
            "maximum_denominator_bits": (
                self.witness.maximum_denominator_bits
            ),
            "maximum_numerator_bits": self.witness.maximum_numerator_bits,
            "objective_value": _rational_token(self.objective_value),
            "positive_definite_block_count": (
                self.positive_definite_block_count
            ),
            "positive_semidefinite_block_count": (
                self.positive_semidefinite_block_count
            ),
            "exact_psd_fallback_block_count": (
                self.exact_psd_fallback_block_count
            ),
            "positivity_precision_bits": self.positivity_precision_bits,
            "rank_sum": self.witness.rank_sum,
            "rational_count": self.witness.rational_count,
            "size_bytes": self.witness.size_bytes,
            "status": "valid",
            "target_objective": _rational_token(self.target_objective),
            "trivariate_coefficient_count": (
                self.trivariate_coefficient_count
            ),
            "univariate_coefficient_count": (
                self.univariate_coefficient_count
            ),
            "witness_sha256": self.witness.sha256,
        }


def _rational_token(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def _exact_fraction(value: int | Fraction, name: str) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, Fraction)):
        raise CompactCertificateError(f"{name} must be an exact rational")
    return Fraction(value)


def _parameters(
    dimension: int,
    degree: int,
    cos_theta: int | Fraction,
    target_objective: int | Fraction,
) -> CompactCertificateParameters:
    if (
        isinstance(dimension, bool)
        or not isinstance(dimension, int)
        or dimension < 3
    ):
        raise CompactCertificateError("dimension must be an integer at least 3")
    if (
        isinstance(degree, bool)
        or not isinstance(degree, int)
        or degree < 0
    ):
        raise CompactCertificateError(
            "degree must be a nonnegative integer"
        )
    theta = _exact_fraction(cos_theta, "cos_theta")
    if theta <= -1 or theta >= 1:
        raise CompactCertificateError(
            "cos_theta must lie strictly between -1 and 1"
        )
    target = _exact_fraction(target_objective, "target_objective")
    return CompactCertificateParameters(
        dimension=dimension,
        degree=degree,
        cos_theta=theta,
        target_objective=target,
    )


def _basis_limit(degree: int, weight_degree: int, equivariant_degree: int) -> int:
    remaining = 2 * degree - weight_degree - 2 * equivariant_degree
    return remaining // 2 if remaining >= 0 else -1


def _sos_component_exponents(
    degree: int,
    weight_index: int,
    representation_index: int,
) -> tuple[tuple[tuple[int, int, int], ...], ...]:
    if weight_index not in range(1, 6):
        raise CompactCertificateError("invalid three-point weight index")
    try:
        equivariant_degrees = EQUIVARIANT_DEGREES[representation_index]
    except KeyError as exc:
        raise CompactCertificateError(
            "invalid representation index"
        ) from exc
    weight_degree = THREE_POINT_WEIGHT_DEGREES[weight_index - 1]
    components = []
    for equivariant_degree in equivariant_degrees:
        limit = _basis_limit(
            degree,
            weight_degree,
            equivariant_degree,
        )
        components.append(
            elementary_symmetric_exponents(limit) if limit >= 0 else ()
        )
    return tuple(components)


def canonical_block_layout(degree: int) -> tuple[BlockLayout, ...]:
    """Return the exact lexicographically sorted block layout for ``d2=d3=d``."""

    if isinstance(degree, bool) or not isinstance(degree, int) or degree < 0:
        raise CompactCertificateError(
            "degree must be a nonnegative integer"
        )
    blocks = [
        BlockLayout(f"F/{index:02d}", degree - index + 1)
        for index in range(degree + 1)
    ]
    blocks.extend(
        BlockLayout(f"a/{index:02d}", 1)
        for index in range(2 * degree + 1)
    )
    blocks.append(BlockLayout("univariatesos/1", degree + 1))
    if degree >= 1:
        blocks.append(BlockLayout("univariatesos/2", degree))
    for weight_index in range(1, 6):
        for representation_index in range(1, 4):
            components = _sos_component_exponents(
                degree,
                weight_index,
                representation_index,
            )
            dimension = sum(len(component) for component in components)
            if dimension:
                blocks.append(
                    BlockLayout(
                        (
                            f"trivariatesos/{weight_index}/"
                            f"{representation_index}"
                        ),
                        dimension,
                    )
                )
    return tuple(sorted(blocks, key=lambda block: block.name))


def _invariant_add_scaled(
    target: InvariantPolynomial,
    source: Mapping[Sequence[int], int | Fraction],
    scale: Fraction = ONE,
) -> None:
    if scale == ZERO:
        return
    for raw_exponent, raw_coefficient in source.items():
        exponent = tuple(raw_exponent)
        if len(exponent) != 3:
            raise CompactCertificateError(
                "invariant exponent must have three entries"
            )
        coefficient = _exact_fraction(
            raw_coefficient,
            "invariant coefficient",
        )
        updated = target.get(exponent, ZERO) + scale * coefficient
        if updated:
            target[exponent] = updated
        else:
            target.pop(exponent, None)


def _invariant_scale(
    polynomial: Mapping[Sequence[int], int | Fraction],
    scale: Fraction,
) -> InvariantPolynomial:
    output: InvariantPolynomial = {}
    _invariant_add_scaled(output, polynomial, scale)
    return output


def _invariant_multiply(
    left: Mapping[Sequence[int], int | Fraction],
    right: Mapping[Sequence[int], int | Fraction],
) -> InvariantPolynomial:
    output: InvariantPolynomial = {}
    for left_exponent, raw_left in left.items():
        left_coefficient = _exact_fraction(
            raw_left,
            "invariant coefficient",
        )
        if left_coefficient == ZERO:
            continue
        for right_exponent, raw_right in right.items():
            right_coefficient = _exact_fraction(
                raw_right,
                "invariant coefficient",
            )
            if right_coefficient == ZERO:
                continue
            exponent = (
                left_exponent[0] + right_exponent[0],
                left_exponent[1] + right_exponent[1],
                left_exponent[2] + right_exponent[2],
            )
            output[exponent] = output.get(exponent, ZERO) + (
                left_coefficient * right_coefficient
            )
    return {
        exponent: coefficient
        for exponent, coefficient in output.items()
        if coefficient
    }


def _invariant_square(
    polynomial: Mapping[Sequence[int], int | Fraction],
) -> InvariantPolynomial:
    items = [
        (tuple(exponent), _exact_fraction(value, "invariant coefficient"))
        for exponent, value in polynomial.items()
        if value
    ]
    output: InvariantPolynomial = {}
    for left_index, (left_exponent, left_coefficient) in enumerate(items):
        for right_index in range(left_index, len(items)):
            right_exponent, right_coefficient = items[right_index]
            multiplier = 1 if left_index == right_index else 2
            exponent = (
                left_exponent[0] + right_exponent[0],
                left_exponent[1] + right_exponent[1],
                left_exponent[2] + right_exponent[2],
            )
            output[exponent] = output.get(exponent, ZERO) + (
                multiplier * left_coefficient * right_coefficient
            )
    return {
        exponent: coefficient
        for exponent, coefficient in output.items()
        if coefficient
    }


def _original_column(block: LDLBlock, column: Sequence[Fraction]) -> tuple[Fraction, ...]:
    if len(column) != block.dimension:
        raise CompactCertificateError(
            f"{block.name}: LDL column has the wrong dimension"
        )
    original = [ZERO] * block.dimension
    for permuted_index, original_index in enumerate(block.permutation):
        original[original_index] = column[permuted_index]
    return tuple(original)


def _original_factor_columns(
    block: LDLBlock,
) -> Iterable[tuple[Fraction, tuple[Fraction, ...]]]:
    if len(block.diagonal) != len(block.columns):
        raise CompactCertificateError(
            f"{block.name}: LDL diagonal and column counts differ"
        )
    for diagonal, column in zip(block.diagonal, block.columns):
        if diagonal <= ZERO:
            raise CompactCertificateError(
                f"{block.name}: LDL diagonal is not positive"
            )
        yield diagonal, _original_column(block, column)


def _matrix_from_block(
    block: LDLBlock | MatrixBlock,
) -> tuple[tuple[Fraction, ...], ...]:
    try:
        return reconstruct_block(block)
    except CompactWitnessError as exc:
        raise CompactCertificateError(str(exc)) from exc


def _symmetric_entries(
    matrix: Sequence[Sequence[Fraction]],
) -> Iterable[tuple[int, int, Fraction]]:
    for row in range(len(matrix)):
        for column in range(row, len(matrix)):
            value = matrix[row][column]
            if value:
                yield row, column, value if row == column else 2 * value


def _monomial_quadratic_form(
    matrix: Sequence[Sequence[Fraction]],
) -> UnivariatePolynomial:
    coefficients = [ZERO] * (2 * len(matrix) - 1)
    for row, column, value in _symmetric_entries(matrix):
        coefficients[row + column] += value
    return tuple(coefficients)


def _univariate_quadratic_form(
    matrix: Sequence[Sequence[Fraction]],
    basis: Sequence[Sequence[int | Fraction]],
) -> UnivariatePolynomial:
    if len(matrix) != len(basis):
        raise CompactCertificateError(
            "univariate basis and matrix dimensions differ"
        )
    output: UnivariatePolynomial = (ZERO,)
    for row, column, value in _symmetric_entries(matrix):
        output = univariate_add(
            output,
            univariate_scale(
                univariate_multiply(basis[row], basis[column]),
                value,
            ),
        )
    return output


def _matrix_entry_sum(
    matrix: Sequence[Sequence[Fraction]],
) -> Fraction:
    return sum(
        value
        for _, _, value in _symmetric_entries(matrix)
    )


def _matrix_row_sums(
    matrix: Sequence[Sequence[Fraction]],
) -> tuple[Fraction, ...]:
    return tuple(sum(row) for row in matrix)


def _matrix_bivariate_form(
    matrix: Sequence[Sequence[Fraction]],
    first_variable: int,
    second_variable: int,
) -> TrivariatePolynomial:
    output: TrivariatePolynomial = {}
    for row in range(len(matrix)):
        for column in range(row, len(matrix)):
            value = matrix[row][column]
            if not value:
                continue
            exponent = [0, 0, 0]
            exponent[first_variable] = row
            exponent[second_variable] = column
            key = tuple(exponent)
            output[key] = output.get(key, ZERO) + value
            if row != column:
                exponent = [0, 0, 0]
                exponent[first_variable] = column
                exponent[second_variable] = row
                key = tuple(exponent)
                output[key] = output.get(key, ZERO) + value
    return {
        exponent: coefficient
        for exponent, coefficient in output.items()
        if coefficient
    }


def _invariant_add_shifted_scaled(
    target: InvariantPolynomial,
    polynomial: InvariantPolynomial,
    shift: tuple[int, int, int],
    scale: Fraction,
) -> None:
    if not scale:
        return
    for exponent, coefficient in polynomial.items():
        shifted = (
            exponent[0] + shift[0],
            exponent[1] + shift[1],
            exponent[2] + shift[2],
        )
        value = target.get(shifted, ZERO) + scale * coefficient
        if value:
            target[shifted] = value
        else:
            target.pop(shifted, None)


def _rigorous_positive_definite(
    matrix: Sequence[Sequence[Fraction]],
    *,
    precision_bits: int = POSITIVITY_PRECISION_BITS,
) -> None:
    if precision_bits < 64 or precision_bits > 4096:
        raise CompactCertificateError(
            "interval Cholesky precision is outside the supported range"
        )
    dimension = len(matrix)
    if dimension == 0 or any(len(row) != dimension for row in matrix):
        raise CompactCertificateError(
            "interval Cholesky requires a nonempty square matrix"
        )
    if any(
        matrix[row][column] != matrix[column][row]
        for row in range(dimension)
        for column in range(row + 1, dimension)
    ):
        raise CompactCertificateError(
            "interval Cholesky requires a symmetric matrix"
        )

    scale = 1 << precision_bits

    def ceiling_division(numerator: int, denominator: int) -> int:
        return -((-numerator) // denominator)

    def interval(value: Fraction) -> tuple[int, int]:
        scaled = value.numerator * scale
        return (
            scaled // value.denominator,
            ceiling_division(scaled, value.denominator),
        )

    def subtract(
        left: tuple[int, int],
        right: tuple[int, int],
    ) -> tuple[int, int]:
        return left[0] - right[1], left[1] - right[0]

    def multiply(
        left: tuple[int, int],
        right: tuple[int, int],
    ) -> tuple[int, int]:
        left_lower, left_upper = left
        right_lower, right_upper = right
        if left_lower >= 0:
            if right_lower >= 0:
                return (
                    (left_lower * right_lower) // scale,
                    ceiling_division(
                        left_upper * right_upper,
                        scale,
                    ),
                )
            if right_upper <= 0:
                return (
                    (left_upper * right_lower) // scale,
                    ceiling_division(
                        left_lower * right_upper,
                        scale,
                    ),
                )
        elif left_upper <= 0:
            if right_lower >= 0:
                return (
                    (left_lower * right_upper) // scale,
                    ceiling_division(
                        left_upper * right_lower,
                        scale,
                    ),
                )
            if right_upper <= 0:
                return (
                    (left_upper * right_upper) // scale,
                    ceiling_division(
                        left_lower * right_lower,
                        scale,
                    ),
                )
        products = (
            left_lower * right_lower,
            left_lower * right_upper,
            left_upper * right_lower,
            left_upper * right_upper,
        )
        return (
            min(products) // scale,
            ceiling_division(max(products), scale),
        )

    def divide(
        numerator: tuple[int, int],
        denominator: tuple[int, int],
    ) -> tuple[int, int]:
        lower, upper = numerator
        denominator_lower, denominator_upper = denominator
        if denominator_lower <= 0:
            raise CompactCertificateError(
                "interval Cholesky encountered a nonpositive divisor"
            )
        if lower >= 0:
            return (
                (lower * scale) // denominator_upper,
                ceiling_division(
                    upper * scale,
                    denominator_lower,
                ),
            )
        if upper <= 0:
            return (
                (lower * scale) // denominator_lower,
                ceiling_division(
                    upper * scale,
                    denominator_upper,
                ),
            )
        return (
            (lower * scale) // denominator_lower,
            ceiling_division(
                upper * scale,
                denominator_lower,
            ),
        )

    exact_intervals = [
        [interval(value) for value in row[: row_index + 1]]
        for row_index, row in enumerate(matrix)
    ]
    lower_factor: list[list[tuple[int, int] | None]] = [
        [None] * (row + 1)
        for row in range(dimension)
    ]
    for row in range(dimension):
        for column in range(row + 1):
            value = exact_intervals[row][column]
            for index in range(column):
                left = lower_factor[row][index]
                right = lower_factor[column][index]
                if left is None or right is None:
                    raise CompactCertificateError(
                        "interval Cholesky factor is incomplete"
                    )
                value = subtract(value, multiply(left, right))
            if row == column:
                if value[0] <= 0:
                    raise CompactCertificateError(
                        "interval Cholesky failed at pivot "
                        f"{row + 1}/{dimension}"
                    )
                lower = math.isqrt(value[0] * scale)
                upper_target = value[1] * scale
                upper = math.isqrt(upper_target)
                if upper * upper < upper_target:
                    upper += 1
                lower_factor[row][column] = (lower, upper)
            else:
                pivot = lower_factor[column][column]
                if pivot is None:
                    raise CompactCertificateError(
                        "interval Cholesky pivot is missing"
                    )
                lower_factor[row][column] = divide(value, pivot)


def _rigorous_positive_semidefinite_exact(
    matrix: Sequence[Sequence[Fraction]],
) -> None:
    dimension = len(matrix)
    if dimension == 0 or any(len(row) != dimension for row in matrix):
        raise CompactCertificateError(
            "exact PSD fallback requires a nonempty square matrix"
        )
    if any(
        matrix[row][column] != matrix[column][row]
        for row in range(dimension)
        for column in range(row + 1, dimension)
    ):
        raise CompactCertificateError(
            "exact PSD fallback requires a symmetric matrix"
        )
    if dimension > EXACT_PSD_FALLBACK_MAX_DIMENSION:
        raise CompactCertificateError(
            "exact PSD fallback dimension exceeds its resource limit"
        )
    maximum_input_bits = max(
        max(
            abs(value.numerator).bit_length(),
            value.denominator.bit_length(),
        )
        for row in matrix
        for value in row
    )
    if maximum_input_bits > EXACT_PSD_FALLBACK_MAX_INPUT_BITS:
        raise CompactCertificateError(
            "exact PSD fallback input exceeds its bit limit"
        )

    active = [list(row) for row in matrix]
    for pivot_index in range(dimension):
        selected: int | None = None
        for row in range(pivot_index, dimension):
            diagonal = active[row][row]
            if diagonal < ZERO:
                raise CompactCertificateError(
                    "exact PSD fallback found a negative pivot"
                )
            if diagonal == ZERO:
                if any(
                    active[row][column] != ZERO
                    for column in range(pivot_index, dimension)
                ):
                    raise CompactCertificateError(
                        "exact PSD fallback found a nonzero zero-diagonal row"
                    )
            elif selected is None:
                selected = row

        if selected is None:
            if any(
                active[row][column] != ZERO
                for row in range(pivot_index, dimension)
                for column in range(pivot_index, dimension)
            ):
                raise CompactCertificateError(
                    "exact PSD fallback found a nonzero zero-diagonal block"
                )
            return

        if selected != pivot_index:
            active[pivot_index], active[selected] = (
                active[selected],
                active[pivot_index],
            )
            for row in range(dimension):
                active[row][pivot_index], active[row][selected] = (
                    active[row][selected],
                    active[row][pivot_index],
                )

        pivot = active[pivot_index][pivot_index]
        for row in range(pivot_index + 1, dimension):
            for column in range(row, dimension):
                updated = (
                    active[row][column]
                    - active[row][pivot_index]
                    * active[column][pivot_index]
                    / pivot
                )
                if max(
                    abs(updated.numerator).bit_length(),
                    updated.denominator.bit_length(),
                ) > EXACT_PSD_FALLBACK_MAX_INTERMEDIATE_BITS:
                    raise CompactCertificateError(
                        "exact PSD fallback intermediate exceeds its bit limit"
                    )
                active[row][column] = updated
                active[column][row] = updated


def _rigorous_positive_semidefinite(
    matrix: Sequence[Sequence[Fraction]],
    *,
    precision_bits: int = POSITIVITY_PRECISION_BITS,
) -> bool:
    """Prove PSD, returning whether interval Cholesky proved strict positivity."""

    try:
        _rigorous_positive_definite(
            matrix,
            precision_bits=precision_bits,
        )
    except CompactCertificateError as interval_error:
        try:
            _rigorous_positive_semidefinite_exact(matrix)
        except CompactCertificateError as exact_error:
            raise CompactCertificateError(
                f"{interval_error}; {exact_error}"
            ) from exact_error
        return False
    return True


def _univariate_linear_combination(
    coefficients: Sequence[Fraction],
    basis: Sequence[Sequence[int | Fraction]],
) -> UnivariatePolynomial:
    if len(coefficients) != len(basis):
        raise CompactCertificateError(
            "univariate basis and coefficient lengths differ"
        )
    output: UnivariatePolynomial = (ZERO,)
    for coefficient, polynomial in zip(coefficients, basis):
        if coefficient:
            output = univariate_add(
                output,
                univariate_scale(polynomial, coefficient),
            )
    return output


def _trivariate_linear_form(
    coefficients: Sequence[Fraction],
    variable_index: int,
) -> TrivariatePolynomial:
    output: TrivariatePolynomial = {}
    for degree, coefficient in enumerate(coefficients):
        if not coefficient:
            continue
        exponent = [0, 0, 0]
        exponent[variable_index] = degree
        output[tuple(exponent)] = coefficient
    return output


def _gegenbauer_kernel(
    dimension: int,
    degree: int,
    first: Mapping[Sequence[int], int | Fraction],
    second: Mapping[Sequence[int], int | Fraction],
    third: Mapping[Sequence[int], int | Fraction],
) -> TrivariatePolynomial:
    """Return the exact Bachoc-Vallentin ``Q_k`` kernel."""

    basis = normalized_gegenbauer_basis(degree, dimension)
    polynomial = basis[degree]
    first_square = trivariate_power(first, 2)
    second_square = trivariate_power(second, 2)
    radial = trivariate_multiply(
        trivariate_subtract(trivariate_constant(1), first_square),
        trivariate_subtract(trivariate_constant(1), second_square),
    )
    mixed = trivariate_subtract(
        third,
        trivariate_multiply(first, second),
    )
    output: TrivariatePolynomial = {}
    radial_powers: dict[int, TrivariatePolynomial] = {}
    mixed_powers: dict[int, TrivariatePolynomial] = {}
    for power, coefficient in enumerate(polynomial):
        if coefficient == ZERO:
            continue
        difference = degree - power
        if difference < 0 or difference % 2:
            raise CompactCertificateError(
                "Gegenbauer polynomial has an invalid parity term"
            )
        radial_exponent = difference // 2
        if radial_exponent not in radial_powers:
            radial_powers[radial_exponent] = trivariate_power(
                radial,
                radial_exponent,
            )
        if power not in mixed_powers:
            mixed_powers[power] = trivariate_power(mixed, power)
        term = trivariate_multiply(
            radial_powers[radial_exponent],
            mixed_powers[power],
        )
        output = trivariate_add(
            output,
            trivariate_scale(term, coefficient),
        )
    return output


def _f_kernel_triplet(
    dimension: int,
    degree: int,
) -> tuple[
    TrivariatePolynomial,
    TrivariatePolynomial,
    TrivariatePolynomial,
]:
    u, v, t = (trivariate_variable(index) for index in range(3))
    return (
        _gegenbauer_kernel(dimension - 1, degree, u, v, t),
        _gegenbauer_kernel(dimension - 1, degree, t, u, v),
        _gegenbauer_kernel(dimension - 1, degree, t, v, u),
    )


def _contract_f_trivariate_column(
    kernels: tuple[
        TrivariatePolynomial,
        TrivariatePolynomial,
        TrivariatePolynomial,
    ],
    column: Sequence[Fraction],
) -> TrivariatePolynomial:
    q_uvt, q_tuv, q_tvu = kernels
    c_u = _trivariate_linear_form(column, 0)
    c_v = _trivariate_linear_form(column, 1)
    c_t = _trivariate_linear_form(column, 2)
    terms = (
        trivariate_multiply(
            q_uvt,
            trivariate_multiply(c_u, c_v),
        ),
        trivariate_multiply(
            q_tuv,
            trivariate_multiply(c_u, c_t),
        ),
        trivariate_multiply(
            q_tvu,
            trivariate_multiply(c_v, c_t),
        ),
    )
    output: TrivariatePolynomial = {}
    for term in terms:
        output = trivariate_add(output, term)
    return trivariate_scale(output, Fraction(1, 3))


def _f_trivariate_column(
    dimension: int,
    degree: int,
    column: Sequence[Fraction],
) -> TrivariatePolynomial:
    """Contract one original-coordinate LDL column with ``S_k^d``."""

    return _contract_f_trivariate_column(
        _f_kernel_triplet(dimension, degree),
        column,
    )


def _invariant_from_values(
    exponents: Sequence[tuple[int, int, int]],
    values: Sequence[Fraction],
) -> InvariantPolynomial:
    if len(exponents) != len(values):
        raise CompactCertificateError(
            "invariant basis and coefficient lengths differ"
        )
    return {
        exponent: value
        for exponent, value in zip(exponents, values)
        if value
    }


class _CertificateAccumulator:
    def __init__(self, parameters: CompactCertificateParameters) -> None:
        self.parameters = parameters
        self.objective = ONE
        self.univariate: UnivariatePolynomial = (ONE,)
        self.trivariate_f: TrivariatePolynomial = {}
        self.trivariate_sos: InvariantPolynomial = {}
        self.positive_definite_block_count = 0
        self.positive_semidefinite_block_count = 0
        self.exact_psd_fallback_block_count = 0
        self.gegenbauer = normalized_gegenbauer_basis(
            2 * parameters.degree,
            parameters.dimension,
        )
        self.chebyshev = chebyshev_basis(parameters.degree)
        self.interval_weight = univariate_multiply(
            (ONE, ONE),
            (parameters.cos_theta, -ONE),
        )
        self.f_kernels: dict[
            int,
            tuple[
                TrivariatePolynomial,
                TrivariatePolynomial,
                TrivariatePolynomial,
            ],
        ] = {}
        self.sos_kernels = self._build_sos_kernels()

    def _build_sos_kernels(
        self,
    ) -> dict[
        tuple[int, int],
        tuple[tuple[InvariantPolynomial, ...], ...],
    ]:
        weights = tuple(
            reduce_symmetric_polynomial(weight)
            for weight in domain_weights(self.parameters.cos_theta)
        )
        kernels = representation_kernels()
        representation_matrices = {
            1: kernels["trivial"],
            2: kernels["alternating"],
            3: kernels["standard"],
        }
        output = {}
        for weight_index, weight in enumerate(weights, start=1):
            for representation_index, matrix in representation_matrices.items():
                output[(weight_index, representation_index)] = tuple(
                    tuple(
                        _invariant_multiply(
                            weight,
                            reduce_symmetric_polynomial(entry),
                        )
                        for entry in row
                    )
                    for row in matrix
                )
        return output

    def consume(self, block: MatrixBlock) -> None:
        matrix = _matrix_from_block(block)
        try:
            strictly_positive = _rigorous_positive_semidefinite(matrix)
        except CompactCertificateError as exc:
            raise CompactCertificateError(f"{block.name}: {exc}") from exc
        self.positive_semidefinite_block_count += 1
        if strictly_positive:
            self.positive_definite_block_count += 1
        else:
            self.exact_psd_fallback_block_count += 1
        if block.name.startswith("F/"):
            self._consume_f(block, matrix)
        elif block.name.startswith("a/"):
            self._consume_a(block, matrix)
        elif block.name == "univariatesos/1":
            self._consume_univariate_sos(
                block,
                weighted=False,
                matrix=matrix,
            )
        elif block.name == "univariatesos/2":
            self._consume_univariate_sos(
                block,
                weighted=True,
                matrix=matrix,
            )
        elif block.name.startswith("trivariatesos/"):
            self._consume_trivariate_sos(block, matrix)
        else:
            raise CompactCertificateError(
                f"unexpected canonical block name: {block.name}"
            )

    def _consume_f(
        self,
        block: LDLBlock | MatrixBlock,
        matrix: tuple[tuple[Fraction, ...], ...] | None = None,
    ) -> None:
        degree = int(block.name.split("/")[1])
        expected_dimension = self.parameters.degree - degree + 1
        if block.dimension != expected_dimension:
            raise CompactCertificateError(
                f"{block.name}: incorrect F-block dimension"
            )
        if matrix is None:
            matrix = _matrix_from_block(block)
        radial = univariate_power((ONE, ZERO, -ONE), degree)
        if any(any(row) for row in matrix) and degree not in self.f_kernels:
            self.f_kernels[degree] = _f_kernel_triplet(
                self.parameters.dimension,
                degree,
            )
        quadratic = _monomial_quadratic_form(matrix)
        if degree == 0:
            univariate_contribution = univariate_add(
                quadratic,
                tuple(2 * value for value in _matrix_row_sums(matrix)),
            )
            self.objective += _matrix_entry_sum(matrix)
        else:
            univariate_contribution = univariate_multiply(
                radial,
                quadratic,
            )
        self.univariate = univariate_add(
            self.univariate,
            univariate_contribution,
        )
        if degree in self.f_kernels:
            q_uvt, q_tuv, q_tvu = self.f_kernels[degree]
            contribution: TrivariatePolynomial = {}
            for kernel, variables in (
                (q_uvt, (0, 1)),
                (q_tuv, (2, 0)),
                (q_tvu, (2, 1)),
            ):
                contribution = trivariate_add(
                    contribution,
                    trivariate_multiply(
                        kernel,
                        _matrix_bivariate_form(
                            matrix,
                            variables[0],
                            variables[1],
                        ),
                    ),
                )
            self.trivariate_f = trivariate_add(
                self.trivariate_f,
                trivariate_scale(contribution, Fraction(1, 3)),
            )

    def _consume_a(
        self,
        block: LDLBlock | MatrixBlock,
        matrix: tuple[tuple[Fraction, ...], ...] | None = None,
    ) -> None:
        degree = int(block.name.split("/")[1])
        if block.dimension != 1 or degree > 2 * self.parameters.degree:
            raise CompactCertificateError(
                f"{block.name}: incorrect scalar block"
            )
        if matrix is None:
            matrix = _matrix_from_block(block)
        value = matrix[0][0]
        self.objective += value
        self.univariate = univariate_add(
            self.univariate,
            univariate_scale(self.gegenbauer[degree], value),
        )

    def _consume_univariate_sos(
        self,
        block: LDLBlock | MatrixBlock,
        *,
        weighted: bool,
        matrix: tuple[tuple[Fraction, ...], ...] | None = None,
    ) -> None:
        basis = (
            self.chebyshev[: self.parameters.degree]
            if weighted
            else self.chebyshev
        )
        if block.dimension != len(basis):
            raise CompactCertificateError(
                f"{block.name}: incorrect univariate SOS dimension"
            )
        if matrix is None:
            matrix = _matrix_from_block(block)
        contribution = _univariate_quadratic_form(matrix, basis)
        if weighted:
            contribution = univariate_multiply(
                self.interval_weight,
                contribution,
            )
        self.univariate = univariate_add(
            self.univariate,
            contribution,
        )

    def _consume_trivariate_sos(
        self,
        block: LDLBlock | MatrixBlock,
        matrix: tuple[tuple[Fraction, ...], ...] | None = None,
    ) -> None:
        _, raw_weight, raw_representation = block.name.split("/")
        weight_index = int(raw_weight)
        representation_index = int(raw_representation)
        components = _sos_component_exponents(
            self.parameters.degree,
            weight_index,
            representation_index,
        )
        expected_dimension = sum(len(component) for component in components)
        if block.dimension != expected_dimension or not expected_dimension:
            raise CompactCertificateError(
                f"{block.name}: incorrect three-point SOS dimension"
            )
        if matrix is None:
            matrix = _matrix_from_block(block)
        kernels = self.sos_kernels[(weight_index, representation_index)]
        coordinates = [
            (component_index, exponent)
            for component_index, exponents in enumerate(components)
            for exponent in exponents
        ]
        if len(coordinates) != block.dimension:
            raise CompactCertificateError(
                f"{block.name}: component partition is incomplete"
            )
        for row, column, value in _symmetric_entries(matrix):
            left_component, left_exponent = coordinates[row]
            right_component, right_exponent = coordinates[column]
            _invariant_add_shifted_scaled(
                self.trivariate_sos,
                kernels[left_component][right_component],
                (
                    left_exponent[0] + right_exponent[0],
                    left_exponent[1] + right_exponent[1],
                    left_exponent[2] + right_exponent[2],
                ),
                value,
            )

    def finish(
        self,
        witness: WitnessReport,
    ) -> CompactCertificateReport:
        if self.positive_semidefinite_block_count != witness.block_count:
            raise CompactCertificateError(
                "not every direct matrix block passed exact PSD verification"
            )
        maximum_degree = 2 * self.parameters.degree
        if len(self.univariate) > maximum_degree + 1:
            raise CompactCertificateError(
                "univariate identity exceeds its certified degree"
            )
        if self.objective != self.parameters.target_objective:
            raise CompactCertificateError(
                "objective mismatch: expected "
                f"{_rational_token(self.parameters.target_objective)}, "
                f"received {_rational_token(self.objective)}"
            )
        if self.univariate != (ZERO,):
            nonzero_degree = next(
                index
                for index, coefficient in enumerate(self.univariate)
                if coefficient
            )
            raise CompactCertificateError(
                "univariate identity failed at coefficient "
                f"w^{nonzero_degree}: "
                f"{_rational_token(self.univariate[nonzero_degree])}"
            )
        if self.trivariate_f:
            if trivariate_total_degree(self.trivariate_f) > maximum_degree:
                raise CompactCertificateError(
                    "three-point F identity exceeds its certified degree"
                )
            if not trivariate_is_symmetric(self.trivariate_f):
                raise CompactCertificateError(
                    "three-point F contribution is not symmetric"
                )
            _invariant_add_scaled(
                self.trivariate_sos,
                reduce_symmetric_polynomial(self.trivariate_f),
            )
        invalid_degrees = [
            exponent
            for exponent in self.trivariate_sos
            if exponent[0] + 2 * exponent[1] + 3 * exponent[2]
            > maximum_degree
        ]
        if invalid_degrees:
            raise CompactCertificateError(
                "three-point identity exceeds its certified degree"
            )
        if self.trivariate_sos:
            exponent = min(
                self.trivariate_sos,
                key=lambda value: (
                    value[0] + 2 * value[1] + 3 * value[2],
                    value,
                ),
            )
            raise CompactCertificateError(
                "three-point identity failed at coefficient "
                f"e1^{exponent[0]} e2^{exponent[1]} e3^{exponent[2]}: "
                f"{_rational_token(self.trivariate_sos[exponent])}"
            )
        return CompactCertificateReport(
            dimension=self.parameters.dimension,
            degree=self.parameters.degree,
            cos_theta=self.parameters.cos_theta,
            target_objective=self.parameters.target_objective,
            objective_value=self.objective,
            positive_definite_block_count=(
                self.positive_definite_block_count
            ),
            positive_semidefinite_block_count=(
                self.positive_semidefinite_block_count
            ),
            exact_psd_fallback_block_count=(
                self.exact_psd_fallback_block_count
            ),
            positivity_precision_bits=POSITIVITY_PRECISION_BITS,
            univariate_coefficient_count=maximum_degree + 1,
            trivariate_coefficient_count=len(
                elementary_symmetric_exponents(maximum_degree)
            ),
            witness=witness,
        )


class CompactCertificateReplay:
    """Consume one parsed witness stream and finish its coefficient replay."""

    def __init__(
        self,
        *,
        dimension: int,
        degree: int,
        cos_theta: int | Fraction,
        target_objective: int | Fraction,
    ) -> None:
        self.parameters = _parameters(
            dimension,
            degree,
            cos_theta,
            target_objective,
        )
        self.layout = canonical_block_layout(self.parameters.degree)
        self._accumulator = _CertificateAccumulator(self.parameters)

    def consume(self, block: MatrixBlock) -> None:
        self._accumulator.consume(block)

    def finish(self, witness: WitnessReport) -> CompactCertificateReport:
        return self._accumulator.finish(witness)


def verify_compact_certificate(
    path: str | Path,
    *,
    dimension: int,
    degree: int,
    cos_theta: int | Fraction,
    target_objective: int | Fraction,
    limits: WitnessLimits = DEFAULT_LIMITS,
) -> CompactCertificateReport:
    """Verify one exact compact certificate for ``d2=d3=degree``."""

    replay = CompactCertificateReplay(
        dimension=dimension,
        degree=degree,
        cos_theta=cos_theta,
        target_objective=target_objective,
    )
    try:
        witness = read_compact_witness(
            path,
            replay.layout,
            consumer=replay.consume,
            limits=limits,
        )
    except CompactWitnessError as exc:
        raise CompactCertificateError(str(exc)) from exc
    return replay.finish(witness)


def verify_compact_certificate_bytes(
    data: bytes,
    *,
    dimension: int,
    degree: int,
    cos_theta: int | Fraction,
    target_objective: int | Fraction,
    limits: WitnessLimits = DEFAULT_LIMITS,
) -> CompactCertificateReport:
    """Verify one exact compact certificate from immutable witness bytes."""

    replay = CompactCertificateReplay(
        dimension=dimension,
        degree=degree,
        cos_theta=cos_theta,
        target_objective=target_objective,
    )
    try:
        witness = read_compact_witness_bytes(
            data,
            replay.layout,
            consumer=replay.consume,
            limits=limits,
        )
    except CompactWitnessError as exc:
        raise CompactCertificateError(str(exc)) from exc
    return replay.finish(witness)


def verify_kn11_compact_certificate(
    path: str | Path,
    *,
    limits: WitnessLimits = DEFAULT_LIMITS,
) -> CompactCertificateReport:
    """Verify the intended dimension-11, degree-17 target certificate."""

    return verify_compact_certificate(
        path,
        dimension=11,
        degree=17,
        cos_theta=Fraction(1, 2),
        target_objective=Fraction(86899, 100),
        limits=limits,
    )


def verify_kn11_compact_certificate_bytes(
    data: bytes,
    *,
    limits: WitnessLimits = DEFAULT_LIMITS,
) -> CompactCertificateReport:
    """Verify the intended target from one immutable witness byte string."""

    return verify_compact_certificate_bytes(
        data,
        dimension=11,
        degree=17,
        cos_theta=Fraction(1, 2),
        target_objective=Fraction(86899, 100),
        limits=limits,
    )


__all__ = [
    "CompactCertificateError",
    "CompactCertificateParameters",
    "CompactCertificateReplay",
    "CompactCertificateReport",
    "canonical_block_layout",
    "verify_compact_certificate",
    "verify_compact_certificate_bytes",
    "verify_kn11_compact_certificate",
    "verify_kn11_compact_certificate_bytes",
]
