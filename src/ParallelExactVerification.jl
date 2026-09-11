module ParallelExactVerification

using Base.Threads
using KissingNumber11Certificate
using ClusteredLowRankSolver
using Nemo

using ..StrictInteriorVerification

export affine_sample_chunks
export verify_parallel_exact_affine_sample_range
export verify_parallel_exact_affine_identities
export verify_parallel_strictly_positive_exact_solution

function sample_residual(constraint, solution, sample_index::Int)
    sample = constraint.samples[sample_index]
    residual = -StrictInteriorVerification.scalar_at_sample(
        constraint.constant,
        sample,
        sample_index,
    )
    for (key, coefficient) in matrixcoeffs(constraint)
        residual += StrictInteriorVerification.trace_at_sample(
            coefficient,
            matrixvar(solution, key),
            sample,
            sample_index,
        )
    end
    for (key, coefficient) in freecoeffs(constraint)
        residual +=
            StrictInteriorVerification.scalar_at_sample(
                coefficient,
                sample,
                sample_index,
            ) *
            freevar(solution, key)
    end
    return residual
end

function affine_sample_chunks(problem; chunk_size::Int)
    chunk_size > 0 || throw(ArgumentError("chunk_size must be positive"))
    chunks = NamedTuple[]
    for (constraint_index, constraint) in enumerate(constraints(problem))
        sample_count = length(constraint.samples)
        for first_sample in 1:chunk_size:sample_count
            push!(
                chunks,
                (
                    constraint_index=constraint_index,
                    first_sample=first_sample,
                    last_sample=min(
                        sample_count,
                        first_sample + chunk_size - 1,
                    ),
                    sample_count=sample_count,
                ),
            )
        end
    end
    return chunks
end

"""
    verify_parallel_exact_affine_sample_range(
        problem,
        solution,
        constraint_index,
        first_sample,
        last_sample;
        verbose=false,
    )

Verify one inclusive sample range. This supports process-isolated verification
where each worker exits after a bounded amount of exact rational arithmetic.
"""
function verify_parallel_exact_affine_sample_range(
    problem,
    solution,
    constraint_index::Int,
    first_sample::Int,
    last_sample::Int;
    verbose::Bool=false,
)
    problem_constraints = constraints(problem)
    1 <= constraint_index <= length(problem_constraints) ||
        throw(ArgumentError("constraint index is out of range"))
    constraint = problem_constraints[constraint_index]
    sample_count = length(constraint.samples)
    1 <= first_sample <= last_sample <= sample_count ||
        throw(ArgumentError("sample range is out of bounds"))

    range_count = last_sample - first_sample + 1
    valid_samples = fill(false, range_count)
    completed = Atomic{Int}(0)
    output_lock = ReentrantLock()
    batch_size = max(1, 2 * nthreads())
    for batch_start in first_sample:batch_size:last_sample
        batch_stop = min(last_sample, batch_start + batch_size - 1)
        Threads.@threads :dynamic for sample_index in batch_start:batch_stop
            valid_samples[sample_index - first_sample + 1] =
                iszero(sample_residual(constraint, solution, sample_index))
            completed_count = atomic_add!(completed, 1) + 1
            if verbose &&
               (
                   completed_count == 1 ||
                   completed_count == range_count ||
                   completed_count % 100 == 0
               )
                lock(output_lock) do
                    println(
                        "exact_affine_chunk_constraint=$constraint_index/" *
                        "$(length(problem_constraints)) " *
                        "range=$first_sample:$last_sample " *
                        "completed=$completed_count/$range_count",
                    )
                end
            end
        end
        GC.gc(true)
    end
    failed_offset = findfirst(!, valid_samples)
    return (
        valid=isnothing(failed_offset),
        residual_count=range_count,
        failed_constraint=
            isnothing(failed_offset) ? nothing : constraint_index,
        failed_sample=
            isnothing(failed_offset) ?
            nothing :
            first_sample + failed_offset - 1,
        thread_count=nthreads(),
        batch_size=batch_size,
    )
end

"""
    verify_parallel_exact_affine_identities(problem, solution; verbose=false)

Verify independent sample identities across Julia threads. Every worker uses
fresh exact-rational temporaries and treats the restored solution as read-only.
"""
function verify_parallel_exact_affine_identities(
    problem,
    solution;
    verbose::Bool=false,
)
    residual_count = 0
    for (constraint_index, constraint) in enumerate(constraints(problem))
        sample_count = length(constraint.samples)
        range_verification = verify_parallel_exact_affine_sample_range(
            problem,
            solution,
            constraint_index,
            1,
            sample_count;
            verbose=verbose,
        )
        residual_count += range_verification.residual_count
        if !range_verification.valid
            return (
                valid=false,
                residual_count=residual_count,
                failed_constraint=constraint_index,
                failed_sample=range_verification.failed_sample,
                thread_count=nthreads(),
                batch_size=range_verification.batch_size,
            )
        end
    end
    return (
        valid=true,
        residual_count=residual_count,
        failed_constraint=nothing,
        failed_sample=nothing,
        thread_count=nthreads(),
        batch_size=max(1, 2 * nthreads()),
    )
end

function validated_preverified_affine(problem, verification)
    required = (
        :valid,
        :residual_count,
        :failed_constraint,
        :failed_sample,
        :thread_count,
        :batch_size,
    )
    all(name -> hasproperty(verification, name), required) ||
        throw(ArgumentError("preverified affine result is incomplete"))
    verification.valid === true ||
        throw(ArgumentError("preverified affine result is not valid"))
    expected_residual_count =
        sum(length(constraint.samples) for constraint in constraints(problem))
    verification.residual_count == expected_residual_count ||
        throw(ArgumentError("preverified affine residual count is incorrect"))
    isnothing(verification.failed_constraint) ||
        throw(ArgumentError("preverified affine result records a failure"))
    isnothing(verification.failed_sample) ||
        throw(ArgumentError("preverified affine result records a failure"))
    verification.thread_count > 0 ||
        throw(ArgumentError("preverified affine thread count is invalid"))
    verification.batch_size > 0 ||
        throw(ArgumentError("preverified affine batch size is invalid"))
    return verification
end

"""
    verify_parallel_strictly_positive_exact_solution(problem, solution; ...)

Run structure and exact-scalar checks, threaded samplewise affine replay,
sequential rigorous Arb-ball Cholesky proofs, and the exact objective check.
"""
function verify_parallel_strictly_positive_exact_solution(
    problem,
    solution;
    expected_objective=nothing,
    objective_functional=nothing,
    verbose::Bool=false,
    preverified_affine=nothing,
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
        (
            isnothing(preverified_affine) ?
            verify_parallel_exact_affine_identities(
                problem,
                solution;
                verbose=verbose,
            ) :
            validated_preverified_affine(problem, preverified_affine)
        ) :
        (
            valid=false,
            residual_count=0,
            failed_constraint=nothing,
            failed_sample=nothing,
            thread_count=nthreads(),
            batch_size=max(1, 2 * nthreads()),
        )
    affine_ok = affine_verification.valid

    verbose && println("exact_verification_stage=positive-definiteness")
    block_results = NamedTuple[]
    ordered_blocks =
        sort(collect(matrixvars(solution)); by=item -> repr(first(item)))
    for (index, (key, value)) in enumerate(ordered_blocks)
        verbose && println(
            "exact_psd_block=$index/$(length(ordered_blocks)) " *
            "key=$(repr(key)) size=$(size(value, 1))",
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
        affine_thread_count=affine_verification.thread_count,
        affine_batch_size=affine_verification.batch_size,
        affine_preverified=!isnothing(preverified_affine),
        block_count=length(block_results),
    )
end

end
