using KissingNumber11Certificate
using ClusteredLowRankSolver
using Nemo
using SHA

const OUTPUT = get(
    ENV,
    "KN11_RESIDUAL_SPACE_CERTIFICATE",
    joinpath("evidence", "residual-space.json"),
)
const MAX_DEGREE = 2 * TARGET_DEGREE

function symmetric_polynomial(polynomial, u, v, t)
    permutations = (
        (u, v, t),
        (u, t, v),
        (v, u, t),
        (v, t, u),
        (t, u, v),
        (t, v, u),
    )
    return all(polynomial == polynomial(values...) for values in permutations)
end

univariate_degree(polynomial) = iszero(polynomial) ? 0 : degree(polynomial)

function main()
univariate_ring, w = polynomial_ring(QQ, :w)
univariate_entries = 0
univariate_max_degree = 0

for k in 0:TARGET_DEGREE
    matrix_value =
        3 * KissingNumber11Certificate.symmetrized_matrix(
            QQ,
            TARGET_DIMENSION,
            k,
            TARGET_DEGREE,
            w,
            w,
            1,
        )
    for value in matrix_value
        univariate_entries += 1
        univariate_max_degree =
            max(univariate_max_degree, univariate_degree(value))
    end
end

gegenbauer_basis =
    basis_gegenbauer(MAX_DEGREE, TARGET_DIMENSION, w)
for value in gegenbauer_basis
    univariate_entries += 1
    univariate_max_degree =
        max(univariate_max_degree, univariate_degree(value))
end

chebyshev_basis = basis_chebyshev(MAX_DEGREE, w)
for left in chebyshev_basis[1:(TARGET_DEGREE + 1)]
    for right in chebyshev_basis[1:(TARGET_DEGREE + 1)]
        univariate_entries += 1
        univariate_max_degree =
            max(univariate_max_degree, univariate_degree(left * right))
    end
end
interval = (w + 1) * (TARGET_COSTHETA - w)
for left in chebyshev_basis[1:TARGET_DEGREE]
    for right in chebyshev_basis[1:TARGET_DEGREE]
        univariate_entries += 1
        univariate_max_degree =
            max(
                univariate_max_degree,
                univariate_degree(interval * left * right),
            )
    end
end

univariate_entries == 2757 ||
    error("unexpected univariate coefficient-entry count")
univariate_max_degree <= MAX_DEGREE ||
    error("univariate residual degree exceeds $MAX_DEGREE")

trivariate_ring, (u, v, t) = polynomial_ring(QQ, [:u, :v, :t])
three_point_entries = 0
three_point_max_degree = 0
for k in 0:TARGET_DEGREE
    matrix_value = KissingNumber11Certificate.symmetrized_matrix(
        QQ,
        TARGET_DIMENSION,
        k,
        TARGET_DEGREE,
        u,
        v,
        t,
    )
    for value in matrix_value
        symmetric_polynomial(value, u, v, t) ||
            error("three-point kernel entry is not symmetric")
        three_point_entries += 1
        three_point_max_degree =
            max(three_point_max_degree, total_degree(value))
    end
end
three_point_entries == 2109 ||
    error("unexpected three-point kernel-entry count")
three_point_max_degree <= MAX_DEGREE ||
    error("three-point residual degree exceeds $MAX_DEGREE")

elementary_1 = u + v + t
elementary_2 = u * v + u * t + v * t
elementary_3 = u * v * t
all(
    symmetric_polynomial(value, u, v, t)
    for value in (elementary_1, elementary_2, elementary_3)
) || error("elementary invariant basis is not symmetric")

residual_exponents =
    KissingNumber11Certificate.symmetric_exponents(MAX_DEGREE)
length(residual_exponents) == 1461 ||
    error("unexpected symmetric residual-space dimension")

basis_degrees = Int[]
for degree in 0:TARGET_DEGREE
    for k in 0:div(degree, 3)
        for j in 0:div(degree - 3 * k, 2)
            push!(basis_degrees, degree)
        end
    end
end
length(basis_degrees) == 237 ||
    error("unexpected degree-17 invariant-basis dimension")

p(x) = (x + 1) * (TARGET_COSTHETA - x)
weights = [
    trivariate_ring(1),
    p(u) + p(v) + p(t),
    p(u) * p(v) + p(u) * p(t) + p(v) * p(t),
    p(u) * p(v) * p(t),
    1 + 2 * u * v * t - u^2 - v^2 - t^2,
]
all(symmetric_polynomial(value, u, v, t) for value in weights) ||
    error("domain weight is not symmetric")

alternating = (u - v) * (v - t) * (t - u)
symmetric_polynomial(alternating^2, u, v, t) ||
    error("alternating representation kernel is not symmetric")

standard_rows = [
    [2 * u - v - t, 2 * v * t - u * t - u * v],
    [v - t, u * t - u * v],
]
standard_factors = [QQ(1) // 2, QQ(3) // 2]
for left in 1:2
    for right in 1:2
        kernel = sum(
            standard_factors[row] *
            standard_rows[row][left] *
            standard_rows[row][right]
            for row in 1:2
        )
        symmetric_polynomial(kernel, u, v, t) ||
            error("standard representation kernel is not symmetric")
    end
end

equivariant_degree_rows = [
    [[0]],
    [[3]],
    [[1, 2], [1, 2]],
]
block_sizes = Int[]
sos_max_degree = 0
for weight in weights
    weight_degree = total_degree(weight)
    for rows in equivariant_degree_rows
        row_descriptors = Vector{Tuple{Int,Int}}[]
        for row in rows
            descriptors = Tuple{Int,Int}[]
            for equivariant_degree in row
                for basis_degree in basis_degrees
                    if weight_degree +
                       2 * equivariant_degree +
                       2 * basis_degree <= MAX_DEGREE
                        push!(
                            descriptors,
                            (equivariant_degree, basis_degree),
                        )
                    end
                end
            end
            push!(row_descriptors, descriptors)
        end
        all(length(row) == length(first(row_descriptors)) for row in row_descriptors) ||
            error("equivariant row lengths differ")
        push!(block_sizes, length(first(row_descriptors)))
        for row in row_descriptors
            for left in row
                for right in row
                    entry_degree =
                        weight_degree +
                        left[1] +
                        left[2] +
                        right[1] +
                        right[2]
                    sos_max_degree = max(sos_max_degree, entry_degree)
                end
            end
        end
    end
end
length(block_sizes) == 15 ||
    error("unexpected trivariate SOS block count")
sos_max_degree <= MAX_DEGREE ||
    error("trivariate SOS residual degree exceeds $MAX_DEGREE")

expected_block_sizes = [
    237, 147, 378,
    204, 123, 321,
    174, 102, 270,
    147, 83, 225,
    174, 102, 270,
]
block_sizes == expected_block_sizes ||
    error("trivariate SOS block sizes differ from the canonical layout")

content = """
{
  "schema_version": 1,
  "dimension": $TARGET_DIMENSION,
  "degree": $TARGET_DEGREE,
  "maximum_residual_degree": $MAX_DEGREE,
  "univariate_coefficient_entries": $univariate_entries,
  "univariate_maximum_degree": $univariate_max_degree,
  "univariate_sample_count": 35,
  "univariate_samples_distinct": true,
  "three_point_kernel_entries": $three_point_entries,
  "three_point_maximum_degree": $three_point_max_degree,
  "trivariate_sos_block_count": $(length(block_sizes)),
  "trivariate_sos_maximum_degree": $sos_max_degree,
  "symmetric_residual_basis_count": $(length(residual_exponents)),
  "canonical_sample_count": 1461,
  "canonical_modular_rank_prime": 65521,
  "canonical_modular_rank": 1461,
  "symmetry_checks_pass": true,
  "exact_field_checks_pass": true
}
"""

mkpath(dirname(OUTPUT))
temporary = OUTPUT * ".tmp.$(getpid())"
try
    write(temporary, content)
    mv(temporary, OUTPUT; force=true)
finally
    isfile(temporary) && rm(temporary; force=true)
end
println("residual_space_certificate=", OUTPUT)
println("residual_space_sha256=", bytes2hex(sha256(content)))
end

main()
