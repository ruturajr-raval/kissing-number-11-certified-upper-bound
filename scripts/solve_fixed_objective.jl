using KissingNumber11Certificate
using ClusteredLowRankSolver
using LinearAlgebra

const OUTPUT = get(
    ENV,
    "KN11_FIXED_OUTPUT",
    joinpath("build", "degree17-fixed-86899-over-100.jls"),
)
const CHECKPOINT = get(
    ENV,
    "KN11_FIXED_CHECKPOINT",
    joinpath("build", "degree17-fixed-checkpoint.jls"),
)
const PRECISION = parse(Int, get(ENV, "KN11_PRECISION", "384"))
const MAX_ITERATIONS = parse(Int, get(ENV, "KN11_MAX_ITERATIONS", "500"))
const CHECKPOINT_SECONDS =
    parse(Float64, get(ENV, "KN11_CHECKPOINT_SECONDS", "1800"))
const MAX_RESIDUAL = BigFloat(get(ENV, "KN11_MAX_RESIDUAL", "1e-35"))
const MIN_EIGENVALUE = BigFloat(get(ENV, "KN11_MIN_EIGENVALUE", "-1e-34"))
const MAX_OBJECTIVE_ERROR =
    BigFloat(get(ENV, "KN11_MAX_OBJECTIVE_ERROR", "1e-35"))

BLAS.set_num_threads(1)

specification = problem_specification(
    mode="fixed-objective",
    dimension=TARGET_DIMENSION,
    costheta=TARGET_COSTHETA,
    d2=TARGET_DEGREE,
    d3=TARGET_DEGREE,
    fixed_objective=TARGET_OBJECTIVE,
    precision=PRECISION,
    script_path=@__FILE__,
)
resume = load_compatible_checkpoint(
    CHECKPOINT,
    specification,
    "fixed-objective-checkpoint",
)
resume_keywords = isnothing(resume) ?
    (;) :
    (
        dualsol=resume.dual_solution,
        primalsol=resume.primal_solution,
    )
save_callback = checkpoint_callback(
    CHECKPOINT,
    specification,
    "fixed-objective-checkpoint";
    interval_seconds=CHECKPOINT_SECONDS,
)

problem, status, dual_solution, primal_solution, elapsed, error_code =
    solve_three_point_problem(
        TARGET_DIMENSION,
        TARGET_COSTHETA,
        TARGET_DEGREE,
        TARGET_DEGREE;
        fixed_objective=TARGET_OBJECTIVE,
        prec=PRECISION,
        maxiterations=MAX_ITERATIONS,
        duality_gap_threshold=1e-50,
        dual_error_threshold=1e-40,
        primal_error_threshold=1e-40,
        need_primal_feasible=true,
        solution_callback=save_callback,
        resume_keywords...,
    )

objective_value = objvalue(
    original_objective(TARGET_DEGREE, TARGET_DEGREE),
    primal_solution,
)
objective_error = abs(objective_value - BigFloat(TARGET_OBJECTIVE))
residual = numerical_residual_summary(problem, primal_solution)
minimum_eigenvalue = minimum_matrix_eigenvalue(primal_solution)
status_ok =
    status isa PrimalFeasible ||
    status isa Feasible ||
    status isa NearOptimal ||
    status isa Optimal
accepted =
    error_code == 0 &&
    status_ok &&
    objective_error <= MAX_OBJECTIVE_ERROR &&
    residual.maximum_absolute <= MAX_RESIDUAL &&
    minimum_eigenvalue >= MIN_EIGENVALUE

println("status=", status)
println("fixed_objective=", TARGET_OBJECTIVE)
println("measured_objective=", objective_value)
println("objective_error=", objective_error)
println("maximum_affine_residual=", residual.maximum_absolute)
println("minimum_matrix_eigenvalue=", minimum_eigenvalue)
println("elapsed=", elapsed)
println("error_code=", error_code)
println("accepted=", accepted)

accepted || error("fixed-objective solve did not pass every gate")

atomic_serialize(
    OUTPUT,
    (
        schema_version=BUNDLE_SCHEMA_VERSION,
        kind="fixed-objective",
        specification=specification,
        julia_version=string(VERSION),
        status=string(status),
        status_type=string(nameof(typeof(status))),
        dual_solution=dual_solution,
        primal_solution=primal_solution,
        elapsed=elapsed,
        error_code=error_code,
        objective=objective_value,
        objective_error=objective_error,
        residual=residual,
        minimum_eigenvalue=minimum_eigenvalue,
        accepted=accepted,
    ),
)
