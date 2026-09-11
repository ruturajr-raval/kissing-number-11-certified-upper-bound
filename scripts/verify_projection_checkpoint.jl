using KissingNumber11Certificate
using ClusteredLowRankSolver
using Serialization
using SHA

include(joinpath(@__DIR__, "..", "src", "CheckpointRecovery.jl"))
include(joinpath(@__DIR__, "..", "src", "PortableExactSolution.jl"))
include(joinpath(@__DIR__, "..", "src", "StrictInteriorVerification.jl"))
include(joinpath(@__DIR__, "..", "src", "ParallelExactVerification.jl"))
using .CheckpointRecovery
using .PortableExactSolution
using .StrictInteriorVerification
using .ParallelExactVerification

const INPUT = get(
    ENV,
    "KN11_PROJECTION_OUTPUT",
    joinpath("build", "degree17-projected-86899-over-100.jls"),
)
const OUTPUT = get(
    ENV,
    "KN11_EXACT_OUTPUT",
    joinpath("build", "degree17-exact-86899-over-100.jls"),
)
const PRECISION = parse(Int, get(ENV, "KN11_PRECISION", "384"))
const MAX_INPUT_BYTES = 16 * 1024^3
const EXPECTED_FIXED_BUNDLE_SHA256 =
    "ceed3e884625b2ff6365ea6c68eecdcdddd900d8aac0fa4d9955d8f1894f003a"
const ROUNDING_SEED = 11_017
const AFFINE_CHUNK_SIZE = 100
const AFFINE_WORKER_THREADS = 2
const AFFINE_CHUNK_SPEC = get(ENV, "KN11_AFFINE_CHUNK", "")
const VERIFICATION_MODE =
    "process-isolated-threaded-affine-sequential-arb-cholesky-v2"

Threads.nthreads() == AFFINE_WORKER_THREADS ||
    error("exact verification requires $AFFINE_WORKER_THREADS Julia threads")
isempty(AFFINE_CHUNK_SPEC) &&
    ispath(OUTPUT) &&
    error("refusing to replace an existing exact output")

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

rounding_script = joinpath(@__DIR__, "round_exact_solution.jl")
checkpoint_source =
    joinpath(@__DIR__, "..", "src", "CheckpointRecovery.jl")
portable_source =
    joinpath(@__DIR__, "..", "src", "PortableExactSolution.jl")
strict_verification_source =
    joinpath(@__DIR__, "..", "src", "StrictInteriorVerification.jl")
rounding_fields = [
    "schema_version=$(BUNDLE_SCHEMA_VERSION)",
    "source_specification=$(expected_specification.digest)",
    "fixed_bundle_sha256=$EXPECTED_FIXED_BUNDLE_SHA256",
    "julia_version=$(VERSION)",
    "rounding_script_sha256=$(open(io -> bytes2hex(sha256(io)), rounding_script))",
    "checkpoint_source_sha256=$(open(io -> bytes2hex(sha256(io)), checkpoint_source))",
    "portable_source_sha256=$(open(io -> bytes2hex(sha256(io)), portable_source))",
    "verification_source_sha256=$(open(io -> bytes2hex(sha256(io)), strict_verification_source))",
    "rounding_mode=strict-interior-direct-projection",
    "projection_encoding=$PORTABLE_EXACT_SOLUTION_ENCODING",
    "rounding_seed=$ROUNDING_SEED",
    "approximation_decimals=60",
    "regularization=1e-50",
    "redundancyfactor=8",
    "pseudo=true",
    "pseudo_columnfactor=1.05",
]
expected_rounding_specification = (
    fields=rounding_fields,
    digest=bytes2hex(sha256(join(rounding_fields, "\n") * "\n")),
)

projection_snapshot = read_checkpoint_snapshot(
    INPUT;
    max_bytes=MAX_INPUT_BYTES,
    allowed_root=joinpath(@__DIR__, "..", "build"),
)
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
    projection_bundle.rounding_specification ==
    expected_rounding_specification ||
    error("projection checkpoint has the wrong rounding specification")
hasproperty(projection_bundle, :fixed_bundle_sha256) &&
    projection_bundle.fixed_bundle_sha256 ==
    EXPECTED_FIXED_BUNDLE_SHA256 ||
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

parallel_source =
    joinpath(@__DIR__, "..", "src", "ParallelExactVerification.jl")
function verification_source_hashes()
    return (
        script=open(io -> bytes2hex(sha256(io)), @__FILE__),
        parallel=open(io -> bytes2hex(sha256(io)), parallel_source),
        strict=open(
            io -> bytes2hex(sha256(io)),
            strict_verification_source,
        ),
        portable=open(io -> bytes2hex(sha256(io)), portable_source),
    )
end

initial_verification_source_hashes = verification_source_hashes()
verification_fields = [
    "schema_version=$(BUNDLE_SCHEMA_VERSION)",
    "source_specification=$(expected_specification.digest)",
    "rounding_specification=$(expected_rounding_specification.digest)",
    "projection_checkpoint_sha256=$(projection_snapshot.sha256)",
    "julia_version=$(VERSION)",
    "verification_script_sha256=$(initial_verification_source_hashes.script)",
    "parallel_verification_source_sha256=$(initial_verification_source_hashes.parallel)",
    "strict_verification_source_sha256=$(initial_verification_source_hashes.strict)",
    "portable_source_sha256=$(initial_verification_source_hashes.portable)",
    "verification_mode=$VERIFICATION_MODE",
    "affine_chunk_size=$AFFINE_CHUNK_SIZE",
    "affine_worker_threads=$AFFINE_WORKER_THREADS",
]
verification_specification = (
    fields=verification_fields,
    digest=bytes2hex(sha256(join(verification_fields, "\n") * "\n")),
)
expected_verification_digest =
    get(ENV, "KN11_EXPECTED_VERIFICATION_SPECIFICATION", "")
isempty(expected_verification_digest) ||
    verification_specification.digest == expected_verification_digest ||
    error("verification worker source does not match the coordinator")

println("exact_projection_resume=", INPUT)
println("exact_projection_checkpoint_sha256=", projection_snapshot.sha256)
println("exact_projection_checkpoint_bytes=", projection_snapshot.byte_count)
println("exact_affine_threads=", Threads.nthreads())
println("exact_affine_batch_size=", max(1, 2 * Threads.nthreads()))
println("exact_affine_chunk_size=", AFFINE_CHUNK_SIZE)

canonical_problem = build_three_point_problem(
    TARGET_DIMENSION,
    TARGET_COSTHETA,
    TARGET_DEGREE,
    TARGET_DEGREE;
    fixed_objective=TARGET_OBJECTIVE,
)

function parse_affine_chunk(specification, problem)
    fields = split(specification, ":")
    length(fields) == 3 ||
        error("affine chunk must be constraint:first:last")
    constraint_index, first_sample, last_sample = parse.(Int, fields)
    problem_constraints = constraints(problem)
    1 <= constraint_index <= length(problem_constraints) ||
        error("affine chunk constraint index is out of range")
    sample_count =
        length(problem_constraints[constraint_index].samples)
    1 <= first_sample <= last_sample <= sample_count ||
        error("affine chunk sample range is out of bounds")
    return (
        constraint_index=constraint_index,
        first_sample=first_sample,
        last_sample=last_sample,
        sample_count=sample_count,
    )
end

function affine_worker_command(chunk, verification_digest)
    project_root = normpath(joinpath(@__DIR__, ".."))
    command = `$(Base.julia_cmd()) --startup-file=no --history-file=no --project=$project_root $(abspath(@__FILE__))`
    return addenv(
        command,
        "KN11_AFFINE_CHUNK" =>
            "$(chunk.constraint_index):$(chunk.first_sample):$(chunk.last_sample)",
        "KN11_EXPECTED_VERIFICATION_SPECIFICATION" => verification_digest,
        "KN11_PROJECTION_OUTPUT" => abspath(INPUT),
        "KN11_EXACT_OUTPUT" => abspath(OUTPUT),
        "KN11_PRECISION" => string(PRECISION),
    )
end

if !isempty(AFFINE_CHUNK_SPEC)
    chunk = parse_affine_chunk(AFFINE_CHUNK_SPEC, canonical_problem)
    exact_solution =
        restore_exact_solution(projection_bundle.portable_exact_solution)
    result = verify_parallel_exact_affine_sample_range(
        canonical_problem,
        exact_solution,
        chunk.constraint_index,
        chunk.first_sample,
        chunk.last_sample;
        verbose=true,
    )
    println("exact_affine_chunk_valid=", result.valid)
    println("exact_affine_chunk_residuals=", result.residual_count)
    result.valid ||
        error(
            "exact affine chunk failed at constraint " *
            "$(result.failed_constraint), sample $(result.failed_sample)",
        )
    flush(stdout)
    exit(0)
end

println("exact_verification_stage=affine-worker-processes")
chunks = affine_sample_chunks(
    canonical_problem;
    chunk_size=AFFINE_CHUNK_SIZE,
)
for (index, chunk) in enumerate(chunks)
    println(
        "exact_affine_process_chunk=$index/$(length(chunks)) " *
        "constraint=$(chunk.constraint_index) " *
        "range=$(chunk.first_sample):$(chunk.last_sample)",
    )
    run(affine_worker_command(chunk, verification_specification.digest))
end
affine_verification = (
    valid=true,
    residual_count=sum(
        chunk.last_sample - chunk.first_sample + 1
        for chunk in chunks
    ),
    failed_constraint=nothing,
    failed_sample=nothing,
    thread_count=AFFINE_WORKER_THREADS,
    batch_size=max(1, 2 * AFFINE_WORKER_THREADS),
)

exact_solution =
    restore_exact_solution(projection_bundle.portable_exact_solution)
sample_certificate =
    sample_unisolvence_certificate(TARGET_DEGREE, TARGET_DEGREE)
sample_certificate.univariate_distinct ||
    error("canonical univariate sample set is not unisolvent")
sample_certificate.full_rank ||
    error("canonical trivariate sample set is not unisolvent")

verification = verify_parallel_strictly_positive_exact_solution(
    canonical_problem,
    exact_solution;
    expected_objective=TARGET_OBJECTIVE,
    objective_functional=original_objective(TARGET_DEGREE, TARGET_DEGREE),
    verbose=true,
    preverified_affine=affine_verification,
)
verification = merge(
    verification,
    (
        affine_process_count=length(chunks),
        affine_chunk_size=AFFINE_CHUNK_SIZE,
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
    error("projected solution failed canonical exact verification")

portable_verification = merge(
    verification,
    (
        objective_value=PortableExactSolution.portable_rational(
            verification.objective_value,
        ),
    ),
)
verification_source_hashes() == initial_verification_source_hashes ||
    error("verification sources changed during exact replay")
ispath(OUTPUT) && error("refusing to replace an existing exact output")
atomic_serialize(
    OUTPUT,
    (
        schema_version=BUNDLE_SCHEMA_VERSION,
        kind="exact-solution-temporary",
        source_specification=expected_specification,
        rounding_specification=expected_rounding_specification,
        verification_specification=verification_specification,
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
