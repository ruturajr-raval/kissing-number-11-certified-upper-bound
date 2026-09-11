using KissingNumber11Certificate
using ClusteredLowRankSolver
using Serialization
using SHA

include(joinpath(@__DIR__, "..", "src", "CompactWitness.jl"))
include(joinpath(@__DIR__, "..", "src", "PortableExactSolution.jl"))
include(joinpath(@__DIR__, "..", "src", "StrictInteriorVerification.jl"))
include(joinpath(@__DIR__, "..", "src", "ParallelExactVerification.jl"))
using .CompactWitness
using .PortableExactSolution
using .StrictInteriorVerification
using .ParallelExactVerification

const FORMULA_REVISION = "kn11-reduced-dual-coefficients-v2"
const PROJECT_ROOT = normpath(joinpath(@__DIR__, ".."))
const INPUT_PATH =
    joinpath(PROJECT_ROOT, "build", "degree17-exact-86899-over-100.jls")
const WITNESS_PATH =
    joinpath(PROJECT_ROOT, "certificates", "kn11-degree17-witness-v2.bin")
const MANIFEST_PATH =
    joinpath(PROJECT_ROOT, "certificates", "kn11-degree17-certificate-v2.json")
const MAX_INPUT_BYTES = 16 * 1024^3
const MAX_WITNESS_BYTES = 128 * 1024^2
const EXPECTED_PROJECTION_CHECKPOINT_SHA256 =
    "b39c3d218dd5d459018d6f112ef57e9ebe12d083751a594bd7a53bf8b6909826"
const AFFINE_CHUNK_SIZE = 100
const AFFINE_WORKER_THREADS = 2
const VERIFICATION_MODE =
    "process-isolated-threaded-affine-sequential-arb-cholesky-v2"

Threads.nthreads() == AFFINE_WORKER_THREADS ||
    error("certificate export requires $AFFINE_WORKER_THREADS Julia threads")

function project_path(path)
    candidate =
        isabspath(path) ? normpath(path) : normpath(joinpath(PROJECT_ROOT, path))
    relative = relpath(candidate, PROJECT_ROOT)
    separator = string(Base.Filesystem.path_separator)
    (
        relative == "." ||
        (
            !isabspath(relative) &&
            relative != ".." &&
            !startswith(relative, ".." * separator)
        )
    ) || error("path escapes project root: $path")
    return candidate
end

const EVIDENCE_PATHS = sort([
    joinpath("evidence", "canonical-samples.json"),
    joinpath("evidence", "cross-language-formulation.json"),
    joinpath("evidence", "explicit-schema-audit.json"),
    joinpath("evidence", "problem-structure.json"),
    joinpath("evidence", "residual-space.json"),
    joinpath("evidence", "sample-unisolvence.json"),
])

const SOURCE_PATHS = sort([
    "Manifest.toml",
    "Project.toml",
    joinpath("docs", "THEOREM_BRIDGE.md"),
    joinpath("scripts", "certify_cross_language_formulation.jl"),
    joinpath("scripts", "export_compact_certificate.jl"),
    joinpath("scripts", "export_compact_certificate_bootstrap.jl"),
    joinpath("scripts", "round_exact_solution.jl"),
    joinpath("scripts", "solve_fixed_objective.jl"),
    joinpath("scripts", "verify_dependency_integrity.jl"),
    joinpath("scripts", "verify_projection_checkpoint.jl"),
    joinpath("src", "CheckpointRecovery.jl"),
    joinpath("src", "CompactWitness.jl"),
    joinpath("src", "KissingNumber11Certificate.jl"),
    joinpath("src", "ParallelExactVerification.jl"),
    joinpath("src", "PortableExactSolution.jl"),
    joinpath("src", "StrictInteriorVerification.jl"),
    joinpath("test", "check_cross_language_formulation.py"),
    joinpath("tools", "export_compact_certificate.py"),
    joinpath("tools", "release_check.py"),
    joinpath("tools", "release_manifest.py"),
    joinpath("tools", "run_with_limits.py"),
    joinpath("verifier", "compact_certificate.py"),
    joinpath("verifier", "compact_witness.py"),
    joinpath("verifier", "cpp", "compact_witness.cpp"),
    joinpath("verifier", "cpp", "compact_witness.hpp"),
    joinpath("verifier", "formulation.py"),
    joinpath("verifier", "package_manifest.py"),
    joinpath("verifier", "verify_compact_certificate.py"),
    joinpath("verifier", "verify_compact_package.py"),
])

function file_sha256(path)
    return open(project_path(path), "r") do stream
        bytes2hex(sha256(stream))
    end
end

snapshot_hashes(paths) = Dict(path => file_sha256(path) for path in paths)
specification_digest(fields) =
    bytes2hex(sha256(join(fields, "\n") * "\n"))

function snapshot_binding(source_hashes, evidence_hashes)
    lines = vcat(
        [
            "source:$path=$(source_hashes[path])"
            for path in SOURCE_PATHS
        ],
        [
            "evidence:$path=$(evidence_hashes[path])"
            for path in EVIDENCE_PATHS
        ],
    )
    return bytes2hex(sha256(join(lines, "\n") * "\n"))
end

function write_atomic(path, content)
    mkpath(dirname(path))
    temporary, stream = mktemp(dirname(path); cleanup=false)
    try
        write(stream, content)
        flush(stream)
        close(stream)
        mv(temporary, path; force=true)
    finally
        isopen(stream) && close(stream)
        isfile(temporary) && rm(temporary; force=true)
    end
end

all(path -> isfile(project_path(path)), EVIDENCE_PATHS) ||
    error("one or more proof-component evidence files are missing")
all(path -> isfile(project_path(path)), SOURCE_PATHS) ||
    error("one or more bound source files are missing")
evidence_hashes = snapshot_hashes(EVIDENCE_PATHS)
source_hashes = snapshot_hashes(SOURCE_PATHS)
expected_preflight = get(ENV, "KN11_EXPORT_PREFLIGHT_SHA256", "")
isempty(expected_preflight) &&
    error("certificate export requires the preflight hashing wrapper")
snapshot_binding(source_hashes, evidence_hashes) == expected_preflight ||
    error("certificate source or evidence changed after export preflight")

isfile(INPUT_PATH) ||
    error("exact-solution input does not exist: $INPUT_PATH")
expected_exact_input =
    get(ENV, "KN11_EXPECTED_EXACT_INPUT_SHA256", "")
isempty(expected_exact_input) &&
    error("certificate export requires an exact-input SHA-256 trust anchor")
file_sha256(INPUT_PATH) == expected_exact_input ||
    error("exact-solution input does not match its trust anchor")
bundle = open(INPUT_PATH, "r") do stream
    before = stat(stream)
    before.size <= MAX_INPUT_BYTES ||
        error("exact-solution input exceeds the configured size limit")
    value = deserialize(stream)
    after = stat(stream)
    (
        before.device,
        before.inode,
        before.size,
        before.mtime,
        before.ctime,
    ) == (
        after.device,
        after.inode,
        after.size,
        after.mtime,
        after.ctime,
    ) || error("exact-solution input changed while reading")
    value
end
hasproperty(bundle, :schema_version) &&
    bundle.schema_version == BUNDLE_SCHEMA_VERSION ||
    error("exact-solution bundle uses an unsupported schema")
hasproperty(bundle, :kind) &&
    bundle.kind == "exact-solution-temporary" ||
    error("input is not an exact-solution bundle")
hasproperty(bundle, :exact_solution_encoding) &&
    bundle.exact_solution_encoding == PORTABLE_EXACT_SOLUTION_ENCODING ||
    error("exact-solution bundle has an unsupported rational encoding")
hasproperty(bundle, :portable_exact_solution) ||
    error("exact-solution bundle has no portable rational witness")
hasproperty(bundle, :objective) &&
    bundle.objective ==
    PortableExactSolution.portable_rational(TARGET_OBJECTIVE) ||
    error("exact-solution bundle has the wrong target objective")
hasproperty(bundle, :dimension) &&
    bundle.dimension == TARGET_DIMENSION ||
    error("exact-solution bundle has the wrong dimension")
hasproperty(bundle, :degree) &&
    bundle.degree == TARGET_DEGREE ||
    error("exact-solution bundle has the wrong degree")
hasproperty(bundle, :source_specification) ||
    error("exact-solution bundle lacks source provenance")
hasproperty(bundle, :rounding_specification) ||
    error("exact-solution bundle lacks rounding provenance")
hasproperty(bundle, :verification_specification) ||
    error("exact-solution bundle lacks verification provenance")
hasproperty(bundle, :verification) ||
    error("exact-solution bundle lacks its primary verification record")
hasproperty(bundle, :projection_checkpoint_sha256) &&
    bundle.projection_checkpoint_sha256 ==
    EXPECTED_PROJECTION_CHECKPOINT_SHA256 ||
    error("exact-solution bundle has the wrong projection checkpoint")

source_specification_fields = [
    "schema_version=$(BUNDLE_SCHEMA_VERSION)",
    "mode=fixed-objective",
    "dimension=$TARGET_DIMENSION",
    "costheta=1/2",
    "d2=$TARGET_DEGREE",
    "d3=$TARGET_DEGREE",
    "fixed_objective=86899/100",
    "precision=384",
    "solver_revision=$(KissingNumber11Certificate.SOLVER_REVISION)",
    "sample_sha256=$(sample_unisolvence_certificate(TARGET_DEGREE, TARGET_DEGREE).sample_sha256)",
    "sample_prime=65521",
    "sample_rank=1461",
    "module_sha256=$(source_hashes[joinpath("src", "KissingNumber11Certificate.jl")])",
    "project_sha256=$(source_hashes["Project.toml"])",
    "manifest_sha256=$(source_hashes["Manifest.toml"])",
    "script_sha256=$(source_hashes[joinpath("scripts", "solve_fixed_objective.jl")])",
]
source_specification_digest =
    specification_digest(source_specification_fields)
source_specification_digest == bundle.source_specification.digest ||
    error("source specification does not match the bound source files")

rounding_specification_fields = [
    "schema_version=$(BUNDLE_SCHEMA_VERSION)",
    "source_specification=$source_specification_digest",
    "fixed_bundle_sha256=ceed3e884625b2ff6365ea6c68eecdcdddd900d8aac0fa4d9955d8f1894f003a",
    "julia_version=$(VERSION)",
    "rounding_script_sha256=$(source_hashes[joinpath("scripts", "round_exact_solution.jl")])",
    "checkpoint_source_sha256=$(source_hashes[joinpath("src", "CheckpointRecovery.jl")])",
    "portable_source_sha256=$(source_hashes[joinpath("src", "PortableExactSolution.jl")])",
    "verification_source_sha256=$(source_hashes[joinpath("src", "StrictInteriorVerification.jl")])",
    "rounding_mode=strict-interior-direct-projection",
    "projection_encoding=$PORTABLE_EXACT_SOLUTION_ENCODING",
    "rounding_seed=11017",
    "approximation_decimals=60",
    "regularization=1e-50",
    "redundancyfactor=8",
    "pseudo=true",
    "pseudo_columnfactor=1.05",
]
hasproperty(bundle.rounding_specification, :fields) ||
    error("rounding provenance lacks its source fields")
bundle.rounding_specification.fields == rounding_specification_fields ||
    error("rounding provenance fields do not match the bound source files")
rounding_specification_digest =
    specification_digest(rounding_specification_fields)
rounding_specification_digest == bundle.rounding_specification.digest ||
    error("rounding specification digest is inconsistent")

verification_specification_fields = [
    "schema_version=$(BUNDLE_SCHEMA_VERSION)",
    "source_specification=$source_specification_digest",
    "rounding_specification=$rounding_specification_digest",
    "projection_checkpoint_sha256=$EXPECTED_PROJECTION_CHECKPOINT_SHA256",
    "julia_version=$(VERSION)",
    "verification_script_sha256=$(source_hashes[joinpath("scripts", "verify_projection_checkpoint.jl")])",
    "parallel_verification_source_sha256=$(source_hashes[joinpath("src", "ParallelExactVerification.jl")])",
    "strict_verification_source_sha256=$(source_hashes[joinpath("src", "StrictInteriorVerification.jl")])",
    "portable_source_sha256=$(source_hashes[joinpath("src", "PortableExactSolution.jl")])",
    "verification_mode=$VERIFICATION_MODE",
    "affine_chunk_size=$AFFINE_CHUNK_SIZE",
    "affine_worker_threads=$AFFINE_WORKER_THREADS",
]
hasproperty(bundle.verification_specification, :fields) ||
    error("verification provenance lacks its source fields")
bundle.verification_specification.fields ==
    verification_specification_fields ||
    error("verification provenance fields do not match the bound source files")
verification_specification_digest =
    specification_digest(verification_specification_fields)
verification_specification_digest ==
    bundle.verification_specification.digest ||
    error("verification specification digest is inconsistent")

sample_certificate =
    sample_unisolvence_certificate(TARGET_DEGREE, TARGET_DEGREE)
sample_certificate.univariate_distinct ||
    error("canonical univariate sample set is not unisolvent")
sample_certificate.full_rank ||
    error("canonical trivariate sample set is not unisolvent")
canonical_problem = build_three_point_problem(
    TARGET_DIMENSION,
    TARGET_COSTHETA,
    TARGET_DEGREE,
    TARGET_DEGREE;
    fixed_objective=TARGET_OBJECTIVE,
)
stored_verification = bundle.verification
for field in (
    :valid,
    :exact_types_ok,
    :structure_ok,
    :affine_ok,
    :positive_definite_ok,
    :objective_ok,
    :affine_preverified,
    :target_binding_ok,
)
    hasproperty(stored_verification, field) &&
        getproperty(stored_verification, field) === true ||
        error("stored exact verification field $field is not true")
end
expected_residual_count =
    sum(length(constraint.samples) for constraint in constraints(canonical_problem))
hasproperty(stored_verification, :residual_count) &&
    stored_verification.residual_count == expected_residual_count ||
    error("stored exact verification has the wrong residual count")
hasproperty(stored_verification, :failed_affine_constraint) &&
    isnothing(stored_verification.failed_affine_constraint) ||
    error("stored exact verification records an affine constraint failure")
hasproperty(stored_verification, :failed_affine_sample) &&
    isnothing(stored_verification.failed_affine_sample) ||
    error("stored exact verification records an affine sample failure")
hasproperty(stored_verification, :affine_thread_count) &&
    stored_verification.affine_thread_count == AFFINE_WORKER_THREADS ||
    error("stored exact verification has the wrong worker thread count")
hasproperty(stored_verification, :affine_batch_size) &&
    stored_verification.affine_batch_size ==
    max(1, 2 * AFFINE_WORKER_THREADS) ||
    error("stored exact verification has the wrong affine batch size")
hasproperty(stored_verification, :affine_chunk_size) &&
    stored_verification.affine_chunk_size == AFFINE_CHUNK_SIZE ||
    error("stored exact verification has the wrong affine chunk size")
expected_process_count = length(
    affine_sample_chunks(
        canonical_problem;
        chunk_size=AFFINE_CHUNK_SIZE,
    ),
)
hasproperty(stored_verification, :affine_process_count) &&
    stored_verification.affine_process_count == expected_process_count ||
    error("stored exact verification has the wrong worker process count")
hasproperty(stored_verification, :block_count) &&
    stored_verification.block_count == 70 ||
    error("stored exact verification has the wrong block count")
hasproperty(stored_verification, :block_results) &&
    length(stored_verification.block_results) == 70 &&
    all(result -> result.valid, stored_verification.block_results) ||
    error("stored exact verification has an invalid block result")
hasproperty(stored_verification, :objective_value) &&
    stored_verification.objective_value ==
    PortableExactSolution.portable_rational(TARGET_OBJECTIVE) ||
    error("stored exact verification has the wrong objective")
hasproperty(stored_verification, :sample_certificate) &&
    stored_verification.sample_certificate.sample_sha256 ==
    sample_certificate.sample_sha256 &&
    stored_verification.sample_certificate.modular_rank ==
    sample_certificate.modular_rank ||
    error("stored exact verification has the wrong sample certificate")

preverified_affine = (
    valid=true,
    residual_count=stored_verification.residual_count,
    failed_constraint=nothing,
    failed_sample=nothing,
    thread_count=stored_verification.affine_thread_count,
    batch_size=stored_verification.affine_batch_size,
)
exact_solution = restore_exact_solution(bundle.portable_exact_solution)
verification = verify_parallel_strictly_positive_exact_solution(
    canonical_problem,
    exact_solution;
    expected_objective=TARGET_OBJECTIVE,
    objective_functional=original_objective(TARGET_DEGREE, TARGET_DEGREE),
    preverified_affine=preverified_affine,
)
verification.valid ||
    error("exact solution failed canonical target verification")
verification.objective_value == TARGET_OBJECTIVE ||
    error("exact solution has the wrong original objective")
verification.block_count == 70 ||
    error("exact solution has an unexpected block count")
verification.affine_preverified ||
    error("certificate export unexpectedly reran affine identities in-process")

named_blocks = sort(
    [
        (
            canonical_block_name(key),
            matrix,
        )
        for (key, matrix) in matrixvars(exact_solution)
    ];
    by=first,
)
metadata = write_compact_witness(
    WITNESS_PATH,
    named_blocks;
    verbose=true,
)
metadata.block_count == 70 ||
    error("compact witness has an unexpected block count")
metadata.size_bytes <= MAX_WITNESS_BYTES ||
    error("compact witness exceeds the raw size preflight")

metadata.sha256 == file_sha256(WITNESS_PATH) ||
    error("compact witness changed after writing")
metadata.size_bytes == filesize(WITNESS_PATH) ||
    error("compact witness size changed after writing")

sample_certificate =
    sample_unisolvence_certificate(TARGET_DEGREE, TARGET_DEGREE)
descriptor_fields = [
    "formula_revision=$FORMULA_REVISION",
    "dimension=$TARGET_DIMENSION",
    "degree=$TARGET_DEGREE",
    "costheta=1/2",
    "fixed_objective=86899/100",
    "formulation=reduced-three-point-dual",
    "sample_sha256=$(sample_certificate.sample_sha256)",
    "sample_rank_prime=$(sample_certificate.modular_prime)",
    "sample_rank=$(sample_certificate.modular_rank)",
    "problem_structure_sha256=$(evidence_hashes[joinpath("evidence", "problem-structure.json")])",
    "residual_space_sha256=$(evidence_hashes[joinpath("evidence", "residual-space.json")])",
    "theorem_bridge_sha256=$(source_hashes[joinpath("docs", "THEOREM_BRIDGE.md")])",
]
problem_descriptor_sha256 =
    bytes2hex(sha256(join(descriptor_fields, "\n") * "\n"))

manifest = IOBuffer()
println(manifest, "{")
println(manifest, "  \"affiliation\": \"Independent Researcher\",")
println(manifest, "  \"author\": \"Ruturaj R Raval\",")
println(manifest, "  \"blocks\": [")
for (index, block) in enumerate(metadata.blocks)
    suffix = index == length(metadata.blocks) ? "" : ","
    println(
        manifest,
        "    {\"dimension\": $(block.dimension), \"name\": \"$(block.name)\", \"rank\": $(block.rank)}$suffix",
    )
end
println(manifest, "  ],")
println(manifest, "  \"evidence\": [")
for (index, path) in enumerate(EVIDENCE_PATHS)
    suffix = index == length(EVIDENCE_PATHS) ? "" : ","
    println(
        manifest,
        "    {\"path\": \"$path\", \"sha256\": \"$(evidence_hashes[path])\"}$suffix",
    )
end
println(manifest, "  ],")
println(manifest, "  \"format\": \"kn11-compact-certificate\",")
println(manifest, "  \"format_version\": 2,")
println(manifest, "  \"orcid\": \"0000-0003-4930-8981\",")
println(manifest, "  \"problem\": {")
println(manifest, "    \"cos_theta\": \"1/2\",")
println(manifest, "    \"degree\": $TARGET_DEGREE,")
println(manifest, "    \"dimension\": $TARGET_DIMENSION,")
println(manifest, "    \"fixed_objective\": \"86899/100\",")
println(manifest, "    \"formula_revision\": \"$FORMULA_REVISION\",")
println(
    manifest,
    "    \"problem_descriptor_sha256\": \"$problem_descriptor_sha256\",",
)
println(
    manifest,
    "    \"sample_sha256\": \"$(sample_certificate.sample_sha256)\",",
)
println(manifest, "    \"theorem\": \"tau_11 <= 868\"")
println(manifest, "  },")
println(manifest, "  \"provenance\": {")
println(manifest, "    \"rounding_specification\": {")
println(
    manifest,
    "      \"digest\": \"$rounding_specification_digest\",",
)
println(manifest, "      \"fields\": [")
for (index, field) in enumerate(rounding_specification_fields)
    suffix = index == length(rounding_specification_fields) ? "" : ","
    println(manifest, "        \"$field\"$suffix")
end
println(manifest, "      ]")
println(manifest, "    },")
println(manifest, "    \"source_specification\": {")
println(
    manifest,
    "      \"digest\": \"$source_specification_digest\",",
)
println(manifest, "      \"fields\": [")
for (index, field) in enumerate(source_specification_fields)
    suffix = index == length(source_specification_fields) ? "" : ","
    println(manifest, "        \"$field\"$suffix")
end
println(manifest, "      ]")
println(manifest, "    },")
println(manifest, "    \"verification_specification\": {")
println(
    manifest,
    "      \"digest\": \"$verification_specification_digest\",",
)
println(manifest, "      \"fields\": [")
for (index, field) in enumerate(verification_specification_fields)
    suffix = index == length(verification_specification_fields) ? "" : ","
    println(manifest, "        \"$field\"$suffix")
end
println(manifest, "      ]")
println(manifest, "    }")
println(manifest, "  },")
println(manifest, "  \"sources\": [")
for (index, path) in enumerate(SOURCE_PATHS)
    suffix = index == length(SOURCE_PATHS) ? "" : ","
    println(
        manifest,
        "    {\"path\": \"$path\", \"sha256\": \"$(source_hashes[path])\"}$suffix",
    )
end
println(manifest, "  ],")
println(manifest, "  \"status\": \"candidate-exact-certificate\",")
println(manifest, "  \"verification\": {")
println(manifest, "    \"affine_identities_exact\": true,")
println(manifest, "    \"block_count\": $(verification.block_count),")
println(manifest, "    \"objective_exact\": true,")
println(manifest, "    \"positive_semidefinite_exact\": true")
println(manifest, "  },")
println(manifest, "  \"witness\": {")
println(manifest, "    \"filename\": \"$(basename(WITNESS_PATH))\",")
println(
    manifest,
    "    \"maximum_denominator_bits\": $(metadata.maximum_denominator_bits),",
)
println(
    manifest,
    "    \"maximum_numerator_bits\": $(metadata.maximum_numerator_bits),",
)
println(manifest, "    \"rank_sum\": $(metadata.rank_sum),")
println(manifest, "    \"rational_count\": $(metadata.rational_count),")
println(manifest, "    \"sha256\": \"$(metadata.sha256)\",")
println(manifest, "    \"size_bytes\": $(metadata.size_bytes)")
println(manifest, "  }")
println(manifest, "}")
manifest_content = String(take!(manifest))
snapshot_hashes(EVIDENCE_PATHS) == evidence_hashes ||
    error("evidence files changed during certificate export")
snapshot_hashes(SOURCE_PATHS) == source_hashes ||
    error("bound source files changed during certificate export")
write_atomic(MANIFEST_PATH, manifest_content)

println("compact_witness=", WITNESS_PATH)
println("compact_witness_sha256=", metadata.sha256)
println("compact_witness_bytes=", metadata.size_bytes)
println("compact_witness_rank_sum=", metadata.rank_sum)
println("compact_witness_rational_count=", metadata.rational_count)
println("problem_descriptor_sha256=", problem_descriptor_sha256)
println("compact_manifest=", MANIFEST_PATH)
println("compact_manifest_sha256=", file_sha256(MANIFEST_PATH))
