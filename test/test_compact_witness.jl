using Test
using Nemo

include(joinpath(@__DIR__, "..", "src", "CompactWitness.jl"))
using .CompactWitness

@testset "compact exact matrix witness" begin
    matrices = [
        [
            QQ(1) QQ(0) QQ(0)
            QQ(0) QQ(0) QQ(0)
            QQ(0) QQ(0) QQ(2)
        ],
        [
            QQ(1) QQ(1) QQ(1)
            QQ(1) QQ(1) QQ(1)
            QQ(1) QQ(1) QQ(1)
        ],
        [
            QQ(4) QQ(2) QQ(-2)
            QQ(2) QQ(5) QQ(1)
            QQ(-2) QQ(1) QQ(6)
        ],
        fill(QQ(0), 4, 4),
    ]

    for matrix in matrices
        factorization = pivoted_ldl(matrix)
        @test reconstruct_ldl(factorization) == matrix
        @test factorization.rank <= size(matrix, 1)
        @test all(value -> value > 0, factorization.diagonal)
    end

    singular = pivoted_ldl(matrices[2])
    @test singular.rank == 1

    zero = pivoted_ldl(matrices[4])
    @test zero.rank == 0
    @test size(zero.factors) == (4, 0)

    @test_throws ArgumentError pivoted_ldl([
        QQ(1) QQ(2)
        QQ(2) QQ(1)
    ])
    @test_throws ArgumentError pivoted_ldl([
        QQ(0) QQ(1)
        QQ(1) QQ(0)
    ])

    mktempdir() do directory
        witness_path = joinpath(directory, "witness.bin")
        metadata = write_compact_witness(
            witness_path,
            [("block", matrices[3])],
        )
        @test metadata.rank_sum == 3
        @test metadata.rational_count == 6
        @test read(witness_path, 8) == codeunits("KNWIT003")

        path = joinpath(directory, "limited.bin")
        blocks = [("block", fill(QQ(8), 1, 1))]
        @test_throws ArgumentError write_compact_witness(
            path,
            blocks;
            limits=WitnessLimits(max_integer_bits=2),
        )
        @test !isfile(path)
        @test_throws ArgumentError write_compact_witness(
            path,
            blocks;
            limits=WitnessLimits(max_bytes=12),
        )
        @test !isfile(path)
    end
end
