using Pkg
using SHA

const PROJECT_ROOT = normpath(joinpath(@__DIR__, ".."))

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

function project_path(path)
    candidate = normpath(joinpath(PROJECT_ROOT, path))
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

file_sha256(path) = open(project_path(path), "r") do stream
    bytes2hex(sha256(stream))
end

function snapshot_binding()
    lines = vcat(
        ["source:$path=$(file_sha256(path))" for path in SOURCE_PATHS],
        ["evidence:$path=$(file_sha256(path))" for path in EVIDENCE_PATHS],
    )
    return bytes2hex(sha256(join(lines, "\n") * "\n"))
end

all(path -> isfile(project_path(path)), EVIDENCE_PATHS) ||
    error("one or more proof-component evidence files are missing")
all(path -> isfile(project_path(path)), SOURCE_PATHS) ||
    error("one or more bound source files are missing")
expected_preflight = get(ENV, "KN11_EXPORT_PREFLIGHT_SHA256", "")
isempty(expected_preflight) &&
    error("certificate export requires the preflight hashing wrapper")
snapshot_binding() == expected_preflight ||
    error("certificate source or evidence changed before package loading")

include(joinpath(PROJECT_ROOT, "scripts", "verify_dependency_integrity.jl"))

before = verify_pinned_dependency_integrity(PROJECT_ROOT)
println("verified_dependency_packages=", before.package_count)
println("verified_dependency_artifacts=", before.artifact_count)

exact_input = joinpath(
    PROJECT_ROOT,
    "build",
    "degree17-exact-86899-over-100.jls",
)
isfile(exact_input) ||
    error("exact-solution input does not exist: $exact_input")
expected_exact_input =
    get(ENV, "KN11_EXPECTED_EXACT_INPUT_SHA256", "")
isempty(expected_exact_input) &&
    error("certificate export requires an exact-input SHA-256 trust anchor")
actual_exact_input = open(exact_input, "r") do stream
    bytes2hex(sha256(stream))
end
actual_exact_input == expected_exact_input ||
    error("exact-solution input does not match its trust anchor")

include(joinpath(PROJECT_ROOT, "scripts", "export_compact_certificate.jl"))

after = verify_pinned_dependency_integrity(PROJECT_ROOT)
after == before ||
    error("dependency inventory changed during certificate export")
