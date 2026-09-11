# Compact Certificate Schema Version 2

Status date: 2026-09-10

## Scope

Version 2 encodes only exact rational PSD matrix blocks. It does not encode a
sampled affine system. Both verifiers reconstruct the fixed mathematical
problem from source.

The release artifacts are:

```text
kn11-degree17-certificate-v2.json
kn11-degree17-witness-v2.bin
```

The JSON file records hashes and descriptive metadata. The binary witness is
the proof data consumed by the independent coefficient verifier.

The manifest's `provenance` object contains structured
`source_specification`, `rounding_specification`, and
`verification_specification` records. Each record has:

1. `fields`, the exact ordered strings used to define the specification.
2. `digest`, SHA-256 of those fields joined by LF with one final LF.

The verifier reconstructs the expected field lists from the fixed target and
the independently hashed source files. A matching opaque digest without the
matching fields is rejected.

## Fixed Target

The public verifier compiles these values into its source:

| Field | Value |
| --- | --- |
| Dimension | `11` |
| Degree | `17` |
| Maximum inner product | `1/2` |
| Fixed objective | `86899/100` |
| Matrix blocks | `70` |
| Univariate coefficients | `35` |
| Symmetric trivariate coefficients | `1461` |
| Claimed consequence after exact verification | `tau_11 <= 868` |

The command-line interface cannot replace these parameters.

## Binary Encoding

The first eight bytes are:

```text
KNWIT003
```

They are followed by a little-endian 32-bit block count and one block record
for every canonical block. Blocks occur in strict lexicographic name order,
but names are not stored because the fixed layout supplies them.

Each block stores:

1. A little-endian 16-bit dimension.
2. A sorted table of distinct positive denominators.
3. The `m(m+1)/2` upper-triangle entries in row-major order.

Variable lengths and denominator indices use canonical unsigned LEB128. Big
integers use minimal big-endian magnitude bytes. Every rational must be
reduced. Zero has sign byte zero and no magnitude. No trailing byte is
permitted.

For each block, the stored values directly define the symmetric matrix:

```text
X_ji = X_ij,  0 <= i <= j < m.
```

The release verifier proves strict positivity with directed fixed-point
interval Cholesky at 896 bits. Complete package verification requires all 70
blocks to pass that proof with no fallback. A bounded exact rational fallback
exists only for standalone low-degree tests with singular PSD blocks.

## Canonical Block Layout

The layout contains:

- `F/00` through `F/17`, with dimensions 18 through 1;
- `a/00` through `a/34`, each with dimension 1;
- `univariatesos/1` and `univariatesos/2`, with dimensions 18 and 17;
- 15 `trivariatesos/<weight>/<representation>` blocks with dimensions
  recorded in `evidence/problem-structure.json`.

The largest block has dimension 378.

## Exact Equation Replay

The verifier computes:

```text
1 + sum_k a_k + <J,F_0>
```

and requires exact equality with `86899/100`.

For the interval identity, it reconstructs normalized Gegenbauer
polynomials, symmetrized three-point kernels at `(w,w,1)`, and both Chebyshev
SOS terms. Every coefficient through degree 34 must be zero.

For the three-point identity, it reconstructs the `F` kernels, five domain
weights, and trivial, alternating, and standard `S_3` representation
kernels. Every coefficient in

```text
e1^a e2^b e3^c,  a + 2b + 3c <= 34,
```

must be zero.

## Resource Limits

The parser enforces explicit limits on file size, block count, dimensions,
declared full-rank sum, rational count, denominator-table size, and integer
bit length. It rejects symlink witness paths, checks dimension and rational
budgets before allocating a block, and reuses one authenticated immutable byte
snapshot for manifest binding and coefficient replay.
Release acceptance additionally requires:

- compressed certificate below 50 MB;
- verification below two hours;
- peak resident memory below 16 GiB.

Internal acceptance margins are 45 MiB, 90 minutes, and 12 GiB.

## Rejected Version 1

The discarded version-1 prototype expanded all sampled affine terms into
JSON. `evidence/explicit-schema-audit.json` proves that the nonzero
three-point `F` terms alone require at least 93,153,648 bytes in that schema.
That exceeds the compactness gate before SOS terms or witness matrices are
included. Version 1 is retained only as an audited design rejection, not as a
supported certificate format.
