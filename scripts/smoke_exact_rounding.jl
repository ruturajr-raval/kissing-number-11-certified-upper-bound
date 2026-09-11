using KissingNumber11Certificate
using ClusteredLowRankSolver

include(joinpath(@__DIR__, "..", "src", "CompactWitness.jl"))
using .CompactWitness

fixed_value = 15 // 1
problem, status, dual_solution, primal_solution, elapsed, error_code =
    solve_three_point_problem(
        3,
        1 // 2,
        2,
        2;
        fixed_objective=fixed_value,
        prec=192,
        duality_gap_threshold=1e-25,
        dual_error_threshold=1e-20,
        primal_error_threshold=1e-20,
        need_primal_feasible=true,
    )

println("status=", status)
println("fixed_objective=", fixed_value)
println("elapsed=", elapsed)
println("error_code=", error_code)

settings = RoundingSettings(
    kernel_use_dual=false,
    approximation_decimals=20,
    regularization=1e-20,
    redundancyfactor=12,
    pseudo=true,
    pseudo_columnfactor=1.10,
)
success, exact_primal = exact_solution(
    problem,
    dual_solution,
    primal_solution;
    settings=settings,
)
println("exact_rounding_success=", success)

if !success
    error("small fixed-objective exact rounding failed")
end

verification = verify_target_exact_solution(
    exact_primal;
    dimension=3,
    costheta=1 // 2,
    d2=2,
    d3=2,
    expected_objective=fixed_value,
)
println("exact_types_ok=", verification.exact_types_ok)
println("exact_structure_ok=", verification.structure_ok)
println("exact_affine_ok=", verification.affine_ok)
println("exact_objective_ok=", verification.objective_ok)
println("exact_psd_blocks=", verification.block_count)
println("exact_verification_valid=", verification.valid)
if !verification.valid
    error("small exact solution failed exact rational verification")
end

factorizations = [
    pivoted_ldl(matrix)
    for matrix in values(matrixvars(exact_primal))
]
all(
    reconstruct_ldl(factorization) == matrix
    for (factorization, matrix) in
        zip(factorizations, values(matrixvars(exact_primal)))
) || error("exact factorization audit failed")
factor_rank_sum = sum(factorization.rank for factorization in factorizations)
matrix_entry_count = sum(
    size(matrix, 1) * (size(matrix, 1) + 1) ÷ 2
    for matrix in values(matrixvars(exact_primal))
)
println("compact_ldl_rank_sum=", factor_rank_sum)
println("compact_matrix_rational_entries=", matrix_entry_count)

compact_output = get(
    ENV,
    "KN11_SMOKE_COMPACT_OUTPUT",
    joinpath("build", "smoke-exact-witness.bin"),
)
named_blocks = sort(
    [
        (
            canonical_block_name(key),
            matrix,
        )
        for (key, matrix) in matrixvars(exact_primal)
    ];
    by=first,
)
compact_metadata = write_compact_witness(compact_output, named_blocks)
compact_metadata.rational_count == matrix_entry_count ||
    error("compact witness rational count differs from the matrix audit")
println("compact_witness=", compact_output)
println("compact_witness_sha256=", compact_metadata.sha256)
println("compact_witness_bytes=", compact_metadata.size_bytes)
