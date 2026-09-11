using KissingNumber11Certificate
using Nemo
using SHA

const OUTPUT = get(
    ENV,
    "KN11_SAMPLE_CERTIFICATE",
    joinpath("evidence", "sample-unisolvence.json"),
)
const SAMPLES_OUTPUT = get(
    ENV,
    "KN11_CANONICAL_SAMPLES",
    joinpath("evidence", "canonical-samples.json"),
)

certificate =
    sample_unisolvence_certificate(TARGET_DEGREE, TARGET_DEGREE)
certificate.univariate_distinct ||
    error("canonical univariate samples are not distinct")
certificate.full_rank ||
    error("canonical trivariate sample matrix is not full rank")

function rational_token(value)
    rational = QQ(value)
    return "$(numerator(rational))/$(denominator(rational))"
end

sample_sets = canonical_sample_sets(TARGET_DEGREE, TARGET_DEGREE)
samples_payload = IOBuffer()
println(samples_payload, "{")
println(samples_payload, "  \"degree\": $TARGET_DEGREE,")
println(samples_payload, "  \"dimension\": $TARGET_DIMENSION,")
println(
    samples_payload,
    "  \"sample_sha256\": \"$(certificate.sample_sha256)\",",
)
println(samples_payload, "  \"schema_version\": 1,")
println(samples_payload, "  \"trivariate\": [")
for (index, sample) in enumerate(sample_sets.trivariate)
    suffix = index == length(sample_sets.trivariate) ? "" : ","
    tokens = join(["\"$(rational_token(value))\"" for value in sample], ", ")
    println(samples_payload, "    [$tokens]$suffix")
end
println(samples_payload, "  ],")
println(
    samples_payload,
    "  \"univariate\": [",
    join(
        ["\"$(rational_token(value))\"" for value in sample_sets.univariate],
        ", ",
    ),
    "]",
)
println(samples_payload, "}")
samples_content = String(take!(samples_payload))
samples_sha256 = bytes2hex(sha256(samples_content))

content = """
{
  "schema_version": 1,
  "dimension": $TARGET_DIMENSION,
  "degree": $TARGET_DEGREE,
  "sample_sha256": "$(certificate.sample_sha256)",
  "seed": $(certificate.seed),
  "decimal_digits": $(certificate.decimal_digits),
  "construction_precision": $(certificate.construction_precision),
  "univariate_sample_count": $(certificate.univariate_sample_count),
  "univariate_distinct": $(certificate.univariate_distinct),
  "trivariate_sample_count": $(certificate.trivariate_sample_count),
  "symmetric_basis_count": $(certificate.symmetric_basis_count),
  "modular_prime": $(certificate.modular_prime),
  "modular_rank": $(certificate.modular_rank),
  "full_rank": $(certificate.full_rank),
  "canonical_samples_file": "$(basename(SAMPLES_OUTPUT))",
  "canonical_samples_sha256": "$samples_sha256"
}
"""

mkpath(dirname(OUTPUT))
mkpath(dirname(SAMPLES_OUTPUT))
temporary = OUTPUT * ".tmp.$(getpid())"
samples_temporary = SAMPLES_OUTPUT * ".tmp.$(getpid())"
try
    write(samples_temporary, samples_content)
    write(temporary, content)
    mv(samples_temporary, SAMPLES_OUTPUT; force=true)
    mv(temporary, OUTPUT; force=true)
finally
    isfile(temporary) && rm(temporary; force=true)
    isfile(samples_temporary) && rm(samples_temporary; force=true)
end
println("sample_certificate=", OUTPUT)
println("canonical_samples=", SAMPLES_OUTPUT)
println("canonical_samples_sha256=", samples_sha256)
