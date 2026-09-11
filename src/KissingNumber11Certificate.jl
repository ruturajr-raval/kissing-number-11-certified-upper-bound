module KissingNumber11Certificate

using ClusteredLowRankSolver
using LinearAlgebra
using Nemo
using Random
using Serialization
using SHA

export build_three_point_problem
export solve_three_point_problem
export fixed_objective
export original_objective
export exact_psd
export verify_exact_solution
export verify_target_exact_solution
export canonical_sample_sets
export sample_unisolvence_certificate
export problem_specification
export numerical_residual_summary
export minimum_matrix_eigenvalue
export atomic_serialize
export load_compatible_checkpoint
export checkpoint_callback
export TARGET_DIMENSION
export TARGET_DEGREE
export TARGET_COSTHETA
export TARGET_OBJECTIVE
export BUNDLE_SCHEMA_VERSION

const TARGET_DIMENSION = 11
const TARGET_DEGREE = 17
const TARGET_COSTHETA = QQ(1) // 2
const TARGET_OBJECTIVE = QQ(86899) // 100
const BUNDLE_SCHEMA_VERSION = 1
const SAMPLE_SEED = 1935
const SAMPLE_DIGITS = 4
const SAMPLE_PRECISION = 256
const SAMPLE_RANK_PRIME = 65_521
const SOLVER_REVISION = "09ac81aed031bdea714832cf515244f6eb223531"
const PROJECT_ROOT = normpath(joinpath(@__DIR__, ".."))
const SAMPLE_CERTIFICATE_CACHE = Dict{Tuple{Int,Int,Int},Any}()

function gegenbauer_kernel(field, dimension::Int, degree::Int, u, v, t)
    ring, x = polynomial_ring(field, :x)
    polynomial = basis_gegenbauer(degree, dimension, x)[end]
    sum(
        coeff(polynomial, i) *
        ((1 - u^2) * (1 - v^2))^div(degree - i, 2) *
        (t - u * v)^i
        for i in 0:(length(polynomial) - 1)
    )
end

monomial_vector(variable, degree::Int) = [variable^k for k in 0:degree]

function symmetrized_matrix(field, dimension, degree, max_degree, u, v, t)
    matrix =
        gegenbauer_kernel(field, dimension - 1, degree, u, v, t) .* (
            monomial_vector(v, max_degree - degree) *
            transpose(monomial_vector(u, max_degree - degree)) +
            monomial_vector(u, max_degree - degree) *
            transpose(monomial_vector(v, max_degree - degree))
        )
    matrix +=
        gegenbauer_kernel(field, dimension - 1, degree, t, u, v) .* (
            monomial_vector(t, max_degree - degree) *
            transpose(monomial_vector(u, max_degree - degree)) +
            monomial_vector(u, max_degree - degree) *
            transpose(monomial_vector(t, max_degree - degree))
        )
    matrix +=
        gegenbauer_kernel(field, dimension - 1, degree, t, v, u) .* (
            monomial_vector(t, max_degree - degree) *
            transpose(monomial_vector(v, max_degree - degree)) +
            monomial_vector(v, max_degree - degree) *
            transpose(monomial_vector(t, max_degree - degree))
        )
    return (1 // 6) * matrix
end

interval_weight(variable, costheta) = interval_weight(variable, -1, costheta)
interval_weight(variable, lower, upper) = (variable - lower) * (upper - variable)

function objective_coefficients(d2::Int, d3::Int)
    coefficients = Dict()
    coefficients[(:F, 0)] = ones(Int, d3 + 1, d3 + 1)
    if d2 >= 0
        for k in 0:(2 * d2)
            coefficients[(:a, k)] = ones(Int, 1, 1)
        end
    end
    return coefficients
end

original_objective(d2::Int, d3::Int) =
    Objective(1, objective_coefficients(d2, d3), Dict())

function symmetric_exponents(max_degree::Int)
    exponents = NTuple{3,Int}[]
    for degree in 0:max_degree
        for k in 0:div(degree, 3)
            for j in 0:div(degree - 3 * k, 2)
                a = degree - 3 * k - 2 * j
                push!(exponents, (a, j, k))
            end
        end
    end
    return exponents
end

quantize_rational_sample(value) =
    floor(BigInt, big(10)^SAMPLE_DIGITS * value) //
    big(10)^SAMPLE_DIGITS

quantize_qq_sample(value) = QQ(quantize_rational_sample(value))

"""
    canonical_sample_sets(d2, d3)

Construct the exact deterministic sample sets used by the SDP. The local
random generator and fixed BigFloat precision prevent ambient process state
from changing the selected trivariate points.
"""
function canonical_sample_sets(d2::Int, d3::Int)
    n2 = max(d2, d3)
    return setprecision(BigFloat, SAMPLE_PRECISION) do
        samples_1d = [
            quantize_rational_sample(value)
            for value in sample_points_chebyshev(2 * n2, -1, 1)
        ]

        exponents = symmetric_exponents(2 * d3)
        chebyshev_points = [
            vcat(sample_points_chebyshev(2 * d3 + offset, -1, 1)...)
            for offset in 0:2
        ]
        candidate_samples = [
            [
                chebyshev_points[1][i + 1],
                chebyshev_points[2][j + 1],
                chebyshev_points[3][k + 1],
            ]
            for i in 0:(2 * d3)
            for j in 0:(2 * d3 + 1)
            for k in 0:(2 * d3 + 2)
        ]
        selected = shuffle(
            Xoshiro(SAMPLE_SEED),
            collect(eachindex(candidate_samples)),
        )[1:length(exponents)]
        samples_3d = sort([
            [quantize_qq_sample(value) for value in candidate_samples[index]]
            for index in selected
        ])

        return (
            univariate=samples_1d,
            trivariate=samples_3d,
            symmetric_exponents=exponents,
        )
    end
end

function rational_token(value)
    rational = QQ(value)
    return "$(numerator(rational))/$(denominator(rational))"
end

function sample_digest(sample_sets)
    buffer = IOBuffer()
    println(buffer, "seed=", SAMPLE_SEED)
    println(buffer, "digits=", SAMPLE_DIGITS)
    println(buffer, "precision=", SAMPLE_PRECISION)
    for value in sample_sets.univariate
        println(buffer, "u:", rational_token(value))
    end
    for sample in sample_sets.trivariate
        println(buffer, "t:", join(rational_token.(sample), ","))
    end
    return bytes2hex(sha256(take!(buffer)))
end

function finite_field_value(field, value, prime::Int)
    rational = QQ(value)
    denominator_mod_prime = mod(BigInt(denominator(rational)), prime)
    iszero(denominator_mod_prime) &&
        error("sample denominator is zero modulo $prime")
    return field(numerator(rational)) / field(denominator(rational))
end

"""
    sample_unisolvence_certificate(d2, d3; prime=65_521)

Prove that the sampled equalities determine the relevant polynomial spaces.
Distinct univariate points certify degree at most `2*max(d2,d3)`. For the
symmetric trivariate space, full rank modulo `prime` proves full rank over the
rationals.
"""
function sample_unisolvence_certificate(
    d2::Int,
    d3::Int;
    prime::Int=SAMPLE_RANK_PRIME,
)
    cache_key = (d2, d3, prime)
    if haskey(SAMPLE_CERTIFICATE_CACHE, cache_key)
        return SAMPLE_CERTIFICATE_CACHE[cache_key]
    end

    sample_sets = canonical_sample_sets(d2, d3)
    univariate_tokens = rational_token.(sample_sets.univariate)
    univariate_distinct =
        length(unique(univariate_tokens)) == length(univariate_tokens)

    exponents = sample_sets.symmetric_exponents
    sample_count = length(sample_sets.trivariate)
    length(exponents) == sample_count ||
        error("trivariate sample and basis counts differ")

    field = GF(prime)
    evaluation_matrix = zero_matrix(field, sample_count, sample_count)
    for (row, sample) in enumerate(sample_sets.trivariate)
        u, v, t = (
            finite_field_value(field, value, prime)
            for value in sample
        )
        elementary_1 = u + v + t
        elementary_2 = u * v + u * t + v * t
        elementary_3 = u * v * t
        for (column, (a, j, k)) in enumerate(exponents)
            evaluation_matrix[row, column] =
                elementary_1^a * elementary_2^j * elementary_3^k
        end
    end
    modular_rank = rank(evaluation_matrix)
    full_rank = modular_rank == sample_count
    certificate = (
        sample_sha256=sample_digest(sample_sets),
        seed=SAMPLE_SEED,
        decimal_digits=SAMPLE_DIGITS,
        construction_precision=SAMPLE_PRECISION,
        univariate_sample_count=length(sample_sets.univariate),
        univariate_distinct=univariate_distinct,
        trivariate_sample_count=sample_count,
        symmetric_basis_count=length(exponents),
        modular_prime=prime,
        modular_rank=modular_rank,
        full_rank=full_rank,
    )
    SAMPLE_CERTIFICATE_CACHE[cache_key] = certificate
    return certificate
end

"""
    build_three_point_problem(n, costheta, d2, d3; fixed_objective=nothing)

Construct the rational Bachoc-Vallentin three-point SDP. When
`fixed_objective` is supplied, replace minimization by the exact equality
that the original objective has that value.
"""
function build_three_point_problem(
    n::Int,
    costheta,
    d2::Int,
    d3::Int;
    fixed_objective=nothing,
    field=QQ,
)
    n2 = max(d2, d3)
    n3 = d3
    sample_sets = canonical_sample_sets(d2, d3)

    constraints = Constraint[]

    univariate_ring, w = polynomial_ring(field, :w)
    univariate_coefficients = Dict()
    for k in 0:d3
        univariate_coefficients[(:F, k)] =
            3 * symmetrized_matrix(field, n, k, d3, w, w, 1)
    end
    if d2 >= 0
        basis = basis_gegenbauer(2 * d2, n, w)
        for k in 0:(2 * d2)
            univariate_coefficients[(:a, k)] =
                LowRankMatPol([basis[k + 1]], [[1]])
        end
    end

    basis_1d = basis_chebyshev(2 * n2, w)
    samples_1d = sample_sets.univariate

    if n2 >= 0
        univariate_coefficients[(:univariatesos, 1)] =
            LowRankMatPol([1], [basis_1d[1:(n2 + 1)]])
    end
    if n2 >= 1
        univariate_coefficients[(:univariatesos, 2)] =
            LowRankMatPol(
                [interval_weight(w, costheta)],
                [basis_1d[1:n2]],
            )
    end
    push!(
        constraints,
        Constraint(-1, univariate_coefficients, Dict(), samples_1d),
    )

    polynomial_ring_3d, (u, v, t) =
        polynomial_ring(field, [:u, :v, :t])

    equivariants = [
        [[polynomial_ring_3d(1)]],
        [[(u - v) * (v - t) * (t - u)]],
        [[2 * u - v - t, 2 * v * t - u * t - u * v],
         [v - t, u * t - u * v]],
    ]
    factors = [[1], [1], [1 // 2, 3 // 2]]
    weights = [
        polynomial_ring_3d(1),
        interval_weight(u, costheta) +
            interval_weight(v, costheta) +
            interval_weight(t, costheta),
        interval_weight(u, costheta) * interval_weight(v, costheta) +
            interval_weight(v, costheta) * interval_weight(t, costheta) +
            interval_weight(t, costheta) * interval_weight(u, costheta),
        interval_weight(u, costheta) *
            interval_weight(v, costheta) *
            interval_weight(t, costheta),
        2 * u * v * t + 1 - u^2 - v^2 - t^2,
    ]

    samples = sample_sets.trivariate

    sampled_ring = SampledMPolyRing(field, samples)
    sampled_u = sampled_ring(u)
    sampled_v = sampled_ring(v)
    sampled_t = sampled_ring(t)

    trivariate_coefficients = Dict()
    for k in 0:d3
        trivariate_coefficients[(:F, k)] = symmetrized_matrix(
            field,
            n,
            k,
            d3,
            sampled_u,
            sampled_v,
            sampled_t,
        )
    end

    temporary_ring, x = polynomial_ring(field, :x)
    temporary_basis = monomial_vector(x, n3)
    basis_3d = []
    degrees_3d = Int[]
    for degree in 0:n3
        for k in 0:div(degree, 3)
            for j in 0:div(degree - 3 * k, 2)
                evaluations = [
                    temporary_basis[degree - 3 * k - 2 * j + 1](
                        a + b + c,
                    ) *
                    temporary_basis[j + 1](a * b + b * c + a * c) *
                    temporary_basis[k + 1](a * b * c)
                    for (a, b, c) in samples
                ]
                push!(
                    basis_3d,
                    SampledMPolyRingElem(sampled_ring, evaluations),
                )
                push!(degrees_3d, degree)
            end
        end
    end

    for weight_index in eachindex(weights)
        if total_degree(weights[weight_index]) <= 2 * n3
            for equivariant_index in eachindex(equivariants)
                vectors = []
                for row in eachindex(equivariants[equivariant_index])
                    vector = []
                    for equivariant in
                        equivariants[equivariant_index][row]
                        for (basis_element, basis_degree) in
                            zip(basis_3d, degrees_3d)
                            if total_degree(weights[weight_index]) +
                               2 * total_degree(equivariant) +
                               2 * basis_degree <= 2 * n3
                                push!(
                                    vector,
                                    equivariant(
                                        sampled_u,
                                        sampled_v,
                                        sampled_t,
                                    ) * basis_element,
                                )
                            end
                        end
                    end
                    if !isempty(vector)
                        push!(vectors, vector)
                    end
                end
                if !isempty(vectors)
                    key = (
                        :trivariatesos,
                        weight_index,
                        equivariant_index,
                    )
                    trivariate_coefficients[key] = LowRankMatPol(
                        weights[weight_index](
                            sampled_u,
                            sampled_v,
                            sampled_t,
                        ) .* factors[equivariant_index],
                        vectors,
                    )
                end
            end
        end
    end
    push!(
        constraints,
        Constraint(0, trivariate_coefficients, Dict(), samples),
    )

    if isnothing(fixed_objective)
        objective = original_objective(d2, d3)
    else
        objective = Objective(0, Dict(), Dict())
        push!(
            constraints,
            Constraint(
                fixed_objective - 1,
                objective_coefficients(d2, d3),
                Dict(),
            ),
        )
    end

    return Problem(Minimize(objective), constraints)
end

function solve_three_point_problem(
    n::Int,
    costheta,
    d2::Int,
    d3::Int;
    fixed_objective=nothing,
    kwargs...,
)
    problem = build_three_point_problem(
        n,
        costheta,
        d2,
        d3;
        fixed_objective=fixed_objective,
    )
    status, dual_solution, primal_solution, elapsed, error_code =
        solvesdp(problem; kwargs...)
    return (
        problem,
        status,
        dual_solution,
        primal_solution,
        elapsed,
        error_code,
    )
end

fixed_objective() = TARGET_OBJECTIVE

function file_sha256(path::AbstractString)
    return open(path, "r") do stream
        bytes2hex(sha256(stream))
    end
end

function exact_token(value)
    return isnothing(value) ? "none" : rational_token(value)
end

"""
    problem_specification(; ...)

Create a deterministic binding between a solver artifact and the exact
problem, source files, dependency manifest, sample set, and solver revision.
"""
function problem_specification(
    ;
    mode::AbstractString,
    dimension::Int,
    costheta,
    d2::Int,
    d3::Int,
    fixed_objective=nothing,
    precision::Int,
    script_path::AbstractString,
)
    sample_certificate = sample_unisolvence_certificate(d2, d3)
    sample_certificate.univariate_distinct ||
        error("univariate samples are not distinct")
    sample_certificate.full_rank ||
        error("trivariate sample matrix is not full rank")

    source_hashes = (
        module_sha256=file_sha256(@__FILE__),
        project_sha256=file_sha256(joinpath(PROJECT_ROOT, "Project.toml")),
        manifest_sha256=file_sha256(joinpath(PROJECT_ROOT, "Manifest.toml")),
        script_sha256=file_sha256(abspath(script_path)),
    )
    fields = [
        "schema_version=$(BUNDLE_SCHEMA_VERSION)",
        "mode=$mode",
        "dimension=$dimension",
        "costheta=$(exact_token(costheta))",
        "d2=$d2",
        "d3=$d3",
        "fixed_objective=$(exact_token(fixed_objective))",
        "precision=$precision",
        "solver_revision=$SOLVER_REVISION",
        "sample_sha256=$(sample_certificate.sample_sha256)",
        "sample_prime=$(sample_certificate.modular_prime)",
        "sample_rank=$(sample_certificate.modular_rank)",
        "module_sha256=$(source_hashes.module_sha256)",
        "project_sha256=$(source_hashes.project_sha256)",
        "manifest_sha256=$(source_hashes.manifest_sha256)",
        "script_sha256=$(source_hashes.script_sha256)",
    ]
    digest = bytes2hex(sha256(join(fields, "\n") * "\n"))
    return (
        schema_version=BUNDLE_SCHEMA_VERSION,
        mode=String(mode),
        dimension=dimension,
        costheta=exact_token(costheta),
        d2=d2,
        d3=d3,
        fixed_objective=exact_token(fixed_objective),
        precision=precision,
        solver_revision=SOLVER_REVISION,
        sample_certificate=sample_certificate,
        source_hashes=source_hashes,
        digest=digest,
    )
end

function append_numeric_values!(output::Vector{BigFloat}, value)
    if value isa Number
        push!(output, BigFloat(value))
    elseif value isa SampledMPolyRingElem
        for evaluation in value.evaluations
            append_numeric_values!(output, evaluation)
        end
    elseif value isa AbstractArray
        for entry in value
            append_numeric_values!(output, entry)
        end
    else
        error("unsupported numerical residual type: $(typeof(value))")
    end
    return output
end

"""
    numerical_residual_summary(problem, solution)

Measure every sampled affine residual directly from the returned primal
solution.
"""
function numerical_residual_summary(problem, solution)
    values = BigFloat[]
    for residual in slacks(problem, solution)
        append_numeric_values!(values, residual)
    end
    maximum_absolute =
        isempty(values) ? BigFloat(0) : maximum(abs, values)
    return (
        maximum_absolute=maximum_absolute,
        scalar_count=length(values),
    )
end

"""
    minimum_matrix_eigenvalue(solution)

Return the smallest floating-point eigenvalue across all primal matrix blocks.
This is a numerical screening check only, not an exact PSD certificate.
"""
function minimum_matrix_eigenvalue(solution)
    minimum_value = BigFloat(Inf)
    for matrix_value in values(matrixvars(solution))
        candidate = eigmin(Symmetric(BigFloat.(matrix_value)))
        minimum_value = min(minimum_value, candidate)
    end
    return minimum_value
end

function atomic_serialize(path::AbstractString, value)
    mkpath(dirname(path))
    temporary = path * ".tmp.$(getpid())"
    try
        open(temporary, "w") do stream
            serialize(stream, value)
            flush(stream)
        end
        mv(temporary, path; force=true)
    finally
        isfile(temporary) && rm(temporary; force=true)
    end
    return path
end

function load_compatible_checkpoint(
    path::AbstractString,
    specification,
    kind::AbstractString,
)
    isfile(path) || return nothing
    checkpoint = try
        open(deserialize, path)
    catch error_value
        @warn "Ignoring unreadable checkpoint" path exception=error_value
        return nothing
    end
    if !hasproperty(checkpoint, :schema_version) ||
       checkpoint.schema_version != BUNDLE_SCHEMA_VERSION ||
       !hasproperty(checkpoint, :kind) ||
       checkpoint.kind != kind ||
       !hasproperty(checkpoint, :specification_digest) ||
       checkpoint.specification_digest != specification.digest ||
       !hasproperty(checkpoint, :dual_solution) ||
       !hasproperty(checkpoint, :primal_solution)
        @warn "Ignoring checkpoint with incompatible metadata" path
        return nothing
    end
    return checkpoint
end

function checkpoint_callback(
    path::AbstractString,
    specification,
    kind::AbstractString;
    interval_seconds::Real=1800,
)
    last_save = Ref(time())
    return function(measurements, dual_solution, primal_solution)
        if time() - last_save[] >= interval_seconds
            atomic_serialize(
                path,
                (
                    schema_version=BUNDLE_SCHEMA_VERSION,
                    kind=String(kind),
                    specification_digest=specification.digest,
                    measurements=measurements,
                    dual_solution=dual_solution,
                    primal_solution=primal_solution,
                ),
            )
            last_save[] = time()
        end
        return nothing
    end
end

function is_exact_scalar(value)
    if value isa Integer || value isa typeof(ZZ(0))
        return true
    elseif value isa Rational
        return !iszero(denominator(value))
    elseif value isa typeof(QQ(0))
        return !iszero(denominator(value))
    end
    return false
end

function exact_rational(value)
    is_exact_scalar(value) ||
        throw(ArgumentError("value is not a finite exact rational"))
    if value isa typeof(QQ(0))
        return value
    end
    return QQ(numerator(value)) // denominator(value)
end

function solution_has_exact_scalars(solution)
    return all(
        is_exact_scalar(value)
        for matrix_value in values(matrixvars(solution))
        for value in matrix_value
    ) && all(is_exact_scalar, values(freevars(solution)))
end

"""
    exact_psd(matrix)

Check positive semidefiniteness over an exact ordered field. The algorithm
uses exact symmetric Schur complements, accepts zero pivots only when the
corresponding residual matrix is zero, and performs no floating-point
eigenvalue computation.
"""
function exact_psd(matrix)
    matrix isa AbstractMatrix || return false
    size(matrix, 1) == size(matrix, 2) || return false
    size(matrix, 1) > 0 || return false
    all(is_exact_scalar, matrix) || return false
    active = exact_rational.(Matrix(matrix))
    if active != transpose(active)
        return false
    end

    while !isempty(active)
        diagonal = [active[i, i] for i in axes(active, 1)]
        if any(value -> value < 0, diagonal)
            return false
        end

        pivot = findfirst(value -> value > 0, diagonal)
        if isnothing(pivot)
            return all(iszero, active)
        end

        if pivot != 1
            order = collect(axes(active, 1))
            order[1], order[pivot] = order[pivot], order[1]
            active = active[order, order]
        end

        if size(active, 1) == 1
            return true
        end

        pivot_value = active[1, 1]
        column = active[2:end, 1]
        trailing = active[2:end, 2:end]
        active = [
            trailing[i, j] - column[i] * column[j] / pivot_value
            for i in axes(trailing, 1), j in axes(trailing, 2)
        ]
    end

    return true
end

"""
    verify_exact_solution(
        problem,
        solution;
        expected_objective=nothing,
        objective_functional=nothing,
    )

Check every affine constraint and matrix block in exact arithmetic. Return a
named tuple suitable for a proof-pipeline gate.
"""
function verify_exact_solution(
    problem,
    solution;
    expected_objective=nothing,
    objective_functional=nothing,
)
    exact_types_ok = solution_has_exact_scalars(solution)
    expected_blocks = blocksizes(problem)
    actual_blocks = matrixvars(solution)
    block_keys_ok = Set(keys(actual_blocks)) == Set(keys(expected_blocks))
    block_sizes_ok = block_keys_ok && all(
        size(actual_blocks[key]) == (expected_blocks[key], expected_blocks[key])
        for key in keys(expected_blocks)
    )
    expected_free_keys = Set{Any}()
    union!(expected_free_keys, keys(freecoeffs(objective(problem))))
    for constraint in constraints(problem)
        union!(expected_free_keys, keys(freecoeffs(constraint)))
    end
    free_keys_ok = Set(keys(freevars(solution))) == expected_free_keys
    structure_ok = block_keys_ok && block_sizes_ok && free_keys_ok

    residuals = structure_ok ? slacks(problem, solution) : Any[]
    affine_ok = exact_types_ok && structure_ok && all(iszero, residuals)
    block_results = [
        (
            key=repr(key),
            key_type=string(typeof(key)),
            valid=exact_psd(value),
        )
        for (key, value) in matrixvars(solution)
    ]
    objective_value = isnothing(objective_functional) || !structure_ok ?
        nothing :
        objvalue(objective_functional, solution)
    objective_ok = isnothing(expected_objective) ?
        true :
        exact_types_ok &&
        !isnothing(objective_value) &&
        objective_value == expected_objective
    return (
        valid=
            exact_types_ok &&
            structure_ok &&
            affine_ok &&
            all(result.valid for result in block_results) &&
            objective_ok,
        exact_types_ok=exact_types_ok,
        structure_ok=structure_ok,
        block_keys_ok=block_keys_ok,
        block_sizes_ok=block_sizes_ok,
        free_keys_ok=free_keys_ok,
        affine_ok=affine_ok,
        block_results=block_results,
        objective_ok=objective_ok,
        objective_value=objective_value,
        residual_count=length(residuals),
        block_count=length(block_results),
    )
end

"""
    verify_target_exact_solution(solution; ...)

Reconstruct the canonical fixed-objective problem and verify the supplied
solution against that reconstruction. No serialized problem object is trusted.
"""
function verify_target_exact_solution(
    solution;
    dimension::Int=TARGET_DIMENSION,
    costheta=TARGET_COSTHETA,
    d2::Int=TARGET_DEGREE,
    d3::Int=TARGET_DEGREE,
    expected_objective=TARGET_OBJECTIVE,
)
    sample_certificate = sample_unisolvence_certificate(d2, d3)
    sample_certificate.univariate_distinct ||
        error("canonical univariate sample set is not unisolvent")
    sample_certificate.full_rank ||
        error("canonical trivariate sample set is not unisolvent")
    canonical_problem = build_three_point_problem(
        dimension,
        costheta,
        d2,
        d3;
        fixed_objective=expected_objective,
    )
    verification = verify_exact_solution(
        canonical_problem,
        solution;
        expected_objective=expected_objective,
        objective_functional=original_objective(d2, d3),
    )
    return merge(
        verification,
        (
            target_binding_ok=true,
            sample_certificate=sample_certificate,
        ),
    )
end

end
