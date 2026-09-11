module PortableExactSolution

using ClusteredLowRankSolver
using Nemo

export PORTABLE_EXACT_SOLUTION_ENCODING
export encode_exact_solution
export restore_exact_solution

const PORTABLE_EXACT_SOLUTION_ENCODING = "rational-bigint-upper-triangle-v1"
const PORTABLE_EXACT_SOLUTION_SCHEMA_VERSION = 1

function portable_rational(value)
    if value isa typeof(QQ(0)) || value isa Rational
        numerator_value = BigInt(numerator(value))
        denominator_value = BigInt(denominator(value))
        denominator_value > 0 ||
            throw(ArgumentError("exact rational has a nonpositive denominator"))
        # Both source representations are already canonical, so avoid a second
        # large-integer gcd while constructing the portable value.
        return Base.unsafe_rational(numerator_value, denominator_value)
    elseif value isa Integer || value isa typeof(ZZ(0))
        return Base.unsafe_rational(BigInt(value), BigInt(1))
    end
    throw(ArgumentError("value is not an exact rational"))
end

function restore_rational(value::Rational{BigInt})
    denominator(value) > 0 ||
        throw(ArgumentError("portable rational has a nonpositive denominator"))
    return QQ(numerator(value)) // denominator(value)
end

"""
    encode_exact_solution(solution)

Convert a Nemo-backed exact primal solution into a process-portable payload.
Julia's generic serializer cannot safely persist `QQFieldElem` because those
objects contain process-local FLINT handles. Built-in `Rational{BigInt}` has
explicit value serialization in Julia and is safe to reload in a new process.
"""
function encode_exact_solution(solution)
    blocks = NamedTuple[]
    for key in sort(collect(keys(matrixvars(solution))); by=repr)
        matrix = matrixvars(solution)[key]
        rows, columns = size(matrix)
        rows == columns ||
            throw(ArgumentError("exact solution contains a nonsquare block"))
        matrix == transpose(matrix) ||
            throw(ArgumentError("exact solution contains a nonsymmetric block"))
        upper_triangle = Rational{BigInt}[]
        sizehint!(upper_triangle, rows * (rows + 1) ÷ 2)
        for row in 1:rows, column in row:columns
            push!(upper_triangle, portable_rational(matrix[row, column]))
        end
        push!(
            blocks,
            (
                key=key,
                dimension=rows,
                upper_triangle=upper_triangle,
            ),
        )
    end

    free_variables = NamedTuple[]
    for key in sort(collect(keys(freevars(solution))); by=repr)
        push!(
            free_variables,
            (
                key=key,
                value=portable_rational(freevars(solution)[key]),
            ),
        )
    end

    return (
        schema_version=PORTABLE_EXACT_SOLUTION_SCHEMA_VERSION,
        encoding=PORTABLE_EXACT_SOLUTION_ENCODING,
        blocks=blocks,
        free_variables=free_variables,
    )
end

"""
    restore_exact_solution(payload)

Validate and restore a portable payload as a fresh Nemo-backed primal solution.
"""
function restore_exact_solution(payload)
    hasproperty(payload, :schema_version) &&
        payload.schema_version == PORTABLE_EXACT_SOLUTION_SCHEMA_VERSION ||
        error("portable exact solution uses an unsupported schema")
    hasproperty(payload, :encoding) &&
        payload.encoding == PORTABLE_EXACT_SOLUTION_ENCODING ||
        error("portable exact solution uses an unsupported encoding")
    hasproperty(payload, :blocks) ||
        error("portable exact solution has no matrix blocks")
    hasproperty(payload, :free_variables) ||
        error("portable exact solution has no free variables")

    rational_type = typeof(QQ(0))
    blocks = Dict{Any,Matrix{rational_type}}()
    for block in payload.blocks
        hasproperty(block, :key) ||
            error("portable matrix block has no key")
        haskey(blocks, block.key) &&
            error("portable exact solution has duplicate matrix block keys")
        hasproperty(block, :dimension) ||
            error("portable matrix block has no dimension")
        dimension = block.dimension
        dimension isa Int && dimension > 0 ||
            error("portable matrix block has an invalid dimension")
        hasproperty(block, :upper_triangle) ||
            error("portable matrix block has no upper triangle")
        expected_length = dimension * (dimension + 1) ÷ 2
        length(block.upper_triangle) == expected_length ||
            error("portable matrix block has the wrong coefficient count")
        all(value -> value isa Rational{BigInt}, block.upper_triangle) ||
            error("portable matrix block contains a nonportable scalar")

        matrix = Matrix{rational_type}(undef, dimension, dimension)
        index = 1
        for row in 1:dimension, column in row:dimension
            value = restore_rational(block.upper_triangle[index])
            matrix[row, column] = value
            matrix[column, row] = value
            index += 1
        end
        blocks[block.key] = matrix
    end

    free_variable_values = Dict{Any,rational_type}()
    for variable in payload.free_variables
        hasproperty(variable, :key) ||
            error("portable free variable has no key")
        haskey(free_variable_values, variable.key) &&
            error("portable exact solution has duplicate free-variable keys")
        hasproperty(variable, :value) &&
            variable.value isa Rational{BigInt} ||
            error("portable free variable contains a nonportable scalar")
        free_variable_values[variable.key] =
            restore_rational(variable.value)
    end

    return PrimalSolution{rational_type}(QQ, blocks, free_variable_values)
end

end
