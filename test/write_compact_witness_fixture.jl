using Nemo

include(joinpath(@__DIR__, "..", "src", "CompactWitness.jl"))
using .CompactWitness

output = get(
    ENV,
    "KN11_COMPACT_FIXTURE",
    joinpath(@__DIR__, "..", "build", "compact-witness-fixture.bin"),
)
blocks = [
    (
        "F/00",
        [
            QQ(2) QQ(-2)
            QQ(-2) QQ(7) // 2
        ],
    ),
    ("a/00", fill(QQ(0), 1, 1)),
]
metadata = write_compact_witness(output, blocks)
println("compact_fixture=", output)
println("compact_fixture_sha256=", metadata.sha256)
