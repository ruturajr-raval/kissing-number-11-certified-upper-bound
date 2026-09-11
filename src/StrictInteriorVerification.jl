module StrictInteriorVerification

using KissingNumber11Certificate
using ClusteredLowRankSolver
using Nemo

export rigorous_positive_definite
export verify_exact_affine_identities
export verify_strictly_positive_exact_solution

function scalar_at_sample(value, sample, sample_index::Int)
    if value isa SampledMPolyRingElem
        sample_index <= length(value.evaluations) ||
            error("sampled coefficient has too few evaluations")
        coefficient_samples = parent(value).samples
        sample_index <= length(coefficient_samples) ||
            error("sampled coefficient has too few parent samples")
        coefficient_samples[sample_index] == sample ||
            error("sampled coefficient is not aligned with the constraint")
        return value.evaluations[sample_index]
    end
    return ClusteredLowRankSolver.myevaluate(value, sample)
end

function trace_at_sample(
    coefficient::AbstractMatrix,
    matrix,
    sample,
    sample_index::Int,
)
    size(coefficient) == size(matrix) ||
        throw(DimensionMismatch("coefficient and solution block sizes differ"))
    total = QQ(0)
    for column in axes(matrix, 2), row in axes(matrix, 1)
        matrix_value = matrix[row, column]
        iszero(matrix_value) && continue
        coefficient_value = scalar_at_sample(
            coefficient[row, column],
            sample,
            sample_index,
        )
        iszero(coefficient_value) && continue
        total += coefficient_value * matrix_value
    end
    return total
end

function trace_at_sample(
    coefficient::LowRankMatPol,
    matrix,
    sample,
    sample_index::Int,
)
    size(coefficient) == size(matrix) ||
        throw(DimensionMismatch("coefficient and solution block sizes differ"))
    total = QQ(0)
    for rank_index in eachindex(coefficient.lambda)
        lambda = scalar_at_sample(
            coefficient.lambda[rank_index],
            sample,
            sample_index,
        )
        iszero(lambda) && continue
        left = [
            scalar_at_sample(value, sample, sample_index)
            for value in coefficient.vs[rank_index]
        ]
        right = [
            scalar_at_sample(value, sample, sample_index)
            for value in coefficient.ws[rank_index]
        ]
        inner = QQ(0)
        for column in axes(matrix, 2)
            iszero(right[column]) && continue
            for row in axes(matrix, 1)
                matrix_value = matrix[row, column]
                (iszero(left[row]) || iszero(matrix_value)) && continue
                inner += left[row] * matrix_value * right[column]
            end
        end
        total += lambda * inner
    end
    return total
end

"""
    verify_exact_affine_identities(problem, solution; verbose=false)

Verify every sampled affine identity one sample at a time. This is equivalent
to checking `slacks(problem, solution)`, but avoids constructing arithmetic
vectors containing all 1,461 trivariate samples during every matrix product.
"""
function verify_exact_affine_identities(
    problem,
    solution;
    verbose::Bool=false,
)
    residual_count = 0
    constraint_count = length(constraints(problem))
    for (constraint_index, constraint) in enumerate(constraints(problem))
        sample_count = length(constraint.samples)
        for (sample_index, sample) in enumerate(constraint.samples)
            residual = -scalar_at_sample(
                constraint.constant,
                sample,
                sample_index,
            )
            for (key, coefficient) in matrixcoeffs(constraint)
                residual += trace_at_sample(
                    coefficient,
                    matrixvar(solution, key),
                    sample,
                    sample_index,
                )
            end
            for (key, coefficient) in freecoeffs(constraint)
                residual +=
                    scalar_at_sample(coefficient, sample, sample_index) *
                    freevar(solution, key)
            end
            residual_count += 1
            if !iszero(residual)
                return (
                    valid=false,
                    residual_count=residual_count,
                    failed_constraint=constraint_index,
                    failed_sample=sample_index,
                )
            end
            if verbose &&
               (
                   sample_index == 1 ||
                   sample_index == sample_count ||
                   sample_index % 100 == 0
               )
                println(
                    "exact_affine_constraint=$constraint_index/$constraint_count " *
                    "sample=$sample_index/$sample_count",
                )
            end
        end
    end
    return (
        valid=true,
        residual_count=residual_count,
        failed_constraint=nothing,
        failed_sample=nothing,
    )
end

"""
    rigorous_positive_definite(matrix; precision=256, max_precision=16384)

Prove positive definiteness of an exact rational matrix with Arb ball
arithmetic. A successful interval Cholesky factorization is a rigorous proof,
not a floating-point screening result.
"""
function rigorous_positive_definite(
    matrix;
    precision::Int=256,
    max_precision::Int=16_384,
)
    matrix isa AbstractMatrix || return false
    size(matrix, 1) == size(matrix, 2) || return false
    size(matrix, 1) > 0 || return false
    all(KissingNumber11Certificate.is_exact_scalar, matrix) || return false
    exact_matrix = typeof(QQ(0)).(Matrix(matrix))
    exact_matrix == transpose(exact_matrix) || return false
    return ClusteredLowRankSolver.checkpd_cholesky(
        exact_matrix;
        FF=QQ,
        prec=precision,
        maxprec=max_precision,
    )
end

"""
    verify_strictly_positive_exact_solution(problem, solution; ...)

Check exact scalar types, canonical structure, every affine identity, the
target objective, and rigorous strict positivity of every matrix block.
Strict positivity is stronger than the positive-semidefinite theorem gate.
"""
function verify_strictly_positive_exact_solution(
    problem,
    solution;
    expected_objective=nothing,
    objective_functional=nothing,
    verbose::Bool=false,
)
    verbose && println("exact_verification_stage=types-and-structure")
    exact_types_ok =
        KissingNumber11Certificate.solution_has_exact_scalars(solution)
    expected_blocks = blocksizes(problem)
    actual_blocks = matrixvars(solution)
    block_keys_ok = Set(keys(actual_blocks)) == Set(keys(expected_blocks))
    block_sizes_ok = block_keys_ok && all(
        size(actual_blocks[key]) ==
        (expected_blocks[key], expected_blocks[key])
        for key in keys(expected_blocks)
    )
    expected_free_keys = Set{Any}()
    union!(expected_free_keys, keys(freecoeffs(objective(problem))))
    for constraint in constraints(problem)
        union!(expected_free_keys, keys(freecoeffs(constraint)))
    end
    free_keys_ok = Set(keys(freevars(solution))) == expected_free_keys
    structure_ok = block_keys_ok && block_sizes_ok && free_keys_ok

    verbose && println("exact_verification_stage=affine-identities")
    affine_verification =
        exact_types_ok && structure_ok ?
        verify_exact_affine_identities(problem, solution; verbose=verbose) :
        (
            valid=false,
            residual_count=0,
            failed_constraint=nothing,
            failed_sample=nothing,
        )
    affine_ok = affine_verification.valid

    verbose && println("exact_verification_stage=positive-definiteness")
    block_results = NamedTuple[]
    ordered_blocks = sort(collect(matrixvars(solution)); by=item -> repr(first(item)))
    for (index, (key, value)) in enumerate(ordered_blocks)
        verbose && println(
            "exact_psd_block=$index/$(length(ordered_blocks)) key=$(repr(key)) size=$(size(value, 1))",
        )
        push!(
            block_results,
            (
                key=repr(key),
                key_type=string(typeof(key)),
                valid=rigorous_positive_definite(value),
            ),
        )
    end

    verbose && println("exact_verification_stage=objective")
    objective_value = isnothing(objective_functional) || !structure_ok ?
        nothing :
        objvalue(objective_functional, solution)
    objective_ok = isnothing(expected_objective) ?
        true :
        exact_types_ok &&
        !isnothing(objective_value) &&
        objective_value == expected_objective
    positive_definite_ok = all(result.valid for result in block_results)
    return (
        valid=
            exact_types_ok &&
            structure_ok &&
            affine_ok &&
            positive_definite_ok &&
            objective_ok,
        exact_types_ok=exact_types_ok,
        structure_ok=structure_ok,
        block_keys_ok=block_keys_ok,
        block_sizes_ok=block_sizes_ok,
        free_keys_ok=free_keys_ok,
        affine_ok=affine_ok,
        block_results=block_results,
        positive_definite_ok=positive_definite_ok,
        objective_ok=objective_ok,
        objective_value=objective_value,
        residual_count=affine_verification.residual_count,
        failed_affine_constraint=affine_verification.failed_constraint,
        failed_affine_sample=affine_verification.failed_sample,
        block_count=length(block_results),
    )
end

end
