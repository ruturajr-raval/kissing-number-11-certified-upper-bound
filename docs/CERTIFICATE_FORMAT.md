# Compact Certificate Format

Status date: 2026-09-10

This document specifies the candidate version-2 certificate architecture for
the exact bound `tau_11 <= 868`. It is a prerelease format until the exported
degree-17 witness passes both verification implementations and every resource
gate.

## Reason For The Redesign

The first verifier prototype encoded all 1,497 sampled affine equations as
explicit sparse JSON terms. That representation is exact but not compact.

`evidence/explicit-schema-audit.json` measures:

- 505,535,295 possible expanded terms in the complete sampled system;
- 1,663,458 nonzero three-point `F` terms alone;
- at least 93,153,648 bytes for those `F` terms under the prototype's minimum
  term encoding.

The `F`-only lower bound already exceeds the 50 MiB certificate gate. Version
1 is therefore rejected for release use.

## Release Artifacts

A candidate certificate consists of:

1. `kn11-degree17-certificate-v2.json`, a small human-readable manifest.
2. `kn11-degree17-witness-v2.bin`, the exact rational matrix witness.
3. The canonical formulation, theorem-bridge, and evidence files named and
   hashed by the manifest.
4. Verification transcripts from the primary Julia verifier and the
   independent coefficient verifier.

The manifest records the author, affiliation, ORCID, target parameters,
formula revision, problem descriptor hash, source hashes, evidence hashes,
block dimensions and declared full ranks, witness hash and size, rational bit
lengths, and structured solver and rounding provenance. Each provenance
object includes the ordered source fields and their recomputed SHA-256 digest.

## Binary Witness

The witness magic is:

```text
KNWIT003
```

All fixed-width integers are little-endian. Variable lengths and denominator
indices use canonical unsigned LEB128. Big integers use minimal big-endian
magnitudes with no leading zero.

The file contains:

1. Eight-byte magic.
2. A 32-bit block count.
3. One block record for every matrix block in canonical name order.
4. No trailing bytes.

Each block record contains:

1. 16-bit dimension.
2. A strictly increasing table of positive denominators.
3. The `m(m+1)/2` exact upper-triangle entries in row-major order.

Every rational is reduced. A numerator uses one sign byte followed, when
nonzero, by a canonical magnitude. Every block has at least denominator `1`,
including an all-zero block.

## PSD Semantics

For a block of dimension `m`, the witness directly defines the symmetric
rational matrix:

```text
X_ji = X_ij,  0 <= i <= j < m.
```

The release verifier proves every matrix strictly positive definite using
directed fixed-point interval Cholesky at 896 bits. Package verification
requires all 70 blocks to pass this path and rejects any fallback. The generic
low-degree test API also has a resource-bounded exact rational PSD fallback
for singular matrices of order at most 32; it is not accepted for the release
package. The parser rejects nonreduced rationals, noncanonical integer
encodings, missing blocks, wrong dimensions, excess resource use, and trailing
bytes.

## Equation Verification

The witness does not encode the sampled affine matrix. Each verifier
reconstructs the mathematical formulation from:

```text
n = 11
d2 = d3 = 17
cos(theta) = 1/2
objective = 86899/100
```

The exact checks are:

1. Objective:

   ```text
   1 + sum_k a_k + <J, F_0> = 86899/100.
   ```

2. Univariate identity:

   Reconstruct the normalized Gegenbauer basis, symmetrized three-point
   kernels at `(w,w,1)`, both Chebyshev SOS blocks, and compare all 35
   coefficients through degree 34.

3. Trivariate identity:

   Reconstruct the three-point kernels, the five domain weights, and the
   trivial, alternating, and standard `S_3` representation kernels. Accumulate
   all 1,461 coefficients in the basis

   ```text
   e1^a e2^b e3^c,  a + 2b + 3c <= 34.
   ```

4. Require every residual coefficient to be exactly zero over the rationals.

The standard-representation kernels are:

```text
K11 = 2(e1^2 - 3e2)
K12 = 9e3 - e1e2
K22 = 2(e2^2 - 3e1e3)
```

The alternating kernel is the cubic discriminant:

```text
e1^2 e2^2 - 4e2^3 - 4e1^3 e3 - 27e3^2 + 18e1e2e3.
```

Coefficient verification avoids approximately one billion sampled rational
multiply-add operations. The audited coefficient route requires on the order
of 4.8 million structured updates before exact integer-arithmetic costs.

## Trust Boundary

The witness may not choose its own mathematical problem.

The verifier compiles or receives an externally published problem descriptor
hash that binds:

- target dimension, degree, angle, and objective;
- formula revision;
- canonical block layout;
- sample and residual-space evidence;
- theorem bridge.

The manifest binds the witness and every named source or evidence file by
SHA-256. The independent verifier reconstructs the fixed-objective solver
specification from the bound module, project, dependency manifest, solver
entry point, sample result, parameters, precision, and solver revision. It
then reconstructs the rounding specification from the bound rounding script
and fixed settings. Neither provenance digest is accepted as an opaque
manifest value.

The package verifier reads the witness once through a no-follow stable file
descriptor and reuses the resulting immutable bytes for block parsing and
coefficient replay. A release must publish the problem descriptor hash,
witness hash, and both provenance digests in the paper, release notes, and
archive metadata.

The exporter copies every bound source, evidence file, and exact input through
no-follow descriptors into an isolated snapshot containing read-only copies. A
launcher enters that snapshot with `fchdir` before executing Julia. Startup
files and compiled-module caches are disabled. Before and after the project
code runs, the bootstrap verifies every manifest-bound dependency source tree
and every selected artifact tree against its content hash, with artifact
overrides forbidden. The complete Julia runtime tree and an isolated copy of the
Julia executable are bound by separate SHA-256 values. The exact input is
checked against an external SHA-256 before Julia deserializes it.

Each output is published by an atomic no-follow directory-descriptor
replacement at one of the two fixed release filenames. The witness is
installed first and its authenticating manifest last. The pair is not one
filesystem-atomic operation, but interruption is fail-closed because an old
manifest cannot authenticate a new witness. Environment variables, symlinked
parent directories, and arbitrary output paths cannot redirect the release
write. An exclusive publication lock prevents concurrent exporters from
interleaving the two-file installation. Before either file is installed, the
independent package verifier replays immutable copies of the exact captured
certificate bytes. The exporter then installs those same in-memory bytes, so
post-replay replacement of the generator's output paths cannot alter the
published pair.

The final release gate starts from an independently retained bootstrap under
`env -i` and `zsh -f`, before any repository-controlled or user-startup code.
The worktree Makefile cannot authorize a release. The bootstrap loads its
Python orchestrator and repository-manifest verifier directly from the
expected Git commit. It validates all trust anchors as fixed-length
hexadecimal values, sanitizes Git and build environment overrides, derives
the repository manifest from the expected commit tree with Git replacement
objects disabled, and requires the same clean commit before and after complete
replay. The orchestrator requires isolated Python startup. It checks an isolated
copy of the Julia 1.12.7 executable and the complete Julia runtime tree against
published SHA-256 values, then rehashes both Git-ignored certificate files
before and after replay.

These controls assume exclusive control of the release account while the gate
runs. A concurrently malicious process with the same user identity and write
access to the repository, dependency depot, or Julia installation is outside
the local tool's threat model.

## Resource Gates

Public limits:

- compressed certificate below 50 MB;
- either verifier below two hours and 16 GiB RAM.

Internal acceptance margins:

- compressed certificate at most 45 MiB;
- verification at most 90 minutes;
- peak resident memory at most 12 GiB.

The release transcript must also report:

- raw and compressed witness size;
- rational count;
- maximum numerator and denominator bit lengths;
- block rank sum;
- coefficient-verification time;
- peak resident memory;
- exact objective and zero-residual results.

## Current Status

Completed:

- dense schema rejection with retained evidence;
- exact deterministic upper-triangle encoding;
- Julia, Python, and C++ agreement on canonical fixture bytes;
- solver-produced degree-2 compact witness;
- exact Julia reconstruction of all pilot blocks;
- independent Python coefficient replay of the complete pilot certificate;
- exact polynomial and invariant-basis utilities with adversarial tests;
- strict package-manifest verification and published-hash binding;
- independent recomputation of solver and rounding provenance;
- immutable-byte witness replay with symlink rejection;
- descriptor-anchored export snapshots containing read-only copies;
- implemented pre-import and post-export dependency and artifact tree gates,
  with both audits passing on the real exact input;
- fixed fail-closed descriptor-based output publication with an exclusive
  publication lock and mandatory independent replay before installation;
- exact-input binding before deserialization and captured-byte replay plus
  publication;
- commit-sourced trust-anchor binding around final release replay;
- isolated Python startup, replacement-ref rejection, Julia executable and
  runtime-tree binding, artifact-override rejection, and post-replay
  certificate rehashing;
- nondegenerate Julia-Python checks for 35 scalar terms, 54 degree-17 `F`
  contractions, both interval SOS blocks, and 45 three-point SOS
  contractions;
- a 14,850,075-byte final witness containing 346,343 exact rationals and all
  70 release blocks;
- successful captured-byte and installed-file release-mode replay with zero
  exact PSD fallbacks;
- a 14,565,324-byte deterministic compressed package and a 907.16-second
  independent replay using 187,596,800 bytes maximum RSS.

Pending:

- clean hosted replay by both implementations.
