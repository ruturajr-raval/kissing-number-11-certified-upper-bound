using KissingNumber11Certificate
using ClusteredLowRankSolver

problem, status, dual_solution, primal_solution, elapsed, error_code =
    solve_three_point_problem(
        3,
        1 // 2,
        2,
        2;
        prec=128,
        duality_gap_threshold=1e-12,
        dual_error_threshold=1e-12,
        primal_error_threshold=1e-12,
    )

value = objvalue(problem, primal_solution)
println("status=", status)
println("objective=", value)
println("elapsed=", elapsed)
println("error_code=", error_code)

if !(10 < value < 20)
    error("unexpected degree-2 smoke objective: $value")
end
