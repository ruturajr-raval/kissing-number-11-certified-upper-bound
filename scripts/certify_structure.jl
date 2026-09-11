using KissingNumber11Certificate
using ClusteredLowRankSolver
using SHA

const OUTPUT = get(
    ENV,
    "KN11_STRUCTURE_CERTIFICATE",
    joinpath("evidence", "problem-structure.json"),
)

function block_name(key)
    return join(string.(key), ":")
end

problem = build_three_point_problem(
    TARGET_DIMENSION,
    TARGET_COSTHETA,
    TARGET_DEGREE,
    TARGET_DEGREE;
    fixed_objective=TARGET_OBJECTIVE,
)
sizes = blocksizes(problem)
blocks = sort(
    [(name=block_name(key), size=size) for (key, size) in sizes];
    by=entry -> entry.name,
)
upper_triangle_entries =
    sum(entry.size * (entry.size + 1) ÷ 2 for entry in blocks)
full_matrix_entries = sum(entry.size^2 for entry in blocks)

payload = IOBuffer()
println(payload, "{")
println(payload, "  \"schema_version\": 1,")
println(payload, "  \"dimension\": $TARGET_DIMENSION,")
println(payload, "  \"degree\": $TARGET_DEGREE,")
println(payload, "  \"costheta\": \"1/2\",")
println(payload, "  \"fixed_objective\": \"86899/100\",")
println(payload, "  \"constraint_count\": $(length(constraints(problem))),")
println(
    payload,
    "  \"constraint_sample_counts\": [",
    join(
        [length(constraint.samples) for constraint in constraints(problem)],
        ", ",
    ),
    "],",
)
println(payload, "  \"free_variable_count\": 0,")
println(payload, "  \"psd_block_count\": $(length(blocks)),")
println(payload, "  \"upper_triangle_entries\": $upper_triangle_entries,")
println(payload, "  \"full_matrix_entries\": $full_matrix_entries,")
println(payload, "  \"blocks\": [")
for (index, entry) in enumerate(blocks)
    suffix = index == length(blocks) ? "" : ","
    println(
        payload,
        "    {\"name\": \"$(entry.name)\", \"size\": $(entry.size)}$suffix",
    )
end
println(payload, "  ]")
println(payload, "}")
content = String(take!(payload))

mkpath(dirname(OUTPUT))
temporary = OUTPUT * ".tmp.$(getpid())"
try
    write(temporary, content)
    mv(temporary, OUTPUT; force=true)
finally
    isfile(temporary) && rm(temporary; force=true)
end
println("structure_certificate=", OUTPUT)
println("structure_sha256=", bytes2hex(sha256(content)))
