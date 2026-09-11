include(joinpath(@__DIR__, "..", "scripts", "verify_dependency_integrity.jl"))

@testset "dependency integrity" begin
    temporary_parent = normpath(joinpath(@__DIR__, "..", "build"))
    mkpath(temporary_parent)
    mktempdir(temporary_parent) do depot
        artifacts = joinpath(depot, "artifacts")
        mkpath(artifacts)
        write(joinpath(artifacts, "Overrides.toml"), "# forbidden\n")
        pushfirst!(Base.DEPOT_PATH, depot)
        try
            @test_throws ErrorException verify_pinned_dependency_integrity(
                normpath(joinpath(@__DIR__, "..")),
            )
        finally
            popfirst!(Base.DEPOT_PATH)
        end
    end
end
