module CheckpointRecovery

using Serialization
using SHA

export read_checkpoint_snapshot
export validate_checkpoint

function path_within_root(path, allowed_root)
    resolved_path = realpath(path)
    resolved_root = realpath(allowed_root)
    return resolved_path == resolved_root ||
           startswith(resolved_path, resolved_root * Base.Filesystem.path_separator)
end

"""
    read_checkpoint_snapshot(path; max_bytes, allowed_root, expected_sha256)

Read, hash, and deserialize one stable regular-file snapshot. The returned
checkpoint and digest always refer to the same captured bytes.
"""
function read_checkpoint_snapshot(
    path;
    max_bytes::Int,
    allowed_root,
    expected_sha256=nothing,
)
    max_bytes > 0 || throw(ArgumentError("max_bytes must be positive"))
    islink(path) && error("checkpoint must not be a symbolic link")
    isfile(path) || error("checkpoint does not exist: $path")
    path_within_root(path, allowed_root) ||
        error("checkpoint resolves outside the allowed root")
    before = stat(path)
    before.size <= max_bytes ||
        error("checkpoint exceeds the configured size limit")
    bytes = read(path)
    after = stat(path)
    (
        before.size == after.size &&
        before.mtime == after.mtime &&
        before.device == after.device &&
        before.inode == after.inode &&
        length(bytes) == before.size
    ) || error("checkpoint metadata changed while reading")
    digest = bytes2hex(sha256(bytes))
    if !isnothing(expected_sha256)
        digest == expected_sha256 ||
            error("checkpoint SHA-256 does not match the pinned value")
    end
    checkpoint = deserialize(IOBuffer(bytes))
    return (
        checkpoint=checkpoint,
        sha256=digest,
        byte_count=length(bytes),
    )
end

function validate_checkpoint(checkpoint, specification, kind)
    hasproperty(checkpoint, :schema_version) ||
        error("checkpoint has no schema version")
    checkpoint.schema_version == 1 ||
        error("checkpoint uses an unsupported schema")
    hasproperty(checkpoint, :kind) && checkpoint.kind == kind ||
        error("checkpoint kind does not match")
    hasproperty(checkpoint, :specification_digest) &&
        checkpoint.specification_digest == specification.digest ||
        error("checkpoint specification does not match")
    hasproperty(checkpoint, :measurements) ||
        error("checkpoint has no solver measurements")
    hasproperty(checkpoint, :dual_solution) ||
        error("checkpoint has no dual solution")
    hasproperty(checkpoint, :primal_solution) ||
        error("checkpoint has no primal solution")
    return checkpoint
end

end
