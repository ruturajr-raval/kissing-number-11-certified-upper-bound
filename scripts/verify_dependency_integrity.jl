using Pkg

function dependency_path_within(path, root)
    relative = relpath(path, root)
    separator = string(Base.Filesystem.path_separator)
    return (
        relative == "." ||
        (
            !isabspath(relative) &&
            relative != ".." &&
            !startswith(relative, ".." * separator)
        )
    )
end

function verify_pinned_dependency_integrity(project_root)
    canonical_project_root = realpath(project_root)
    stdlib_root = realpath(Sys.STDLIB)
    for depot in Base.DEPOT_PATH
        override = joinpath(depot, "artifacts", "Overrides.toml")
        !ispath(override) ||
            error("artifact overrides are forbidden during verification: $override")
    end
    package_count = 0
    artifact_hashes = Set{String}()
    for (uuid, info) in Pkg.dependencies()
        source = realpath(info.source)
        if info.tree_hash === nothing
            (
                source == canonical_project_root ||
                dependency_path_within(source, stdlib_root)
            ) || error("dependency lacks a bound tree hash: $(info.name)")
            continue
        end

        actual = bytes2hex(Pkg.GitTools.tree_hash(source))
        actual == info.tree_hash ||
            error("dependency tree hash mismatch: $(info.name)")
        package_count += 1

        artifacts_toml = Pkg.Artifacts.find_artifacts_toml(source)
        artifacts_toml === nothing && continue
        for hash in Pkg.Artifacts.extract_all_hashes(
            artifacts_toml;
            pkg_uuid=uuid,
            include_lazy=true,
        )
            token = string(hash)
            token in artifact_hashes && continue
            Pkg.Artifacts.verify_artifact(hash; honor_overrides=false) ||
                error("artifact tree hash mismatch or missing artifact: $token")
            push!(artifact_hashes, token)
        end
    end
    return (
        package_count=package_count,
        artifact_count=length(artifact_hashes),
    )
end

if abspath(PROGRAM_FILE) == @__FILE__
    result = verify_pinned_dependency_integrity(
        normpath(joinpath(@__DIR__, "..")),
    )
    println("verified_dependency_packages=", result.package_count)
    println("verified_dependency_artifacts=", result.artifact_count)
end
