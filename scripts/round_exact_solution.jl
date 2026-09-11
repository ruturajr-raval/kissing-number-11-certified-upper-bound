using KissingNumber11Certificate
using ClusteredLowRankSolver
using Random
using Serialization
using SHA

include(joinpath(@__DIR__, "..", "src", "CheckpointRecovery.jl"))
include(joinpath(@__DIR__, "..", "src", "PortableExactSolution.jl"))
include(joinpath(@__DIR__, "..", "src", "StrictInteriorVerification.jl"))
using .CheckpointRecovery
using .PortableExactSolution
using .StrictInteriorVerification

const INPUT = get(
    ENV,
    "KN11_FIXED_OUTPUT",
    joinpath("build", "degree17-fixed-86899-over-100.jls"),
)
const OUTPUT = get(
    ENV,
    "KN11_EXACT_OUTPUT",
    joinpath("build", "degree17-exact-86899-over-100.jls"),
)
const PROJECTION_OUTPUT = get(
    ENV,
    "KN11_PROJECTION_OUTPUT",
    joinpath("build", "degree17-projected-86899-over-100.jls"),
)
const PRECISION = parse(Int, get(ENV, "KN11_PRECISION", "384"))
const MAX_INPUT_BYTES = 512 * 1024^2
const MAX_PROJECTION_BYTES = 16 * 1024^3
const EXPECTED_INPUT_SHA256 =
    "ceed3e884625b2ff6365ea6c68eecdcdddd900d8aac0fa4d9955d8f1894f003a"
const ROUNDING_SEED = 11_017

ispath(OUTPUT) && error("refusing to replace an existing exact output")

expected_specification = problem_specification(
    mode="fixed-objective",
    dimension=TARGET_DIMENSION,
    costheta=TARGET_COSTHETA,
    d2=TARGET_DEGREE,
    d3=TARGET_DEGREE,
    fixed_objective=TARGET_OBJECTIVE,
    precision=PRECISION,
    script_path=joinpath(@__DIR__, "solve_fixed_objective.jl"),
)
input_snapshot = read_checkpoint_snapshot(
    INPUT;
    max_bytes=MAX_INPUT_BYTES,
    allowed_root=joinpath(@__DIR__, "..", "build"),
    expected_sha256=EXPECTED_INPUT_SHA256,
)
bundle = input_snapshot.checkpoint
hasproperty(bundle, :schema_version) ||
    error("fixed-objective bundle has no schema version")
bundle.schema_version == BUNDLE_SCHEMA_VERSION ||
    error("fixed-objective bundle uses an unsupported schema")
hasproperty(bundle, :kind) && bundle.kind == "fixed-objective" ||
    error("input is not a fixed-objective bundle")
hasproperty(bundle, :specification) ||
    error("fixed-objective bundle has no problem specification")
bundle.specification == expected_specification ||
    error("fixed-objective bundle is not bound to the current canonical problem")
hasproperty(bundle, :julia_version) &&
    bundle.julia_version == string(VERSION) ||
    error("fixed-objective bundle was produced by a different Julia runtime")
hasproperty(bundle, :accepted) && bundle.accepted ||
    error("fixed-objective bundle did not pass its numerical gates")
hasproperty(bundle, :dual_solution) ||
    error("fixed-objective bundle has no dual solution")
hasproperty(bundle, :primal_solution) ||
    error("fixed-objective bundle has no primal solution")

canonical_problem = build_three_point_problem(
    TARGET_DIMENSION,
    TARGET_COSTHETA,
    TARGET_DEGREE,
    TARGET_DEGREE;
    fixed_objective=TARGET_OBJECTIVE,
)
settings = RoundingSettings(
    approximation_decimals=60,
    regularization=1e-50,
    redundancyfactor=8,
    pseudo=true,
    pseudo_columnfactor=1.05,
)
Random.seed!(ROUNDING_SEED)
checkpoint_source = joinpath(
    @__DIR__,
    "..",
    "src",
    "CheckpointRecovery.jl",
)
checkpoint_source_sha256 =
    open(io -> bytes2hex(sha256(io)), checkpoint_source)
verification_source = joinpath(
    @__DIR__,
    "..",
    "src",
    "StrictInteriorVerification.jl",
)
verification_source_sha256 =
    open(io -> bytes2hex(sha256(io)), verification_source)
portable_source = joinpath(
    @__DIR__,
    "..",
    "src",
    "PortableExactSolution.jl",
)
portable_source_sha256 =
    open(io -> bytes2hex(sha256(io)), portable_source)
rounding_fields = [
    "schema_version=$(BUNDLE_SCHEMA_VERSION)",
    "source_specification=$(expected_specification.digest)",
    "fixed_bundle_sha256=$(input_snapshot.sha256)",
    "julia_version=$(VERSION)",
    "rounding_script_sha256=$(open(io -> bytes2hex(sha256(io)), @__FILE__))",
    "checkpoint_source_sha256=$checkpoint_source_sha256",
    "portable_source_sha256=$portable_source_sha256",
    "verification_source_sha256=$verification_source_sha256",
    "rounding_mode=strict-interior-direct-projection",
    "projection_encoding=$PORTABLE_EXACT_SOLUTION_ENCODING",
    "rounding_seed=$ROUNDING_SEED",
    "approximation_decimals=60",
    "regularization=1e-50",
    "redundancyfactor=8",
    "pseudo=true",
    "pseudo_columnfactor=1.05",
]
rounding_specification = (
    fields=rounding_fields,
    digest=bytes2hex(sha256(join(rounding_fields, "\n") * "\n")),
)

projection_snapshot = if ispath(PROJECTION_OUTPUT)
    println("exact_projection_resume=", PROJECTION_OUTPUT)
    read_checkpoint_snapshot(
        PROJECTION_OUTPUT;
        max_bytes=MAX_PROJECTION_BYTES,
        allowed_root=joinpath(@__DIR__, "..", "build"),
    )
else
    projected_solution, correct_slacks =
        ClusteredLowRankSolver.project_to_affine_space(
            canonical_problem,
            bundle.primal_solution;
            settings=settings,
        )
    println("exact_projection_slacks=", correct_slacks)
    correct_slacks ||
        error("exact projection did not satisfy every affine equality")
    portable_solution = nothing
    conversion_seconds = @elapsed begin
        portable_solution = encode_exact_solution(projected_solution)
    end
    println(
        "exact_projection_portable_conversion_seconds=",
        conversion_seconds,
    )
    atomic_serialize(
        PROJECTION_OUTPUT,
        (
            schema_version=BUNDLE_SCHEMA_VERSION,
            kind="exact-projection-checkpoint",
            source_specification=expected_specification,
            rounding_specification=rounding_specification,
            fixed_bundle_sha256=input_snapshot.sha256,
            correct_slacks=correct_slacks,
            exact_solution_encoding=PORTABLE_EXACT_SOLUTION_ENCODING,
            portable_exact_solution=portable_solution,
        ),
    )
    read_checkpoint_snapshot(
        PROJECTION_OUTPUT;
        max_bytes=MAX_PROJECTION_BYTES,
        allowed_root=joinpath(@__DIR__, "..", "build"),
    )
end
projection_bundle = projection_snapshot.checkpoint
hasproperty(projection_bundle, :schema_version) &&
    projection_bundle.schema_version == BUNDLE_SCHEMA_VERSION ||
    error("projection checkpoint uses an unsupported schema")
hasproperty(projection_bundle, :kind) &&
    projection_bundle.kind == "exact-projection-checkpoint" ||
    error("projection checkpoint has the wrong kind")
hasproperty(projection_bundle, :source_specification) &&
    projection_bundle.source_specification == expected_specification ||
    error("projection checkpoint has the wrong source specification")
hasproperty(projection_bundle, :rounding_specification) &&
    projection_bundle.rounding_specification == rounding_specification ||
    error("projection checkpoint has the wrong rounding specification")
hasproperty(projection_bundle, :fixed_bundle_sha256) &&
    projection_bundle.fixed_bundle_sha256 == input_snapshot.sha256 ||
    error("projection checkpoint is bound to a different numerical input")
hasproperty(projection_bundle, :correct_slacks) &&
    projection_bundle.correct_slacks ||
    error("projection checkpoint did not satisfy the projected affine system")
hasproperty(projection_bundle, :exact_solution_encoding) &&
    projection_bundle.exact_solution_encoding ==
    PORTABLE_EXACT_SOLUTION_ENCODING ||
    error("projection checkpoint has an unsupported exact-solution encoding")
hasproperty(projection_bundle, :portable_exact_solution) ||
    error("projection checkpoint has no portable exact solution")
exact_solution =
    restore_exact_solution(projection_bundle.portable_exact_solution)
println("exact_projection_checkpoint_sha256=", projection_snapshot.sha256)
println("exact_projection_checkpoint_bytes=", projection_snapshot.byte_count)

sample_certificate =
    sample_unisolvence_certificate(TARGET_DEGREE, TARGET_DEGREE)
sample_certificate.univariate_distinct ||
    error("canonical univariate sample set is not unisolvent")
sample_certificate.full_rank ||
    error("canonical trivariate sample set is not unisolvent")
verification = verify_strictly_positive_exact_solution(
    canonical_problem,
    exact_solution;
    expected_objective=TARGET_OBJECTIVE,
    objective_functional=original_objective(TARGET_DEGREE, TARGET_DEGREE),
    verbose=true,
)
verification = merge(
    verification,
    (
        target_binding_ok=true,
        sample_certificate=sample_certificate,
    ),
)
println("exact_types_ok=", verification.exact_types_ok)
println("exact_structure_ok=", verification.structure_ok)
println("exact_affine_ok=", verification.affine_ok)
println("exact_objective_ok=", verification.objective_ok)
println("exact_psd_blocks=", verification.block_count)
println("exact_positive_definite=", verification.positive_definite_ok)
println("exact_verification_valid=", verification.valid)
verification.valid ||
    error("rounded solution failed canonical exact verification")

portable_verification = merge(
    verification,
    (
        objective_value=PortableExactSolution.portable_rational(
            verification.objective_value,
        ),
    ),
)
ispath(OUTPUT) && error("refusing to replace an existing exact output")
atomic_serialize(
    OUTPUT,
    (
        schema_version=BUNDLE_SCHEMA_VERSION,
        kind="exact-solution-temporary",
        source_specification=expected_specification,
        rounding_specification=rounding_specification,
        objective=PortableExactSolution.portable_rational(TARGET_OBJECTIVE),
        dimension=TARGET_DIMENSION,
        degree=TARGET_DEGREE,
        projection_checkpoint_sha256=projection_snapshot.sha256,
        projection_checkpoint_bytes=projection_snapshot.byte_count,
        exact_solution_encoding=PORTABLE_EXACT_SOLUTION_ENCODING,
        portable_exact_solution=projection_bundle.portable_exact_solution,
        verification=portable_verification,
    ),
)
