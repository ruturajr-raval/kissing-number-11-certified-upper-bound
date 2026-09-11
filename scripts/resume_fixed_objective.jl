using KissingNumber11Certificate
using ClusteredLowRankSolver
using LinearAlgebra
using Serialization
using SHA

include(joinpath(@__DIR__, "..", "src", "NumericalScreening.jl"))
include(joinpath(@__DIR__, "..", "src", "CheckpointRecovery.jl"))
using .NumericalScreening
using .CheckpointRecovery

const ORIGINAL_CHECKPOINT = get(
    ENV,
    "KN11_ORIGINAL_FIXED_CHECKPOINT",
    joinpath("build", "degree17-fixed-checkpoint.jls"),
)
const RESUME_CHECKPOINT = get(
    ENV,
    "KN11_RESUME_FIXED_CHECKPOINT",
    joinpath("build", "degree17-fixed-resume-checkpoint.jls"),
)
const OUTPUT = get(
    ENV,
    "KN11_FIXED_OUTPUT",
    joinpath("build", "degree17-fixed-86899-over-100.jls"),
)
const EXPECTED_ORIGINAL_SHA256 =
    "d1c012f01018024b33e61da738ee5866bd070dec899c71508a11e1c09514e6e1"
const PRECISION = 384
const MAX_ITERATIONS = 25
const MAX_INPUT_BYTES = 16 * 1024^3
const MAX_RESIDUAL = BigFloat("1e-35")
const MIN_EIGENVALUE = BigFloat("-1e-34")
const MAX_OBJECTIVE_ERROR = BigFloat("1e-35")
const MAX_PRIMAL_ERROR = BigFloat("1e-40")
const EXPECTED_RESIDUAL_COUNT = 1497

BLAS.set_num_threads(1)

file_sha256(path) = open(stream -> bytes2hex(sha256(stream)), path)

ispath(OUTPUT) && error("refusing to replace an existing fixed-objective bundle")

solver_script = joinpath(@__DIR__, "solve_fixed_objective.jl")
helper_source = joinpath(@__DIR__, "..", "src", "NumericalScreening.jl")
checkpoint_source = joinpath(@__DIR__, "..", "src", "CheckpointRecovery.jl")
checkpoint_root = joinpath(@__DIR__, "..", "build")
original_specification = problem_specification(
    mode="fixed-objective",
    dimension=TARGET_DIMENSION,
    costheta=TARGET_COSTHETA,
    d2=TARGET_DEGREE,
    d3=TARGET_DEGREE,
    fixed_objective=TARGET_OBJECTIVE,
    precision=PRECISION,
    script_path=solver_script,
)
execution_specification = problem_specification(
    mode="fixed-objective-recovery",
    dimension=TARGET_DIMENSION,
    costheta=TARGET_COSTHETA,
    d2=TARGET_DEGREE,
    d3=TARGET_DEGREE,
    fixed_objective=TARGET_OBJECTIVE,
    precision=PRECISION,
    script_path=@__FILE__,
)
original_snapshot = read_checkpoint_snapshot(
    ORIGINAL_CHECKPOINT;
    max_bytes=MAX_INPUT_BYTES,
    allowed_root=checkpoint_root,
    expected_sha256=EXPECTED_ORIGINAL_SHA256,
)
original_checkpoint = validate_checkpoint(
    original_snapshot.checkpoint,
    original_specification,
    "fixed-objective-checkpoint",
)
original_sha256 = original_snapshot.sha256

recovery_fields = [
    "schema_version=$(BUNDLE_SCHEMA_VERSION)",
    "original_specification=$(original_specification.digest)",
    "execution_specification=$(execution_specification.digest)",
    "original_checkpoint_sha256=$original_sha256",
    "helper_source_sha256=$(file_sha256(helper_source))",
    "checkpoint_source_sha256=$(file_sha256(checkpoint_source))",
    "julia_version=$(VERSION)",
    "precision=$PRECISION",
    "max_iterations=$MAX_ITERATIONS",
    "checkpoint_interval_seconds=0",
    "maximum_objective_error=$MAX_OBJECTIVE_ERROR",
    "maximum_affine_residual=$MAX_RESIDUAL",
    "minimum_matrix_eigenvalue=$MIN_EIGENVALUE",
    "maximum_primal_error=$MAX_PRIMAL_ERROR",
]
recovery_specification = (
    fields=recovery_fields,
    digest=bytes2hex(sha256(join(recovery_fields, "\n") * "\n")),
)

resume = if ispath(RESUME_CHECKPOINT)
    resume_snapshot = read_checkpoint_snapshot(
        RESUME_CHECKPOINT;
        max_bytes=MAX_INPUT_BYTES,
        allowed_root=checkpoint_root,
    )
    validate_checkpoint(
        resume_snapshot.checkpoint,
        recovery_specification,
        "fixed-objective-resume-checkpoint",
    )
else
    original_checkpoint
end

latest_measurements = Ref{Any}(resume.measurements)
serialize_checkpoint = checkpoint_callback(
    RESUME_CHECKPOINT,
    recovery_specification,
    "fixed-objective-resume-checkpoint";
    interval_seconds=0,
)
save_callback = function(measurements, dual_solution, primal_solution)
    latest_measurements[] = measurements
    serialize_checkpoint(measurements, dual_solution, primal_solution)
    return nothing
end

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
        dualsol=resume.dual_solution,
        primalsol=resume.primal_solution,
    )

measurements = latest_measurements[]
atomic_serialize(
    RESUME_CHECKPOINT,
    (
        schema_version=BUNDLE_SCHEMA_VERSION,
        kind="fixed-objective-resume-checkpoint",
        specification_digest=recovery_specification.digest,
        measurements=measurements,
        dual_solution=dual_solution,
        primal_solution=primal_solution,
    ),
)
objective_value = objvalue(
    original_objective(TARGET_DEGREE, TARGET_DEGREE),
    primal_solution,
)
objective_error = abs(objective_value - BigFloat(TARGET_OBJECTIVE))
residual = sampled_numerical_residual_summary(
    problem,
    primal_solution;
    precision=PRECISION,
)
minimum_eigenvalue = sampled_minimum_matrix_eigenvalue(
    primal_solution;
    precision=PRECISION,
)
primal_error = abs(BigFloat(measurements.p_error))
status_ok =
    status isa PrimalFeasible ||
    status isa Feasible ||
    status isa NearOptimal ||
    status isa Optimal
finite_values =
    isfinite(objective_value) &&
    isfinite(objective_error) &&
    residual.all_finite &&
    isfinite(minimum_eigenvalue) &&
    isfinite(primal_error)
accepted =
    error_code == 0 &&
    status_ok &&
    finite_values &&
    objective_error <= MAX_OBJECTIVE_ERROR &&
    residual.scalar_count == EXPECTED_RESIDUAL_COUNT &&
    residual.maximum_absolute <= MAX_RESIDUAL &&
    minimum_eigenvalue >= MIN_EIGENVALUE &&
    primal_error <= MAX_PRIMAL_ERROR

println("status=", status)
println("resume_iteration=", measurements.iter)
println("primal_error=", primal_error)
println("fixed_objective=", TARGET_OBJECTIVE)
println("measured_objective=", objective_value)
println("objective_error=", objective_error)
println("maximum_affine_residual=", residual.maximum_absolute)
println("residual_scalar_count=", residual.scalar_count)
println("minimum_matrix_eigenvalue=", minimum_eigenvalue)
println("elapsed=", elapsed)
println("error_code=", error_code)
println("finite_values=", finite_values)
println("accepted=", accepted)

accepted || error("resumed fixed-objective solve did not pass every gate")

resume_snapshot = read_checkpoint_snapshot(
    RESUME_CHECKPOINT;
    max_bytes=MAX_INPUT_BYTES,
    allowed_root=checkpoint_root,
)
validate_checkpoint(
    resume_snapshot.checkpoint,
    recovery_specification,
    "fixed-objective-resume-checkpoint",
)
resume_checkpoint_sha256 = resume_snapshot.sha256
ispath(OUTPUT) && error("refusing to replace an existing fixed-objective bundle")
atomic_serialize(
    OUTPUT,
    (
        schema_version=BUNDLE_SCHEMA_VERSION,
        kind="fixed-objective",
        specification=original_specification,
        recovery_specification=recovery_specification,
        original_checkpoint_sha256=original_sha256,
        resume_checkpoint_sha256=resume_checkpoint_sha256,
        julia_version=string(VERSION),
        status=string(status),
        status_type=string(nameof(typeof(status))),
        dual_solution=dual_solution,
        primal_solution=primal_solution,
        measurements=measurements,
        elapsed=elapsed,
        error_code=error_code,
        objective=objective_value,
        objective_error=objective_error,
        residual=residual,
        minimum_eigenvalue=minimum_eigenvalue,
        accepted=accepted,
    ),
)
