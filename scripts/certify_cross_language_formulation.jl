using KissingNumber11Certificate
using ClusteredLowRankSolver
using Nemo
using SHA

const OUTPUT = get(
    ENV,
    "KN11_CROSS_LANGUAGE_OUTPUT",
    joinpath("evidence", "cross-language-formulation.json"),
)
const DIMENSION = 11
const FULL_DEGREE = 17
const SOS_DEGREE = 6
const COSTHETA = QQ(1) // 2
const CHECKS_PER_BLOCK = 3

function rational_token(value)
    rational = QQ(value)
    return "$(numerator(rational))/$(denominator(rational))"
end

function deterministic_column(dimension, salt)
    return [
        QQ(mod(7 * index + 5 * salt, 17) - 8) //
        (mod(3 * index + salt, 7) + 1)
        for index in 1:dimension
    ]
end

function quadratic_value(coefficient, sample, column)
    evaluated = evaluate(coefficient, sample)
    return sum(
        evaluated[row, column_index] *
        column[row] *
        column[column_index]
        for row in eachindex(column)
        for column_index in eachindex(column)
    )
end

function direct_quadratic_value(matrix, column)
    return sum(
        matrix[row, column_index] *
        column[row] *
        column[column_index]
        for row in eachindex(column)
        for column_index in eachindex(column)
    )
end

function write_atomic(path, content)
    mkpath(dirname(path))
    temporary = path * ".tmp.$(getpid())"
    try
        write(temporary, content)
        mv(temporary, path; force=true)
    finally
        isfile(temporary) && rm(temporary; force=true)
    end
end

sample_sets = canonical_sample_sets(SOS_DEGREE, SOS_DEGREE)
w = first(
    value
    for value in sample_sets.univariate
    if !iszero(value) && value != -1 && value != COSTHETA
)
sample = first(
    values
    for values in sample_sets.trivariate
    if all(!iszero, values) &&
       length(unique(values)) == 3 &&
       !iszero(
           (values[1] - values[2]) *
           (values[2] - values[3]) *
           (values[3] - values[1]),
       )
)

problem = build_three_point_problem(
    DIMENSION,
    COSTHETA,
    SOS_DEGREE,
    SOS_DEGREE;
    fixed_objective=QQ(15),
)
univariate_constraint = constraints(problem)[1]
trivariate_constraint = constraints(problem)[2]

ring, x = polynomial_ring(QQ, :x)
gegenbauer = basis_gegenbauer(2 * FULL_DEGREE, DIMENSION, x)

buffer = IOBuffer()
println(buffer, "{")
println(buffer, "  \"a\": [")
for degree in 0:(2 * FULL_DEGREE)
    suffix = degree == 2 * FULL_DEGREE ? "" : ","
    value = evaluate(gegenbauer[degree + 1], w)
    println(
        buffer,
        "    {\"degree\": $degree, \"value\": \"$(rational_token(value))\"}$suffix",
    )
end
println(buffer, "  ],")
println(buffer, "  \"cos_theta\": \"$(rational_token(COSTHETA))\",")
println(buffer, "  \"dimension\": $DIMENSION,")
println(buffer, "  \"f\": [")
f_record_count = (FULL_DEGREE + 1) * CHECKS_PER_BLOCK
for degree in 0:FULL_DEGREE, check_index in 1:CHECKS_PER_BLOCK
    f_record_index = degree * CHECKS_PER_BLOCK + check_index
    block_dimension = FULL_DEGREE - degree + 1
    column = deterministic_column(
        block_dimension,
        10 * (degree + 1) + check_index,
    )
    trivariate_matrix = KissingNumber11Certificate.symmetrized_matrix(
        QQ,
        DIMENSION,
        degree,
        FULL_DEGREE,
        sample...,
    )
    univariate_matrix =
        3 *
        KissingNumber11Certificate.symmetrized_matrix(
            QQ,
            DIMENSION,
            degree,
            FULL_DEGREE,
            w,
            w,
            QQ(1),
        )
    suffix = f_record_index == f_record_count ? "" : ","
    println(buffer, "    {")
    println(
        buffer,
        "      \"column\": [\"$(join(rational_token.(column), "\", \""))\"],",
    )
    println(buffer, "      \"check_index\": $check_index,")
    println(buffer, "      \"degree\": $degree,")
    println(buffer, "      \"dimension\": $block_dimension,")
    println(
        buffer,
        "      \"trivariate\": \"$(rational_token(direct_quadratic_value(trivariate_matrix, column)))\",",
    )
    println(
        buffer,
        "      \"univariate\": \"$(rational_token(direct_quadratic_value(univariate_matrix, column)))\"",
    )
    println(buffer, "    }$suffix")
end
println(buffer, "  ],")
println(buffer, "  \"full_degree\": $FULL_DEGREE,")
println(
    buffer,
    "  \"sample\": [\"$(join(rational_token.(sample), "\", \""))\"],",
)
println(buffer, "  \"sos_degree\": $SOS_DEGREE,")
println(buffer, "  \"trivariate_sos\": [")
trivariate_keys = sort(
    [
        key
        for key in keys(trivariate_constraint.matrixcoeff)
        if key isa Tuple && key[1] == :trivariatesos
    ];
    by=string,
)
length(trivariate_keys) == 15 ||
    error("expected all 15 three-point SOS block families")
trivariate_record_count = length(trivariate_keys) * CHECKS_PER_BLOCK
for (key_index, key) in enumerate(trivariate_keys),
    check_index in 1:CHECKS_PER_BLOCK
    trivariate_record_index =
        (key_index - 1) * CHECKS_PER_BLOCK + check_index
    coefficient = trivariate_constraint.matrixcoeff[key]
    block_dimension = size(coefficient, 1)
    column = deterministic_column(
        block_dimension,
        100 + 10 * key_index + check_index,
    )
    name = "trivariatesos/$(key[2])/$(key[3])"
    suffix =
        trivariate_record_index == trivariate_record_count ? "" : ","
    println(buffer, "    {")
    println(
        buffer,
        "      \"column\": [\"$(join(rational_token.(column), "\", \""))\"],",
    )
    println(buffer, "      \"check_index\": $check_index,")
    println(buffer, "      \"dimension\": $block_dimension,")
    println(buffer, "      \"name\": \"$name\",")
    println(
        buffer,
        "      \"value\": \"$(rational_token(quadratic_value(coefficient, sample, column)))\"",
    )
    println(buffer, "    }$suffix")
end
println(buffer, "  ],")
println(buffer, "  \"univariate_sos\": [")
univariate_keys = [(:univariatesos, 1), (:univariatesos, 2)]
univariate_record_count = length(univariate_keys) * CHECKS_PER_BLOCK
for (key_index, key) in enumerate(univariate_keys),
    check_index in 1:CHECKS_PER_BLOCK
    univariate_record_index =
        (key_index - 1) * CHECKS_PER_BLOCK + check_index
    coefficient = univariate_constraint.matrixcoeff[key]
    block_dimension = size(coefficient, 1)
    column = deterministic_column(
        block_dimension,
        200 + 10 * key_index + check_index,
    )
    suffix = univariate_record_index == univariate_record_count ? "" : ","
    println(buffer, "    {")
    println(
        buffer,
        "      \"column\": [\"$(join(rational_token.(column), "\", \""))\"],",
    )
    println(buffer, "      \"check_index\": $check_index,")
    println(buffer, "      \"dimension\": $block_dimension,")
    println(buffer, "      \"name\": \"univariatesos/$(key[2])\",")
    println(
        buffer,
        "      \"value\": \"$(rational_token(quadratic_value(coefficient, w, column)))\"",
    )
    println(buffer, "    }$suffix")
end
println(buffer, "  ],")
println(buffer, "  \"w\": \"$(rational_token(w))\"")
println(buffer, "}")

content = String(take!(buffer))
write_atomic(OUTPUT, content)
println("cross_language_formulation=", OUTPUT)
println("cross_language_formulation_sha256=", bytes2hex(sha256(content)))
println("cross_language_f_checks=", f_record_count)
println("cross_language_trivariate_sos_checks=", trivariate_record_count)
