using KissingNumber11Certificate
using ClusteredLowRankSolver
using LinearAlgebra

const OUTPUT = get(
    ENV,
    "KN11_NUMERICAL_OUTPUT",
    joinpath("build", "degree17-numerical.jls"),
)
const CHECKPOINT = get(
    ENV,
    "KN11_NUMERICAL_CHECKPOINT",
    joinpath("build", "degree17-numerical-checkpoint.jls"),
)
const PRECISION = parse(Int, get(ENV, "KN11_PRECISION", "256"))
const MAX_ITERATIONS = parse(Int, get(ENV, "KN11_MAX_ITERATIONS", "500"))
const CHECKPOINT_SECONDS =
    parse(Float64, get(ENV, "KN11_CHECKPOINT_SECONDS", "1800"))
const MAX_RESIDUAL = BigFloat("1e-25")
const MIN_EIGENVALUE = BigFloat("-1e-24")
const MAX_DUALITY_GAP = BigFloat("1e-25")

BLAS.set_num_threads(1)

specification = problem_specification(
    mode="numerical-reproduction",
    dimension=TARGET_DIMENSION,
    costheta=TARGET_COSTHETA,
    d2=TARGET_DEGREE,
    d3=TARGET_DEGREE,
    precision=PRECISION,
    script_path=@__FILE__,
)
resume = load_compatible_checkpoint(
    CHECKPOINT,
    specification,
    "numerical-reproduction-checkpoint",
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
    "numerical-reproduction-checkpoint";
    interval_seconds=CHECKPOINT_SECONDS,
)

problem, status, dual_solution, primal_solution, elapsed, error_code =
    solve_three_point_problem(
        TARGET_DIMENSION,
        TARGET_COSTHETA,
        TARGET_DEGREE,
        TARGET_DEGREE;
        prec=PRECISION,
        maxiterations=MAX_ITERATIONS,
        duality_gap_threshold=1e-30,
        dual_error_threshold=1e-30,
        primal_error_threshold=1e-30,
        solution_callback=save_callback,
        resume_keywords...,
    )

objective_value = objvalue(problem, primal_solution)
dual_objective_value = dualobjvalue(problem, dual_solution)
duality_gap = abs(objective_value - dual_objective_value) /
              max(BigFloat(1), abs(objective_value) + abs(dual_objective_value))
residual = numerical_residual_summary(problem, primal_solution)
minimum_eigenvalue = minimum_matrix_eigenvalue(primal_solution)
status_ok = status isa Optimal
accepted =
    error_code == 0 &&
    status_ok &&
    isfinite(objective_value) &&
    objective_value < BigFloat("868.84") &&
    duality_gap <= MAX_DUALITY_GAP &&
    residual.maximum_absolute <= MAX_RESIDUAL &&
    minimum_eigenvalue >= MIN_EIGENVALUE

println("status=", status)
println("objective=", objective_value)
println("dual_objective=", dual_objective_value)
println("duality_gap=", duality_gap)
println("maximum_affine_residual=", residual.maximum_absolute)
println("minimum_matrix_eigenvalue=", minimum_eigenvalue)
println("elapsed=", elapsed)
println("error_code=", error_code)
println("accepted=", accepted)

accepted || error("degree-17 numerical reproduction did not pass every gate")

atomic_serialize(
    OUTPUT,
    (
        schema_version=BUNDLE_SCHEMA_VERSION,
        kind="numerical-reproduction",
        specification=specification,
        julia_version=string(VERSION),
        status=string(status),
        status_type=string(nameof(typeof(status))),
        dual_solution=dual_solution,
        primal_solution=primal_solution,
        elapsed=elapsed,
        error_code=error_code,
        objective=objective_value,
        dual_objective=dual_objective_value,
        duality_gap=duality_gap,
        maximum_allowed_duality_gap=MAX_DUALITY_GAP,
        maximum_allowed_affine_residual=MAX_RESIDUAL,
        minimum_allowed_matrix_eigenvalue=MIN_EIGENVALUE,
        residual=residual,
        minimum_eigenvalue=minimum_eigenvalue,
        accepted=accepted,
    ),
)
