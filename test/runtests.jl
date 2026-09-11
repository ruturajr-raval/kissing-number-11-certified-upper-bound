using Test
using KissingNumber11Certificate
using ClusteredLowRankSolver
using LinearAlgebra
using Nemo
using Serialization
using SHA

include("test_compact_witness.jl")
include("test_dependency_integrity.jl")
include(joinpath(@__DIR__, "..", "src", "NumericalScreening.jl"))
include(joinpath(@__DIR__, "..", "src", "CheckpointRecovery.jl"))
include(joinpath(@__DIR__, "..", "src", "PortableExactSolution.jl"))
include(joinpath(@__DIR__, "..", "src", "StrictInteriorVerification.jl"))
include(joinpath(@__DIR__, "..", "src", "ParallelExactVerification.jl"))
using .NumericalScreening
using .CheckpointRecovery
using .PortableExactSolution
using .StrictInteriorVerification
using .ParallelExactVerification

@testset "target parameters" begin
    @test TARGET_DIMENSION == 11
    @test TARGET_DEGREE == 17
    @test TARGET_COSTHETA == QQ(1) // 2
    @test TARGET_OBJECTIVE == QQ(86899) // 100
    @test TARGET_OBJECTIVE < 869
end

@testset "problem construction" begin
    optimized = build_three_point_problem(3, QQ(1) // 2, 2, 2)
    fixed = build_three_point_problem(
        3,
        QQ(1) // 2,
        2,
        2;
        fixed_objective=QQ(13),
    )

    @test length(constraints(optimized)) == 2
    @test length(constraints(fixed)) == 3
    @test objective(optimized).constant == 1
    @test objective(fixed).constant == 0
    @test constraints(fixed)[end].constant == 12
    @test isempty(matrixcoeffs(objective(fixed)))
    @test original_objective(2, 2).constant == 1
end

@testset "sample unisolvence" begin
    certificate = sample_unisolvence_certificate(2, 2)
    @test certificate.univariate_distinct
    @test certificate.full_rank
    @test certificate.modular_rank == certificate.symmetric_basis_count
    @test certificate.trivariate_sample_count ==
          certificate.symmetric_basis_count
end

@testset "exact positive semidefiniteness" begin
    @test exact_psd([1 // 1 0 // 1; 0 // 1 0 // 1])
    @test exact_psd([1 // 1 1 // 1; 1 // 1 1 // 1])
    @test exact_psd(zeros(Rational{Int}, 3, 3))
    @test !exact_psd([0 // 1 1 // 1; 1 // 1 0 // 1])
    @test !exact_psd([1 // 1 0 // 1; 0 // 1 -1 // 1])
    @test !exact_psd([1 // 1 2 // 1; 2 // 1 1 // 1])
    @test !exact_psd([1 2; 2 1])
    @test !exact_psd([1.0 0.0; 0.0 1.0])
    @test !exact_psd(zeros(Rational{Int}, 0, 0))
    large = big(10)^80
    @test exact_psd([
        large // 1 1 // 1
        1 // 1 large // 1
    ])
end

@testset "rigorous strict-interior positivity" begin
    @test rigorous_positive_definite([
        QQ(2) QQ(1)
        QQ(1) QQ(2)
    ])
    @test !rigorous_positive_definite([
        QQ(1) QQ(1)
        QQ(1) QQ(1)
    ])
    @test !rigorous_positive_definite([
        QQ(1) QQ(2)
        QQ(2) QQ(1)
    ])
    @test !rigorous_positive_definite([1.0 0.0; 0.0 1.0])
end

@testset "portable exact solution" begin
    rational_type = typeof(QQ(0))
    source = PrimalSolution{rational_type}(
        QQ,
        Dict{Any,Matrix{rational_type}}(
            (:block, 1) => [
                QQ(2) QQ(1) // 3
                QQ(1) // 3 QQ(5)
            ],
        ),
        Dict{Any,rational_type}(:free => QQ(7) // 11),
    )
    payload = encode_exact_solution(source)
    @test payload.encoding == PORTABLE_EXACT_SOLUTION_ENCODING
    @test all(
        value isa Rational{BigInt}
        for block in payload.blocks
        for value in block.upper_triangle
    )
    restored = restore_exact_solution(payload)
    @test matrixvars(restored) == matrixvars(source)
    @test freevars(restored) == freevars(source)

    temporary_parent = normpath(joinpath(@__DIR__, "..", "build"))
    mkpath(temporary_parent)
    mktempdir(temporary_parent) do directory
        payload_path = joinpath(directory, "portable-exact.jls")
        open(stream -> serialize(stream, payload), payload_path, "w")
        project_root = normpath(joinpath(@__DIR__, ".."))
        portable_source =
            joinpath(project_root, "src", "PortableExactSolution.jl")
        child_script = """
            using ClusteredLowRankSolver
            using Nemo
            using Serialization
            include($(repr(portable_source)))
            using .PortableExactSolution
            payload = open(deserialize, $(repr(payload_path)))
            solution = restore_exact_solution(payload)
            @assert matrixvars(solution)[(:block, 1)][1, 2] == QQ(1) // 3
            @assert freevars(solution)[:free] == QQ(7) // 11
        """
        command = `$(Base.julia_cmd()) --startup-file=no --history-file=no --project=$project_root -e $child_script`
        run(addenv(command, "JULIA_DEPOT_PATH" => first(DEPOT_PATH)))
    end
end

@testset "samplewise exact affine verification" begin
    sampled_ring = SampledMPolyRing(QQ, [[QQ(0)], [QQ(1)]])
    sampled_coefficient =
        SampledMPolyRingElem(sampled_ring, [QQ(2), QQ(5)])
    sampled_constant =
        SampledMPolyRingElem(sampled_ring, [QQ(6), QQ(15)])
    problem = Problem(
        Minimize(Objective(QQ(0), Dict(), Dict())),
        [
            Constraint(
                sampled_constant,
                Dict{Any,Any}(:x => fill(sampled_coefficient, 1, 1)),
                Dict(),
                [[QQ(0)], [QQ(1)]],
            ),
        ],
    )
    rational_type = typeof(QQ(0))
    solution = PrimalSolution{rational_type}(
        QQ,
        Dict{Any,Matrix{rational_type}}(:x => fill(QQ(3), 1, 1)),
        Dict{Any,rational_type}(),
    )
    verification = verify_exact_affine_identities(problem, solution)
    @test verification.valid
    @test verification.residual_count == 2
    @test all(iszero, slacks(problem, solution))

    invalid_solution = PrimalSolution{rational_type}(
        QQ,
        Dict{Any,Matrix{rational_type}}(:x => fill(QQ(4), 1, 1)),
        Dict{Any,rational_type}(),
    )
    invalid_verification =
        verify_exact_affine_identities(problem, invalid_solution)
    @test !invalid_verification.valid
    @test invalid_verification.failed_constraint == 1
    @test invalid_verification.failed_sample == 1
    @test !all(iszero, slacks(problem, invalid_solution))
end

@testset "canonical samplewise affine equivalence" begin
    problem = build_three_point_problem(
        3,
        QQ(1) // 2,
        2,
        2;
        fixed_objective=QQ(13),
    )
    rational_type = typeof(QQ(0))
    blocks = Dict{Any,Matrix{rational_type}}()
    for (key, dimension) in blocksizes(problem)
        matrix = fill(QQ(0), dimension, dimension)
        for index in 1:dimension
            matrix[index, index] = QQ(index + 1)
        end
        blocks[key] = matrix
    end
    solution = PrimalSolution{rational_type}(
        QQ,
        blocks,
        Dict{Any,rational_type}(),
    )

    adjusted_constraints = Constraint[]
    for (constraint, residual) in zip(
        constraints(problem),
        slacks(problem, solution),
    )
        push!(
            adjusted_constraints,
            Constraint(
                constraint.constant + residual,
                copy(constraint.matrixcoeff),
                copy(constraint.freecoeff),
                constraint.samples,
                constraint.scalings,
            ),
        )
    end
    adjusted_problem = Problem(
        problem.maximize,
        problem.objective,
        adjusted_constraints,
    )
    verification =
        verify_exact_affine_identities(adjusted_problem, solution)
    parallel_verification =
        verify_parallel_exact_affine_identities(adjusted_problem, solution)
    chunks = affine_sample_chunks(adjusted_problem; chunk_size=2)
    chunk_verifications = [
        verify_parallel_exact_affine_sample_range(
            adjusted_problem,
            solution,
            chunk.constraint_index,
            chunk.first_sample,
            chunk.last_sample,
        )
        for chunk in chunks
    ]
    @test all(iszero, slacks(adjusted_problem, solution))
    @test verification.valid
    @test parallel_verification.valid
    @test all(result.valid for result in chunk_verifications)
    @test sum(result.residual_count for result in chunk_verifications) ==
          verification.residual_count
    @test parallel_verification.residual_count ==
          verification.residual_count
    @test verification.residual_count ==
          sum(length(constraint.samples) for constraint in adjusted_constraints)
end

@testset "strict-interior exact verifier" begin
    zero_block = fill(QQ(0), 2, 2)
    zero_objective = Objective(QQ(0), Dict(), Dict())
    problem = Problem(
        Minimize(zero_objective),
        [
            Constraint(
                QQ(0),
                Dict{Any,Any}(:x => zero_block),
                Dict(),
            ),
        ],
    )
    positive_solution = PrimalSolution{typeof(QQ(0))}(
        QQ,
        Dict{Any,Matrix{typeof(QQ(0))}}(
            :x => [
                QQ(2) QQ(1)
                QQ(1) QQ(2)
            ],
        ),
        Dict{Any,typeof(QQ(0))}(),
    )
    verification = verify_strictly_positive_exact_solution(
        problem,
        positive_solution;
        expected_objective=QQ(0),
        objective_functional=zero_objective,
    )
    @test verification.valid
    @test verification.exact_types_ok
    @test verification.structure_ok
    @test verification.affine_ok
    @test verification.positive_definite_ok
    @test verification.objective_ok
    @test verification.block_count == 1
    @test verification.residual_count == 1
    preverified_affine = (
        valid=true,
        residual_count=1,
        failed_constraint=nothing,
        failed_sample=nothing,
        thread_count=Threads.nthreads(),
        batch_size=max(1, 2 * Threads.nthreads()),
    )
    preverified = verify_parallel_strictly_positive_exact_solution(
        problem,
        positive_solution;
        expected_objective=QQ(0),
        objective_functional=zero_objective,
        preverified_affine=preverified_affine,
    )
    @test preverified.valid
    @test preverified.affine_preverified
    @test_throws ArgumentError verify_parallel_strictly_positive_exact_solution(
        problem,
        positive_solution;
        preverified_affine=merge(
            preverified_affine,
            (residual_count=0,),
        ),
    )

    singular_solution = PrimalSolution{typeof(QQ(0))}(
        QQ,
        Dict{Any,Matrix{typeof(QQ(0))}}(
            :x => [
                QQ(1) QQ(1)
                QQ(1) QQ(1)
            ],
        ),
        Dict{Any,typeof(QQ(0))}(),
    )
    singular_verification = verify_strictly_positive_exact_solution(
        problem,
        singular_solution,
    )
    @test !singular_verification.valid
    @test !singular_verification.positive_definite_ok
end

@testset "exact verifier rejects malformed solutions" begin
    zero_block = [
        QQ(0) QQ(0)
        QQ(0) QQ(0)
    ]
    problem = Problem(
        Minimize(Objective(QQ(0), Dict(), Dict())),
        [
            Constraint(
                QQ(0),
                Dict{Any,Any}("x" => zero_block, :x => zero_block),
                Dict(),
            ),
        ],
    )
    rational_type = typeof(QQ(0))
    blocks = Dict{Any,Matrix{rational_type}}(
        "x" => [
            QQ(0) QQ(1)
            QQ(1) QQ(0)
        ],
        :x => [
            QQ(1) QQ(0)
            QQ(0) QQ(1)
        ],
    )
    solution = PrimalSolution{rational_type}(
        QQ,
        blocks,
        Dict{Any,rational_type}(),
    )
    verification = verify_exact_solution(problem, solution)
    @test !verification.valid
    @test verification.structure_ok
    @test length(verification.block_results) == 2
    @test count(result -> !result.valid, verification.block_results) == 1

    missing_block_solution = PrimalSolution{rational_type}(
        QQ,
        Dict{Any,Matrix{rational_type}}(:x => blocks[:x]),
        Dict{Any,rational_type}(),
    )
    missing_verification =
        verify_exact_solution(problem, missing_block_solution)
    @test !missing_verification.valid
    @test !missing_verification.structure_ok
end

@testset "checkpoint binding" begin
    temporary_parent = normpath(joinpath(@__DIR__, "..", "build"))
    mkpath(temporary_parent)
    mktempdir(temporary_parent) do directory
        checkpoint_path = joinpath(directory, "checkpoint.jls")
        specification = (digest="expected-digest",)
        callback = checkpoint_callback(
            checkpoint_path,
            specification,
            "test-checkpoint";
            interval_seconds=0,
        )
        callback((iter=1,), "dual", "primal")

        loaded = load_compatible_checkpoint(
            checkpoint_path,
            specification,
            "test-checkpoint",
        )
        @test !isnothing(loaded)
        @test loaded.dual_solution == "dual"
        @test loaded.primal_solution == "primal"

        stale = load_compatible_checkpoint(
            checkpoint_path,
            (digest="different-digest",),
            "test-checkpoint",
        )
        @test isnothing(stale)
    end
end

@testset "sampled numerical residuals" begin
    polynomial_ring_1d, x = polynomial_ring(QQ, :x)
    coefficient = LowRankMatPol(
        [x + 1],
        [[QQ(1), QQ(2)]],
    )
    matrix_value = BigFloat[
        3 1
        1 2
    ]
    solution = PrimalSolution{BigFloat}(
        BigFloat,
        Dict{Any,Matrix{BigFloat}}(:x => matrix_value),
        Dict{Any,BigFloat}(),
    )
    problem = Problem(
        Minimize(Objective(0, Dict(), Dict())),
        [
            Constraint(
                0,
                Dict{Any,Any}(:x => coefficient),
                Dict(),
                [QQ(0), QQ(1) // 2],
            ),
        ],
    )

    @test_throws MethodError dot(coefficient, matrix_value)
    summary = sampled_numerical_residual_summary(
        problem,
        solution;
        precision=256,
    )
    @test summary.scalar_count == 2
    @test summary.all_finite
    @test summary.maximum_absolute == BigFloat("22.5")

    scalar_problem = Problem(
        Minimize(Objective(0, Dict(), Dict())),
        [
            Constraint(
                QQ(5),
                Dict{Any,Any}(:x => fill(QQ(2), 1, 1)),
                Dict(),
            ),
        ],
    )
    scalar_solution = PrimalSolution{BigFloat}(
        BigFloat,
        Dict{Any,Matrix{BigFloat}}(:x => fill(BigFloat("2.5"), 1, 1)),
        Dict{Any,BigFloat}(),
    )
    scalar_summary = sampled_numerical_residual_summary(
        scalar_problem,
        scalar_solution,
    )
    @test scalar_summary.scalar_count == 1
    @test scalar_summary.maximum_absolute == 0

    malformed_solution = PrimalSolution{BigFloat}(
        BigFloat,
        Dict{Any,Matrix{BigFloat}}(:x => zeros(BigFloat, 1, 1)),
        Dict{Any,BigFloat}(),
    )
    @test_throws DimensionMismatch sampled_numerical_residual_summary(
        problem,
        malformed_solution,
    )
    @test_throws ArgumentError sampled_numerical_residual_summary(
        problem,
        solution;
        precision=0,
    )

    sampled_ring = SampledMPolyRing(QQ, [[QQ(0)], [QQ(1)]])
    sampled_coefficient = LowRankMatPol(
        [SampledMPolyRingElem(sampled_ring, [QQ(1), QQ(2)])],
        [[QQ(1)]],
    )
    sampled_problem = Problem(
        Minimize(Objective(0, Dict(), Dict())),
        [
            Constraint(
                0,
                Dict{Any,Any}(:x => sampled_coefficient),
                Dict(),
                [QQ(0), QQ(1)],
                [QQ(7), QQ(11)],
            ),
        ],
    )
    sampled_solution = PrimalSolution{BigFloat}(
        BigFloat,
        Dict{Any,Matrix{BigFloat}}(:x => fill(BigFloat(3), 1, 1)),
        Dict{Any,BigFloat}(),
    )
    sampled_summary = sampled_numerical_residual_summary(
        sampled_problem,
        sampled_solution,
    )
    @test sampled_summary.scalar_count == 2
    @test sampled_summary.maximum_absolute == 6

    reversed_problem = Problem(
        Minimize(Objective(0, Dict(), Dict())),
        [
            Constraint(
                0,
                Dict{Any,Any}(:x => sampled_coefficient),
                Dict(),
                [QQ(1), QQ(0)],
            ),
        ],
    )
    @test_throws ErrorException sampled_numerical_residual_summary(
        reversed_problem,
        sampled_solution,
    )

    @test sampled_minimum_matrix_eigenvalue(sampled_solution) == 3
    indefinite_solution = PrimalSolution{BigFloat}(
        BigFloat,
        Dict{Any,Matrix{BigFloat}}(
            :x => BigFloat[
                1 2
                2 1
            ],
        ),
        Dict{Any,BigFloat}(),
    )
    @test sampled_minimum_matrix_eigenvalue(indefinite_solution) == -1
    nonsymmetric_solution = PrimalSolution{BigFloat}(
        BigFloat,
        Dict{Any,Matrix{BigFloat}}(
            :x => BigFloat[
                1 0
                100 1
            ],
        ),
        Dict{Any,BigFloat}(),
    )
    @test_throws ErrorException sampled_minimum_matrix_eigenvalue(
        nonsymmetric_solution,
    )
end

@testset "checkpoint snapshot binding" begin
    temporary_parent = normpath(joinpath(@__DIR__, "..", "build"))
    mkpath(temporary_parent)
    mktempdir(temporary_parent) do directory
        checkpoint_path = joinpath(directory, "checkpoint.jls")
        checkpoint = (
            schema_version=1,
            kind="test-checkpoint",
            specification_digest="expected",
            measurements=(iter=1,),
            dual_solution="dual",
            primal_solution="primal",
        )
        open(stream -> serialize(stream, checkpoint), checkpoint_path, "w")
        digest = open(
            stream -> bytes2hex(SHA.sha256(stream)),
            checkpoint_path,
        )
        snapshot = read_checkpoint_snapshot(
            checkpoint_path;
            max_bytes=1024^2,
            allowed_root=temporary_parent,
            expected_sha256=digest,
        )
        @test snapshot.sha256 == digest
        @test snapshot.checkpoint == checkpoint
        @test validate_checkpoint(
            snapshot.checkpoint,
            (digest="expected",),
            "test-checkpoint",
        ) == checkpoint
        @test_throws ErrorException validate_checkpoint(
            snapshot.checkpoint,
            (digest="different",),
            "test-checkpoint",
        )
        @test_throws ErrorException read_checkpoint_snapshot(
            checkpoint_path;
            max_bytes=1024^2,
            allowed_root=temporary_parent,
            expected_sha256=repeat("0", 64),
        )

        symlink_path = joinpath(directory, "checkpoint-link.jls")
        symlink(checkpoint_path, symlink_path)
        @test_throws ErrorException read_checkpoint_snapshot(
            symlink_path;
            max_bytes=1024^2,
            allowed_root=temporary_parent,
        )
    end
end
