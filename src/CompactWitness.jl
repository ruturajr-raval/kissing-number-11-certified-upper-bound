module CompactWitness

using Nemo
using SHA

export pivoted_ldl
export reconstruct_ldl
export canonical_block_name
export WitnessLimits
export write_compact_witness

const RationalFieldElement = typeof(QQ(0))
const WITNESS_MAGIC = codeunits("KNWIT003")

Base.@kwdef struct WitnessLimits
    max_bytes::Int = 128 * 1024^2
    max_blocks::Int = 128
    max_dimension::Int = 1024
    max_rank_sum::Int = 10_000
    max_rationals::Int = 1_000_000
    max_integer_bits::Int = 131_072
    max_denominators_per_block::Int = 1_000_000
end

const DEFAULT_LIMITS = WitnessLimits()

function validate_limits(limits::WitnessLimits)
    for field in fieldnames(WitnessLimits)
        getfield(limits, field) > 0 ||
            throw(ArgumentError("witness limit $field must be positive"))
    end
    return limits
end

integer_bits(value) =
    iszero(value) ? 0 : ndigits(abs(BigInt(value)); base=2)

function enforce_output_limit(stream, limits::WitnessLimits)
    position(stream) <= limits.max_bytes ||
        throw(ArgumentError("compact witness exceeds byte limit"))
    return nothing
end

function swap_rows!(matrix, left::Int, right::Int, columns)
    left == right && return matrix
    for column in columns
        matrix[left, column], matrix[right, column] =
            matrix[right, column], matrix[left, column]
    end
    return matrix
end

function swap_columns!(matrix, left::Int, right::Int, rows)
    left == right && return matrix
    for row in rows
        matrix[row, left], matrix[row, right] =
            matrix[row, right], matrix[row, left]
    end
    return matrix
end

"""
    pivoted_ldl(matrix)

Return a deterministic exact factorization of a rational positive
semidefinite matrix. If `permutation[i]` is the original index at permuted
index `i`, then the permuted matrix equals `L * Diagonal(D) * L'`.
Only the positive-pivot columns of `L` are retained.
"""
function pivoted_ldl(matrix)
    matrix isa AbstractMatrix ||
        throw(ArgumentError("matrix must be two-dimensional"))
    size(matrix, 1) == size(matrix, 2) ||
        throw(ArgumentError("matrix must be square"))
    dimension = size(matrix, 1)
    dimension > 0 || throw(ArgumentError("matrix must not be empty"))

    active = RationalFieldElement.(Matrix(matrix))
    active == transpose(active) ||
        throw(ArgumentError("matrix must be symmetric"))
    factors = fill(QQ(0), dimension, dimension)
    diagonal = RationalFieldElement[]
    permutation = collect(1:dimension)
    rank = 0

    for pivot_index in 1:dimension
        positive_pivot = nothing
        for row in pivot_index:dimension
            value = active[row, row]
            value < 0 &&
                throw(ArgumentError("matrix is not positive semidefinite"))
            if iszero(value)
                all(
                    iszero(active[row, column])
                    for column in pivot_index:dimension
                ) || throw(
                    ArgumentError(
                        "zero diagonal has a nonzero active row",
                    ),
                )
            elseif isnothing(positive_pivot)
                positive_pivot = row
            end
        end

        if isnothing(positive_pivot)
            all(
                iszero(active[row, column])
                for row in pivot_index:dimension
                for column in pivot_index:dimension
            ) || throw(
                ArgumentError("zero active diagonal has a nonzero block"),
            )
            break
        end

        selected = positive_pivot::Int
        if selected != pivot_index
            swap_rows!(
                active,
                pivot_index,
                selected,
                axes(active, 2),
            )
            swap_columns!(
                active,
                pivot_index,
                selected,
                axes(active, 1),
            )
            if pivot_index > 1
                swap_rows!(
                    factors,
                    pivot_index,
                    selected,
                    1:(pivot_index - 1),
                )
            end
            permutation[pivot_index], permutation[selected] =
                permutation[selected], permutation[pivot_index]
        end

        pivot = active[pivot_index, pivot_index]
        pivot > 0 ||
            error("internal positive-pivot selection failure")
        rank += 1
        push!(diagonal, pivot)
        factors[pivot_index, rank] = QQ(1)
        for row in (pivot_index + 1):dimension
            factors[row, rank] = active[row, pivot_index] / pivot
        end

        for row in (pivot_index + 1):dimension
            for column in row:dimension
                updated =
                    active[row, column] -
                    active[row, pivot_index] * factors[column, rank]
                active[row, column] = updated
                active[column, row] = updated
            end
        end
    end

    retained_factors =
        rank == dimension ? factors : factors[:, 1:rank]
    return (
        dimension=dimension,
        rank=rank,
        permutation=permutation,
        diagonal=diagonal,
        factors=retained_factors,
    )
end

"""
    reconstruct_ldl(factorization)

Reconstruct the original-coordinate rational matrix represented by
`pivoted_ldl`.
"""
function reconstruct_ldl(factorization)
    dimension = factorization.dimension
    rank = factorization.rank
    length(factorization.permutation) == dimension ||
        throw(ArgumentError("permutation length does not match dimension"))
    sort(factorization.permutation) == collect(1:dimension) ||
        throw(ArgumentError("permutation is invalid"))
    length(factorization.diagonal) == rank ||
        throw(ArgumentError("diagonal length does not match rank"))
    size(factorization.factors) == (dimension, rank) ||
        throw(ArgumentError("factor dimensions do not match rank"))
    all(value -> value > 0, factorization.diagonal) ||
        throw(ArgumentError("factor diagonal must be positive"))

    permuted = fill(QQ(0), dimension, dimension)
    for factor_index in 1:rank
        diagonal = factorization.diagonal[factor_index]
        for row in 1:dimension
            left = factorization.factors[row, factor_index]
            iszero(left) && continue
            for column in row:dimension
                right = factorization.factors[column, factor_index]
                iszero(right) && continue
                value = diagonal * left * right
                permuted[row, column] += value
                row == column ||
                    (permuted[column, row] += value)
            end
        end
    end

    result = fill(QQ(0), dimension, dimension)
    for row in 1:dimension
        original_row = factorization.permutation[row]
        for column in 1:dimension
            original_column = factorization.permutation[column]
            result[original_row, original_column] = permuted[row, column]
        end
    end
    return result
end

function canonical_block_name(key)
    if key isa Tuple && length(key) == 2 && key[1] == :F
        return "F/$(lpad(string(key[2]), 2, '0'))"
    elseif key isa Tuple && length(key) == 2 && key[1] == :a
        return "a/$(lpad(string(key[2]), 2, '0'))"
    elseif key isa Tuple &&
           length(key) == 2 &&
           key[1] == :univariatesos
        return "univariatesos/$(key[2])"
    elseif key isa Tuple &&
           length(key) == 3 &&
           key[1] == :trivariatesos
        return "trivariatesos/$(key[2])/$(key[3])"
    end
    throw(ArgumentError("unsupported matrix block key: $(repr(key))"))
end

function write_unsigned_leb128(stream, value::Integer)
    value >= 0 || throw(ArgumentError("ULEB128 value must be nonnegative"))
    remaining = BigInt(value)
    while true
        byte = UInt8(remaining & 0x7f)
        remaining >>= 7
        if iszero(remaining)
            write(stream, byte)
            return
        end
        write(stream, byte | 0x80)
    end
end

function magnitude_bytes(value::Integer)
    value >= 0 || throw(ArgumentError("magnitude must be nonnegative"))
    iszero(value) && return UInt8[]
    bytes = UInt8[]
    remaining = BigInt(value)
    while !iszero(remaining)
        push!(bytes, UInt8(remaining & 0xff))
        remaining >>= 8
    end
    reverse!(bytes)
    return bytes
end

function write_unsigned_integer(stream, value::Integer)
    value > 0 || throw(ArgumentError("encoded denominator must be positive"))
    bytes = magnitude_bytes(value)
    write_unsigned_leb128(stream, length(bytes))
    write(stream, bytes)
end

function write_signed_integer(stream, value::Integer)
    if iszero(value)
        write(stream, UInt8(0))
        return
    end
    write(stream, value > 0 ? UInt8(1) : UInt8(2))
    bytes = magnitude_bytes(abs(value))
    write_unsigned_leb128(stream, length(bytes))
    write(stream, bytes)
end

function factor_values(factorization)
    values = RationalFieldElement[]
    sizehint!(
        values,
        factorization.rank +
        sum(
            factorization.dimension - column
            for column in 1:factorization.rank
        ),
    )
    append!(values, factorization.diagonal)
    for column in 1:factorization.rank
        for row in (column + 1):factorization.dimension
            push!(values, factorization.factors[row, column])
        end
    end
    return values
end

function write_uint16_le(stream, value::Integer)
    0 <= value <= typemax(UInt16) ||
        throw(ArgumentError("value does not fit in UInt16"))
    write(stream, htol(UInt16(value)))
end

function write_uint32_le(stream, value::Integer)
    0 <= value <= typemax(UInt32) ||
        throw(ArgumentError("value does not fit in UInt32"))
    write(stream, htol(UInt32(value)))
end

function file_sha256(path)
    return open(path, "r") do stream
        bytes2hex(sha256(stream))
    end
end

"""
    write_compact_witness(path, matrix_blocks; verbose=false, limits=DEFAULT_LIMITS)

Write exact symmetric matrix upper triangles with a canonical per-block
denominator table. `matrix_blocks` must be an iterable of `(name, matrix)`
pairs in strictly increasing name order. Return size, hash, full-rank, and
rational-count metadata. The independent verifier proves strict positivity
from these exact entries using directed fixed-point interval Cholesky.
"""
function write_compact_witness(
    path,
    matrix_blocks;
    verbose::Bool=false,
    limits::WitnessLimits=DEFAULT_LIMITS,
)
    validate_limits(limits)
    named_blocks = collect(matrix_blocks)
    length(named_blocks) <= limits.max_blocks ||
        throw(ArgumentError("compact witness exceeds block limit"))
    names = [String(name) for (name, _) in named_blocks]
    issorted(names) && length(unique(names)) == length(names) ||
        throw(ArgumentError("block names must be unique and sorted"))

    mkpath(dirname(path))
    temporary, stream = mktemp(dirname(path); cleanup=false)
    block_metadata = NamedTuple[]
    rank_sum = 0
    rational_count = 0
    maximum_numerator_bits = 0
    maximum_denominator_bits = 0
    try
        write(stream, WITNESS_MAGIC)
        write_uint32_le(stream, length(named_blocks))
        enforce_output_limit(stream, limits)
        for (index, (name, matrix)) in enumerate(named_blocks)
            verbose && println(
                "compact_matrix_block=$index/$(length(named_blocks)) name=$(String(name)) size=$(size(matrix, 1))",
            )
            rows, columns = size(matrix)
            rows == columns ||
                throw(ArgumentError("matrix block must be square"))
            rows <= limits.max_dimension ||
                throw(ArgumentError("matrix block exceeds dimension limit"))
            matrix == transpose(matrix) ||
                throw(ArgumentError("matrix block must be symmetric"))
            rank_sum + rows <= limits.max_rank_sum ||
                throw(ArgumentError("compact witness exceeds rank-sum limit"))
            write_uint16_le(stream, rows)
            enforce_output_limit(stream, limits)

            values = [
                matrix[row, column]
                for row in 1:rows
                for column in row:columns
            ]
            rank_sum += rows
            rational_count + length(values) <= limits.max_rationals ||
                throw(
                    ArgumentError(
                        "compact witness exceeds rational-count limit",
                    ),
                )
            rational_count += length(values)
            for value in values
                numerator_bits = integer_bits(numerator(value))
                denominator_bits = integer_bits(denominator(value))
                numerator_bits <= limits.max_integer_bits ||
                    throw(
                        ArgumentError(
                            "compact witness numerator exceeds bit limit",
                        ),
                    )
                denominator_bits <= limits.max_integer_bits ||
                    throw(
                        ArgumentError(
                            "compact witness denominator exceeds bit limit",
                        ),
                    )
                maximum_numerator_bits =
                    max(maximum_numerator_bits, numerator_bits)
                maximum_denominator_bits =
                    max(maximum_denominator_bits, denominator_bits)
            end
            denominators = sort(unique([
                BigInt(denominator(value))
                for value in values
            ]))
            length(denominators) <= limits.max_denominators_per_block ||
                throw(
                    ArgumentError(
                        "matrix block exceeds denominator-table limit",
                    ),
                )
            write_uint32_le(stream, length(denominators))
            for denominator_value in denominators
                write_unsigned_integer(stream, denominator_value)
                enforce_output_limit(stream, limits)
            end
            denominator_indices = Dict(
                value => index - 1
                for (index, value) in enumerate(denominators)
            )
            for value in values
                denominator_value = BigInt(denominator(value))
                numerator_value = BigInt(numerator(value))
                write_unsigned_leb128(
                    stream,
                    denominator_indices[denominator_value],
                )
                write_signed_integer(stream, numerator_value)
                enforce_output_limit(stream, limits)
            end
            push!(
                block_metadata,
                (
                    name=String(name),
                    dimension=rows,
                    rank=rows,
                ),
            )
        end
        flush(stream)
        close(stream)
        mv(temporary, path; force=true)
    finally
        isopen(stream) && close(stream)
        isfile(temporary) && rm(temporary; force=true)
    end

    return (
        path=String(path),
        size_bytes=filesize(path),
        sha256=file_sha256(path),
        block_count=length(named_blocks),
        rank_sum=rank_sum,
        rational_count=rational_count,
        maximum_numerator_bits=maximum_numerator_bits,
        maximum_denominator_bits=maximum_denominator_bits,
        blocks=block_metadata,
    )
end

end
