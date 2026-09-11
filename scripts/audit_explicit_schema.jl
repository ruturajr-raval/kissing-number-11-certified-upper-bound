using KissingNumber11Certificate
using ClusteredLowRankSolver
using SHA

const OUTPUT = get(
    ENV,
    "KN11_SCHEMA_AUDIT",
    joinpath("evidence", "explicit-schema-audit.json"),
)

triangle_entries(size) = size * (size + 1) ÷ 2

function main()
problem = build_three_point_problem(
    TARGET_DIMENSION,
    TARGET_COSTHETA,
    TARGET_DEGREE,
    TARGET_DEGREE;
    fixed_objective=TARGET_OBJECTIVE,
)
problem_constraints = constraints(problem)
length(problem_constraints) == 3 ||
    error("unexpected fixed-objective constraint count")

f_entries = sum(triangle_entries(size) for size in 1:18)
a_entries = 2 * TARGET_DEGREE + 1
univariate_sos_entries =
    triangle_entries(18) + triangle_entries(17)
trivariate_sos_sizes = [
    237, 147, 378,
    204, 123, 321,
    174, 102, 270,
    147, 83, 225,
    174, 102, 270,
]
trivariate_sos_entries =
    sum(triangle_entries, trivariate_sos_sizes)

univariate_expansion =
    length(problem_constraints[1].samples) *
    (f_entries + a_entries + univariate_sos_entries)
trivariate_expansion =
    length(problem_constraints[2].samples) *
    (f_entries + trivariate_sos_entries)
fixed_expansion = triangle_entries(18) + a_entries
full_expansion =
    univariate_expansion + trivariate_expansion + fixed_expansion

trivariate_constraint = problem_constraints[2]
f_nonzero_terms = 0
f_total_terms = 0
for degree in 0:TARGET_DEGREE
    coefficient = matrixcoeff(trivariate_constraint, (:F, degree))
    for row in axes(coefficient, 1)
        for column in first(axes(coefficient, 2)):row
            entry = coefficient[row, column]
            entry isa SampledMPolyRingElem ||
                error("three-point kernel entry is not sampled exactly")
            f_total_terms += length(entry.evaluations)
            f_nonzero_terms += count(!iszero, entry.evaluations)
        end
    end
end
f_total_terms ==
    length(trivariate_constraint.samples) * f_entries ||
    error("unexpected three-point kernel expansion count")

minimum_term = (
    "{\"block\":\"F/00\",\"coefficient\":\"1/1\","
    * "\"column\":0,\"row\":0}"
)
minimum_term_bytes = ncodeunits(minimum_term) + 1
f_only_minimum_bytes = f_nonzero_terms * minimum_term_bytes
certificate_limit_bytes = 50 * 1024^2
f_only_exceeds_limit = f_only_minimum_bytes > certificate_limit_bytes
f_only_exceeds_limit ||
    error("measured F-term lower bound does not reject the explicit schema")

content = """
{
  "schema_version": 1,
  "dimension": $TARGET_DIMENSION,
  "degree": $TARGET_DEGREE,
  "certificate_limit_bytes": $certificate_limit_bytes,
  "full_expanded_term_upper_bound": $full_expansion,
  "univariate_expanded_term_upper_bound": $univariate_expansion,
  "trivariate_expanded_term_upper_bound": $trivariate_expansion,
  "fixed_objective_expanded_terms": $fixed_expansion,
  "trivariate_f_total_terms": $f_total_terms,
  "trivariate_f_nonzero_terms": $f_nonzero_terms,
  "minimum_explicit_term_bytes": $minimum_term_bytes,
  "trivariate_f_only_minimum_bytes": $f_only_minimum_bytes,
  "trivariate_f_only_exceeds_50_mib": $f_only_exceeds_limit,
  "decision": "reject-explicit-affine-json"
}
"""

mkpath(dirname(OUTPUT))
temporary = OUTPUT * ".tmp.$(getpid())"
try
    write(temporary, content)
    mv(temporary, OUTPUT; force=true)
finally
    isfile(temporary) && rm(temporary; force=true)
end
println("explicit_schema_audit=", OUTPUT)
println("explicit_schema_audit_sha256=", bytes2hex(sha256(content)))
end

main()
