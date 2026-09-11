"""Exact polynomial formulation utilities for the Project 10 verifier."""

from __future__ import annotations

from fractions import Fraction
from itertools import permutations
from typing import Iterable, Mapping, Sequence, Tuple, Union


ExactScalar = Union[int, Fraction]
UnivariatePolynomial = Tuple[Fraction, ...]
TrivariateExponent = Tuple[int, int, int]
TrivariatePolynomial = dict[TrivariateExponent, Fraction]
InvariantExponent = Tuple[int, int, int]
InvariantPolynomial = dict[InvariantExponent, Fraction]
PolynomialMatrix = Tuple[Tuple[TrivariatePolynomial, ...], ...]

ZERO = Fraction(0)
ONE = Fraction(1)
_TRIVARIATE_ZERO = (0, 0, 0)
_PERMUTATIONS = tuple(permutations(range(3)))


def _fraction(value: ExactScalar) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, Fraction)):
        raise TypeError("coefficients and evaluation points must be exact rationals")
    return Fraction(value)


def _nonnegative_integer(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _normalize_univariate(
    coefficients: Iterable[ExactScalar],
) -> UnivariatePolynomial:
    output = [_fraction(value) for value in coefficients]
    while len(output) > 1 and output[-1] == ZERO:
        output.pop()
    return tuple(output) if output else (ZERO,)


def univariate_add(
    left: Sequence[ExactScalar],
    right: Sequence[ExactScalar],
) -> UnivariatePolynomial:
    """Add two coefficient vectors stored in ascending degree order."""

    left_polynomial = _normalize_univariate(left)
    right_polynomial = _normalize_univariate(right)
    size = max(len(left_polynomial), len(right_polynomial))
    return _normalize_univariate(
        (
            left_polynomial[index] if index < len(left_polynomial) else ZERO
        )
        + (
            right_polynomial[index] if index < len(right_polynomial) else ZERO
        )
        for index in range(size)
    )


def univariate_scale(
    polynomial: Sequence[ExactScalar],
    scalar: ExactScalar,
) -> UnivariatePolynomial:
    """Multiply a univariate polynomial by an exact scalar."""

    factor = _fraction(scalar)
    return _normalize_univariate(
        factor * coefficient for coefficient in _normalize_univariate(polynomial)
    )


def univariate_multiply(
    left: Sequence[ExactScalar],
    right: Sequence[ExactScalar],
) -> UnivariatePolynomial:
    """Multiply two univariate polynomials exactly."""

    left_polynomial = _normalize_univariate(left)
    right_polynomial = _normalize_univariate(right)
    if left_polynomial == (ZERO,) or right_polynomial == (ZERO,):
        return (ZERO,)
    output = [ZERO] * (len(left_polynomial) + len(right_polynomial) - 1)
    for left_degree, left_coefficient in enumerate(left_polynomial):
        for right_degree, right_coefficient in enumerate(right_polynomial):
            output[left_degree + right_degree] += (
                left_coefficient * right_coefficient
            )
    return _normalize_univariate(output)


def univariate_power(
    polynomial: Sequence[ExactScalar],
    exponent: int,
) -> UnivariatePolynomial:
    """Raise a univariate polynomial to a nonnegative integer power."""

    power = _nonnegative_integer(exponent, "exponent")
    result = (ONE,)
    factor = _normalize_univariate(polynomial)
    while power:
        if power & 1:
            result = univariate_multiply(result, factor)
        power >>= 1
        if power:
            factor = univariate_multiply(factor, factor)
    return result


def univariate_evaluate(
    polynomial: Sequence[ExactScalar],
    value: ExactScalar,
) -> Fraction:
    """Evaluate a univariate polynomial by exact Horner arithmetic."""

    point = _fraction(value)
    result = ZERO
    for coefficient in reversed(_normalize_univariate(polynomial)):
        result = result * point + coefficient
    return result


def chebyshev_basis(max_degree: int) -> Tuple[UnivariatePolynomial, ...]:
    """Return first-kind Chebyshev polynomials through ``max_degree``."""

    degree = _nonnegative_integer(max_degree, "max_degree")
    basis = [(ONE,)]
    if degree == 0:
        return tuple(basis)
    basis.append((ZERO, ONE))
    for current_degree in range(2, degree + 1):
        twice_x_previous = univariate_scale(
            (ZERO,) + basis[current_degree - 1],
            2,
        )
        basis.append(
            univariate_add(
                twice_x_previous,
                univariate_scale(basis[current_degree - 2], -1),
            )
        )
    return tuple(basis)


def normalized_gegenbauer_basis(
    max_degree: int,
    dimension: int,
) -> Tuple[UnivariatePolynomial, ...]:
    """Return Gegenbauer polynomials normalized by ``P_k(1) = 1``.

    ``dimension`` is the spherical-code dimension. The recurrence uses
    Gegenbauer parameter ``dimension / 2 - 1`` and remains valid in
    dimension 2, where it reduces to the first-kind Chebyshev basis.
    """

    degree = _nonnegative_integer(max_degree, "max_degree")
    if isinstance(dimension, bool) or not isinstance(dimension, int):
        raise ValueError("dimension must be an integer")
    if dimension < 2:
        raise ValueError("dimension must be at least 2")
    basis = [(ONE,)]
    if degree == 0:
        return tuple(basis)
    basis.append((ZERO, ONE))
    for current_degree in range(2, degree + 1):
        denominator = current_degree + dimension - 3
        x_previous = (ZERO,) + basis[current_degree - 1]
        first = univariate_scale(
            x_previous,
            Fraction(2 * current_degree + dimension - 4, denominator),
        )
        second = univariate_scale(
            basis[current_degree - 2],
            Fraction(-(current_degree - 1), denominator),
        )
        basis.append(univariate_add(first, second))
    return tuple(basis)


def _validate_trivariate_exponent(
    exponent: Sequence[int],
) -> TrivariateExponent:
    if len(exponent) != 3:
        raise ValueError("a trivariate exponent must have three entries")
    output = tuple(
        _nonnegative_integer(value, "trivariate exponent") for value in exponent
    )
    return output[0], output[1], output[2]


def trivariate_polynomial(
    terms: Mapping[Sequence[int], ExactScalar],
) -> TrivariatePolynomial:
    """Canonicalize a sparse trivariate polynomial."""

    output: TrivariatePolynomial = {}
    for raw_exponent, raw_coefficient in terms.items():
        exponent = _validate_trivariate_exponent(raw_exponent)
        coefficient = _fraction(raw_coefficient)
        if coefficient != ZERO:
            output[exponent] = output.get(exponent, ZERO) + coefficient
            if output[exponent] == ZERO:
                del output[exponent]
    return output


def trivariate_constant(value: ExactScalar) -> TrivariatePolynomial:
    """Construct a constant trivariate polynomial."""

    coefficient = _fraction(value)
    return {} if coefficient == ZERO else {_TRIVARIATE_ZERO: coefficient}


def trivariate_variable(index: int) -> TrivariatePolynomial:
    """Return variable 0, 1, or 2, corresponding to ``u``, ``v``, or ``t``."""

    if isinstance(index, bool) or not isinstance(index, int) or index not in range(3):
        raise ValueError("variable index must be 0, 1, or 2")
    exponent = [0, 0, 0]
    exponent[index] = 1
    return {tuple(exponent): ONE}  # type: ignore[dict-item]


def trivariate_add(
    left: Mapping[Sequence[int], ExactScalar],
    right: Mapping[Sequence[int], ExactScalar],
) -> TrivariatePolynomial:
    """Add two sparse trivariate polynomials."""

    output = trivariate_polynomial(left)
    for exponent, coefficient in trivariate_polynomial(right).items():
        output[exponent] = output.get(exponent, ZERO) + coefficient
        if output[exponent] == ZERO:
            del output[exponent]
    return output


def trivariate_scale(
    polynomial: Mapping[Sequence[int], ExactScalar],
    scalar: ExactScalar,
) -> TrivariatePolynomial:
    """Multiply a sparse trivariate polynomial by an exact scalar."""

    factor = _fraction(scalar)
    if factor == ZERO:
        return {}
    return {
        exponent: factor * coefficient
        for exponent, coefficient in trivariate_polynomial(polynomial).items()
    }


def trivariate_subtract(
    left: Mapping[Sequence[int], ExactScalar],
    right: Mapping[Sequence[int], ExactScalar],
) -> TrivariatePolynomial:
    """Subtract two sparse trivariate polynomials."""

    return trivariate_add(left, trivariate_scale(right, -1))


def trivariate_multiply(
    left: Mapping[Sequence[int], ExactScalar],
    right: Mapping[Sequence[int], ExactScalar],
) -> TrivariatePolynomial:
    """Multiply two sparse trivariate polynomials exactly."""

    left_polynomial = trivariate_polynomial(left)
    right_polynomial = trivariate_polynomial(right)
    if not left_polynomial or not right_polynomial:
        return {}
    output: TrivariatePolynomial = {}
    for left_exponent, left_coefficient in left_polynomial.items():
        for right_exponent, right_coefficient in right_polynomial.items():
            exponent = (
                left_exponent[0] + right_exponent[0],
                left_exponent[1] + right_exponent[1],
                left_exponent[2] + right_exponent[2],
            )
            output[exponent] = output.get(exponent, ZERO) + (
                left_coefficient * right_coefficient
            )
            if output[exponent] == ZERO:
                del output[exponent]
    return output


def trivariate_power(
    polynomial: Mapping[Sequence[int], ExactScalar],
    exponent: int,
) -> TrivariatePolynomial:
    """Raise a sparse trivariate polynomial to a nonnegative integer power."""

    power = _nonnegative_integer(exponent, "exponent")
    result = trivariate_constant(1)
    factor = trivariate_polynomial(polynomial)
    while power:
        if power & 1:
            result = trivariate_multiply(result, factor)
        power >>= 1
        if power:
            factor = trivariate_multiply(factor, factor)
    return result


def trivariate_evaluate(
    polynomial: Mapping[Sequence[int], ExactScalar],
    values: Sequence[ExactScalar],
) -> Fraction:
    """Evaluate a sparse trivariate polynomial exactly."""

    if len(values) != 3:
        raise ValueError("trivariate evaluation requires three values")
    points = tuple(_fraction(value) for value in values)
    return sum(
        (
            coefficient
            * points[0] ** exponent[0]
            * points[1] ** exponent[1]
            * points[2] ** exponent[2]
            for exponent, coefficient in trivariate_polynomial(polynomial).items()
        ),
        ZERO,
    )


def trivariate_total_degree(
    polynomial: Mapping[Sequence[int], ExactScalar],
) -> int:
    """Return total degree, with degree -1 for the zero polynomial."""

    normalized = trivariate_polynomial(polynomial)
    return max((sum(exponent) for exponent in normalized), default=-1)


def trivariate_permute(
    polynomial: Mapping[Sequence[int], ExactScalar],
    permutation: Sequence[int],
) -> TrivariatePolynomial:
    """Rename variables according to a permutation of ``(0, 1, 2)``."""

    if tuple(sorted(permutation)) != (0, 1, 2):
        raise ValueError("permutation must contain 0, 1, and 2 exactly once")
    return trivariate_polynomial(
        {
            tuple(exponent[index] for index in permutation): coefficient
            for exponent, coefficient in trivariate_polynomial(polynomial).items()
        }
    )


def trivariate_is_symmetric(
    polynomial: Mapping[Sequence[int], ExactScalar],
) -> bool:
    """Return whether a polynomial is invariant under every variable permutation."""

    normalized = trivariate_polynomial(polynomial)
    return all(
        trivariate_permute(normalized, permutation) == normalized
        for permutation in _PERMUTATIONS
    )


def elementary_symmetric_polynomials(
) -> Tuple[TrivariatePolynomial, TrivariatePolynomial, TrivariatePolynomial]:
    """Return ``e1 = u+v+t``, ``e2 = uv+ut+vt``, and ``e3 = uvt``."""

    e1 = {
        (1, 0, 0): ONE,
        (0, 1, 0): ONE,
        (0, 0, 1): ONE,
    }
    e2 = {
        (1, 1, 0): ONE,
        (1, 0, 1): ONE,
        (0, 1, 1): ONE,
    }
    e3 = {(1, 1, 1): ONE}
    return e1, e2, e3


def elementary_symmetric_exponents(
    max_degree: int,
) -> Tuple[InvariantExponent, ...]:
    """Enumerate ``e1^a e2^b e3^c`` by weighted total degree."""

    degree_limit = _nonnegative_integer(max_degree, "max_degree")
    output = []
    for degree in range(degree_limit + 1):
        for c_exponent in range(degree // 3 + 1):
            for b_exponent in range((degree - 3 * c_exponent) // 2 + 1):
                a_exponent = degree - 3 * c_exponent - 2 * b_exponent
                output.append((a_exponent, b_exponent, c_exponent))
    return tuple(output)


def _normalize_invariant(
    coefficients: Mapping[Sequence[int], ExactScalar],
) -> InvariantPolynomial:
    output: InvariantPolynomial = {}
    for raw_exponent, raw_coefficient in coefficients.items():
        exponent = _validate_trivariate_exponent(raw_exponent)
        coefficient = _fraction(raw_coefficient)
        if coefficient != ZERO:
            output[exponent] = output.get(exponent, ZERO) + coefficient
            if output[exponent] == ZERO:
                del output[exponent]
    return output


def expand_elementary_symmetric(
    coefficients: Mapping[Sequence[int], ExactScalar],
) -> TrivariatePolynomial:
    """Expand a sparse polynomial in ``e1``, ``e2``, and ``e3`` into ``u,v,t``."""

    invariant = _normalize_invariant(coefficients)
    e1, e2, e3 = elementary_symmetric_polynomials()
    generators = (e1, e2, e3)
    power_cache: dict[Tuple[int, int], TrivariatePolynomial] = {}

    def generator_power(index: int, exponent: int) -> TrivariatePolynomial:
        key = (index, exponent)
        if key not in power_cache:
            power_cache[key] = trivariate_power(generators[index], exponent)
        return power_cache[key]

    output: TrivariatePolynomial = {}
    for exponent, coefficient in invariant.items():
        term = trivariate_constant(coefficient)
        for index, power in enumerate(exponent):
            term = trivariate_multiply(term, generator_power(index, power))
        output = trivariate_add(output, term)
    return output


def reduce_symmetric_polynomial(
    polynomial: Mapping[Sequence[int], ExactScalar],
) -> InvariantPolynomial:
    """Reduce an ``S_3``-symmetric polynomial to the elementary basis.

    Lexicographic leading terms make the conversion triangular:
    ``e1^a e2^b e3^c`` has leading monomial
    ``u^(a+b+c) v^(b+c) t^c`` with coefficient one.
    """

    residual = trivariate_polynomial(polynomial)
    if not trivariate_is_symmetric(residual):
        raise ValueError("polynomial is not symmetric in u, v, and t")
    output: InvariantPolynomial = {}
    expansion_cache: dict[InvariantExponent, TrivariatePolynomial] = {}
    while residual:
        leading_exponent = max(residual)
        u_exponent, v_exponent, t_exponent = leading_exponent
        if u_exponent < v_exponent or v_exponent < t_exponent:
            raise ArithmeticError("symmetric reduction lost triangular order")
        invariant_exponent = (
            u_exponent - v_exponent,
            v_exponent - t_exponent,
            t_exponent,
        )
        coefficient = residual[leading_exponent]
        output[invariant_exponent] = (
            output.get(invariant_exponent, ZERO) + coefficient
        )
        if output[invariant_exponent] == ZERO:
            del output[invariant_exponent]
        if invariant_exponent not in expansion_cache:
            expansion_cache[invariant_exponent] = expand_elementary_symmetric(
                {invariant_exponent: ONE}
            )
        residual = trivariate_subtract(
            residual,
            trivariate_scale(
                expansion_cache[invariant_exponent],
                coefficient,
            ),
        )
    return output


def evaluate_elementary_symmetric(
    coefficients: Mapping[Sequence[int], ExactScalar],
    values: Sequence[ExactScalar],
) -> Fraction:
    """Evaluate an elementary-basis polynomial at exact ``u,v,t`` values."""

    if len(values) != 3:
        raise ValueError("trivariate evaluation requires three values")
    u_value, v_value, t_value = (_fraction(value) for value in values)
    elementary_values = (
        u_value + v_value + t_value,
        u_value * v_value + u_value * t_value + v_value * t_value,
        u_value * v_value * t_value,
    )
    return sum(
        (
            coefficient
            * elementary_values[0] ** exponent[0]
            * elementary_values[1] ** exponent[1]
            * elementary_values[2] ** exponent[2]
            for exponent, coefficient in _normalize_invariant(
                coefficients
            ).items()
        ),
        ZERO,
    )


def invariant_total_degree(
    coefficients: Mapping[Sequence[int], ExactScalar],
) -> int:
    """Return weighted degree in ``e1``, ``e2``, and ``e3``."""

    invariant = _normalize_invariant(coefficients)
    return max(
        (
            exponent[0] + 2 * exponent[1] + 3 * exponent[2]
            for exponent in invariant
        ),
        default=-1,
    )


def interval_weight(
    variable: Mapping[Sequence[int], ExactScalar],
    lower: ExactScalar = -1,
    upper: ExactScalar = Fraction(1, 2),
) -> TrivariatePolynomial:
    """Return ``(variable-lower) * (upper-variable)`` exactly."""

    lower_value = _fraction(lower)
    upper_value = _fraction(upper)
    if lower_value >= upper_value:
        raise ValueError("interval lower endpoint must be less than upper endpoint")
    normalized = trivariate_polynomial(variable)
    return trivariate_multiply(
        trivariate_add(normalized, trivariate_constant(-lower_value)),
        trivariate_subtract(trivariate_constant(upper_value), normalized),
    )


def domain_weights(
    cos_theta: ExactScalar = Fraction(1, 2),
    lower: ExactScalar = -1,
) -> Tuple[TrivariatePolynomial, ...]:
    """Derive the five symmetric weights for the three-point domain."""

    upper_value = _fraction(cos_theta)
    lower_value = _fraction(lower)
    u, v, t = (trivariate_variable(index) for index in range(3))
    intervals = tuple(
        interval_weight(variable, lower_value, upper_value)
        for variable in (u, v, t)
    )
    first = trivariate_constant(1)
    second = trivariate_add(
        trivariate_add(intervals[0], intervals[1]),
        intervals[2],
    )
    third = trivariate_add(
        trivariate_add(
            trivariate_multiply(intervals[0], intervals[1]),
            trivariate_multiply(intervals[0], intervals[2]),
        ),
        trivariate_multiply(intervals[1], intervals[2]),
    )
    fourth = trivariate_multiply(
        trivariate_multiply(intervals[0], intervals[1]),
        intervals[2],
    )
    fifth = trivariate_add(
        trivariate_constant(1),
        trivariate_add(
            trivariate_scale(trivariate_multiply(trivariate_multiply(u, v), t), 2),
            trivariate_scale(
                trivariate_add(
                    trivariate_add(
                        trivariate_power(u, 2),
                        trivariate_power(v, 2),
                    ),
                    trivariate_power(t, 2),
                ),
                -1,
            ),
        ),
    )
    return first, second, third, fourth, fifth


def trivial_representation_kernel() -> PolynomialMatrix:
    """Return the one-dimensional trivial representation kernel."""

    return ((trivariate_constant(1),),)


def alternating_representation_kernel() -> PolynomialMatrix:
    """Return the squared alternating representation kernel."""

    u, v, t = (trivariate_variable(index) for index in range(3))
    alternating = trivariate_multiply(
        trivariate_multiply(
            trivariate_subtract(u, v),
            trivariate_subtract(v, t),
        ),
        trivariate_subtract(t, u),
    )
    return ((trivariate_power(alternating, 2),),)


def standard_representation_kernel() -> PolynomialMatrix:
    """Return the exact 2 by 2 standard representation kernel."""

    u, v, t = (trivariate_variable(index) for index in range(3))
    first_row = (
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
    )
    second_row = (
        trivariate_subtract(v, t),
        trivariate_subtract(
            trivariate_multiply(u, t),
            trivariate_multiply(u, v),
        ),
    )
    output = []
    for left_index in range(2):
        row = []
        for right_index in range(2):
            row.append(
                trivariate_add(
                    trivariate_scale(
                        trivariate_multiply(
                            first_row[left_index],
                            first_row[right_index],
                        ),
                        Fraction(1, 2),
                    ),
                    trivariate_scale(
                        trivariate_multiply(
                            second_row[left_index],
                            second_row[right_index],
                        ),
                        Fraction(3, 2),
                    ),
                )
            )
        output.append(tuple(row))
    return tuple(output)


def representation_kernels() -> dict[str, PolynomialMatrix]:
    """Return all three canonical ``S_3`` representation kernels."""

    return {
        "trivial": trivial_representation_kernel(),
        "alternating": alternating_representation_kernel(),
        "standard": standard_representation_kernel(),
    }


__all__ = [
    "InvariantPolynomial",
    "PolynomialMatrix",
    "TrivariatePolynomial",
    "UnivariatePolynomial",
    "alternating_representation_kernel",
    "chebyshev_basis",
    "domain_weights",
    "elementary_symmetric_exponents",
    "elementary_symmetric_polynomials",
    "evaluate_elementary_symmetric",
    "expand_elementary_symmetric",
    "interval_weight",
    "invariant_total_degree",
    "normalized_gegenbauer_basis",
    "reduce_symmetric_polynomial",
    "representation_kernels",
    "standard_representation_kernel",
    "trivial_representation_kernel",
    "trivariate_add",
    "trivariate_constant",
    "trivariate_evaluate",
    "trivariate_is_symmetric",
    "trivariate_multiply",
    "trivariate_permute",
    "trivariate_polynomial",
    "trivariate_power",
    "trivariate_scale",
    "trivariate_subtract",
    "trivariate_total_degree",
    "trivariate_variable",
    "univariate_add",
    "univariate_evaluate",
    "univariate_multiply",
    "univariate_power",
    "univariate_scale",
]
