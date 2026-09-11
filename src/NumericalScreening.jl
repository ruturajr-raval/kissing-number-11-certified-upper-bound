module NumericalScreening

using ClusteredLowRankSolver
using LinearAlgebra
using Nemo

export sampled_numerical_residual_summary
export sampled_minimum_matrix_eigenvalue

numeric_sample_value(value, sample, sample_index) = BigFloat(value)

function numeric_sample_value(
    value::SampledMPolyRingElem,
    sample,
    sample_index,
)
    samples = parent(value).samples
    1 <= sample_index <= length(samples) ||
        throw(BoundsError(samples, sample_index))
    expected_sample = sample isa AbstractVector ? sample : [sample]
    samples[sample_index] == expected_sample ||
        error("sampled-polynomial ordering does not match the constraint")
    return BigFloat(value.evaluations[sample_index])
end

numeric_sample_value(
    value::Union{Nemo.PolyRingElem,Nemo.MPolyRingElem},
    sample,
    sample_index,
) = BigFloat(Nemo.evaluate(value, sample))

function numeric_trace_inner(
    coefficient::LowRankMatPol,
    matrix_value::AbstractMatrix{BigFloat},
    sample,
    sample_index,
)
    size(coefficient) == size(matrix_value) ||
        throw(DimensionMismatch("coefficient and solution block sizes differ"))
    total = BigFloat(0)
    for index in eachindex(coefficient.lambda)
        lambda = numeric_sample_value(
            coefficient.lambda[index],
            sample,
            sample_index,
        )
        left = map(
            value -> numeric_sample_value(value, sample, sample_index),
            coefficient.vs[index],
        )
        right = map(
            value -> numeric_sample_value(value, sample, sample_index),
            coefficient.ws[index],
        )
        total += lambda * dot(left, matrix_value * right)
    end
    return total
end

function numeric_trace_inner(
    coefficient::AbstractMatrix,
    matrix_value::AbstractMatrix{BigFloat},
    sample,
    sample_index,
)
    size(coefficient) == size(matrix_value) ||
        throw(DimensionMismatch("coefficient and solution block sizes differ"))
    return sum(
        numeric_sample_value(
            coefficient[row, column],
            sample,
            sample_index,
        ) * matrix_value[row, column]
        for row in axes(coefficient, 1), column in axes(coefficient, 2)
    )
end

function solution_precision(solution)
    precisions = Int[]
    for matrix_value in values(matrixvars(solution))
        append!(precisions, precision.(matrix_value))
    end
    append!(precisions, precision.(values(freevars(solution))))
    return isempty(precisions) ? precision(BigFloat) : maximum(precisions)
end

function sampled_residual_summary(problem, solution)
    matrix_values = Dict{Any,Matrix{BigFloat}}(
        key => BigFloat.(value)
        for (key, value) in matrixvars(solution)
    )
    free_values = Dict{Any,BigFloat}(
        key => BigFloat(value)
        for (key, value) in freevars(solution)
    )
    maximum_absolute = BigFloat(0)
    scalar_count = 0
    all_finite = all(
        isfinite,
        Iterators.flatten(values(matrix_values)),
    ) && all(isfinite, values(free_values))

    for constraint in constraints(problem)
        length(constraint.samples) == length(constraint.scalings) ||
            error("constraint sample and scaling counts differ")
        for (sample_index, sample) in enumerate(constraint.samples)
            residual = -numeric_sample_value(
                constraint.constant,
                sample,
                sample_index,
            )
            for (key, coefficient) in matrixcoeffs(constraint)
                haskey(matrix_values, key) ||
                    error("solution is missing matrix variable $(repr(key))")
                residual += numeric_trace_inner(
                    coefficient,
                    matrix_values[key],
                    sample,
                    sample_index,
                )
            end
            for (key, coefficient) in freecoeffs(constraint)
                haskey(free_values, key) ||
                    error("solution is missing free variable $(repr(key))")
                residual +=
                    numeric_sample_value(
                        coefficient,
                        sample,
                        sample_index,
                    ) * free_values[key]
            end
            scalar_count += 1
            if isfinite(residual)
                maximum_absolute = max(maximum_absolute, abs(residual))
            else
                all_finite = false
            end
        end
    end
    return (
        maximum_absolute=all_finite ? maximum_absolute : BigFloat(Inf),
        scalar_count=scalar_count,
        all_finite=all_finite,
    )
end

"""
    sampled_numerical_residual_summary(problem, solution; precision)

Evaluate every affine equality at its canonical samples before pairing exact
polynomial coefficients with the floating-point primal solution.
"""
function sampled_numerical_residual_summary(
    problem,
    solution;
    precision::Int=solution_precision(solution),
)
    precision > 0 || throw(ArgumentError("precision must be positive"))
    return setprecision(BigFloat, precision) do
        sampled_residual_summary(problem, solution)
    end
end

"""
    sampled_minimum_matrix_eigenvalue(solution; precision)

Compute the full symmetric BigFloat eigenspectrum of each primal block and
return the smallest eigenvalue. The full spectrum avoids Julia's unsupported
partial-spectrum path for generic BigFloat matrices.
"""
function sampled_minimum_matrix_eigenvalue(
    solution;
    precision::Int=solution_precision(solution),
)
    precision > 0 || throw(ArgumentError("precision must be positive"))
    return setprecision(BigFloat, precision) do
        minimum_value = BigFloat(Inf)
        for matrix_value in values(matrixvars(solution))
            numeric_matrix = BigFloat.(matrix_value)
            all(isfinite, numeric_matrix) || return BigFloat(-Inf)
            numeric_matrix == transpose(numeric_matrix) ||
                error("primal solution contains a nonsymmetric matrix block")
            eigenvalues = eigvals(Symmetric(numeric_matrix))
            isempty(eigenvalues) &&
                error("primal solution contains an empty matrix block")
            minimum_value = min(minimum_value, minimum(eigenvalues))
        end
        return minimum_value
    end
end

end
