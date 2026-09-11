# Exact Certification of the 11-Dimensional Kissing-Number Upper Bound

## Project Overview

| Field | Value |
| --- | --- |
| Author | Ruturaj R Raval |
| Affiliation | Independent Researcher |
| ORCID | [0000-0003-4930-8981](https://orcid.org/0000-0003-4930-8981) |
| Field | Discrete geometry, semidefinite programming, and exact computation |
| Problem | Certify the reported upper bound `tau_11 <= 868` |
| Current result | A compact exact certificate establishes `tau_11 <= 868`; public hosted replay passes |
| Result type | Exact rational semidefinite-program certificate |
| Release | `v0.1.0` public release candidate |
| Version DOI | not yet assigned |
| Concept DOI | not yet assigned |
| License | MIT |

This repository develops a compact, independently checkable exact certificate
for the reported 11-dimensional kissing-number upper bound. The numerical
degree-17 Bachoc-Vallentin three-point bound is `868.82650`. The certification
target fixes the objective at

```text
86899/100 = 868.99 < 869,
```

so any exact feasible solution proves the integer upper bound
`tau_11 <= 868`.

## Problem And Background

The kissing number `tau_n` is the maximum number of nonoverlapping unit
spheres in `R^n` that can simultaneously touch one central unit sphere. It is
equivalently the maximum size of a spherical code in `S^(n-1)` with pairwise
inner products at most `1/2`.

Bachoc and Vallentin introduced a three-point semidefinite-programming bound
for spherical codes. Machado and de Oliveira later obtained a rigorous
degree-16 upper bound that implies `tau_11 <= 869`. Leijenhorst and de Laat
reported the stronger degree-17 numerical value `868.82650`, while explicitly
stating that their table was not rigorously verified.

## Starting Frontier And Longstanding Gap

The dated audit begun on 2026-09-09 and refreshed on 2026-09-10 found later
tables quoting the integer upper bound 868, but located no equivalent public
exact or outward-rounded certificate for the underlying 11-dimensional
degree-17 computation. The gap addressed here is therefore certification,
not discovery of a lower numerical objective.

The numerical table first appeared in the 2022 preprint. Its dimension-11
degree-17 value had therefore remained without a located public exact
certificate for more than four years at the audit date.

The starting exact upper bound is 869. The exact feasible degree-17 solution
has objective `868.99`, lowering the rigorous integer upper bound by one.

## Main Result

The exact certificate establishes `tau_11 <= 868`. Its verified components
are:

1. An exact rational generator for the degree-17 three-point problem.
2. A deterministic canonical sample set with SHA-256 binding.
3. A modular full-rank proof for the 1,461-dimensional symmetric residual
   space, establishing sample unisolvence over the rationals.
4. A complete theorem bridge from the implemented reduced dual to a
   spherical-code upper bound.
5. A completed 256-bit numerical reproduction with status `pdOpt` and objective
   `868.8264995079022987424...`.
6. An accepted 384-bit fixed-objective point at `86899/100`, with maximum
   sampled affine residual about `1.63e-71` and minimum matrix eigenvalue about
   `9.58e-15`.
7. An exact rounding route that reconstructs the canonical problem and checks
   exact types, block layout, objective, affine identities, and rational PSD.
8. Enforced solve limits and checkpoint gates.
9. A measured rejection of the oversized explicit affine JSON design.
10. A deterministic binary writer for exact rational symmetric upper
    triangles, with matching Julia, Python, and C++ parsing behavior.
11. A standard-library Python coefficient verifier and strict package
    manifest verifier with 56 passing tests.
12. A solver-produced low-degree compact certificate that passes exact Julia
    verification and complete independent Python coefficient replay.
13. A cross-language formulation certificate checking all 35 scalar kernels,
    three contractions for each of the 18 degree-17 `F` blocks, six
    interval-SOS contractions, and three contractions for each of the 15
    three-point SOS families at degree 6.
14. A descriptor-anchored export snapshot containing read-only source copies
    and implemented dependency, artifact, runtime-tree, and exact-input
    binding. Both dependency audits and mandatory captured-byte replay pass on
    the real exact input.
15. Commit-sourced trust-anchor orchestration binding the clean Git commit,
    copied Julia executable, complete Julia runtime tree, and certificate
    files around independent replay.
16. A process-portable exact-solution encoding using value-serialized
    `Rational{BigInt}` upper triangles, with cross-process restoration tests.
17. A sample-by-sample exact affine verifier that is canonically equivalent
    to the original full-vector slack computation without its large temporary
    sampled-polynomial allocations.
18. A 14,850,075-byte exact `KNWIT003` witness and 12,458-byte manifest whose
    release-mode replay verifies all 70 blocks, 35 univariate coefficients,
    and 1,461 symmetric trivariate coefficients in 907.16 seconds using
    187,596,800 bytes maximum RSS.

Publication remains fail-closed until the final release commit passes public
CI and immutable tag-bound asset verification passes.

## Method And Proof Architecture

The intended proof chain is:

1. Reproduce the reported degree-17 numerical objective for `n = 11`.
2. Replace objective minimization by the exact equality
   `objective = 86899/100`.
3. Solve the resulting feasibility problem at high precision with a strictly
   feasible numerical point.
4. Project that point into the exact affine constraint space over `Q`.
5. Verify every polynomial identity exactly.
6. Verify positive semidefiniteness of every rational matrix block.
7. Serialize a compact, deterministic certificate.
8. Replay the certificate with a second implementation that does not call the
   numerical solver.

The formulation uses degree `d = 17`, dimension `n = 11`, and
`cos(theta) = 1/2`.

## Verification And Evidence

The primary implementation uses `ClusteredLowRankSolver.jl` 2.2.0 at pinned
commit `09ac81aed031bdea714832cf515244f6eb223531`, together with Nemo exact
arithmetic. The formulation is derived from the solver's MIT-licensed
three-point example and the published Bachoc-Vallentin program.

The degree-17 sample certificate proves rank `1461` modulo `65521` for the
`1461 x 1461` symmetric-basis evaluation matrix. Its canonical sample-set
SHA-256 is
`9b8af0d4133749c485c9e36269d2f606a18427a3c17af7875665c5d293f97351`.
Full rank modulo one prime proves full rank over the rationals.

The fixed-objective problem has 3 affine constraints, sample counts
`35`, `1461`, and `1`, and 70 PSD blocks. The symmetric upper triangles
contain 346,343 rational entries in total, and the largest block has order
378. `evidence/problem-structure.json` records the complete expected layout.

The retained dimension-11 numerical reproduction completed with objective
`868.826499507902298742415116214534666...`, below the `868.84` gate. The
accepted fixed-objective recovery has objective error about `1.17e-68`,
maximum sampled affine residual about `1.63e-71`, and minimum matrix
eigenvalue about `9.58e-15`. These are numerical precursor results, not the
exact theorem certificate.

`evidence/residual-space.json` records the independent degree and symmetry
audit: 2,757 univariate coefficient entries, 2,109 three-point kernel entries,
15 invariant SOS blocks, maximum residual degree 34, and symmetric residual
space dimension 1,461. The evidence-file SHA-256 is
`8c8ba60be47d795ef7ddc960d9cc0b99044839b93ad93ddfbbec77e11402776b`.

The independent verifier is in `verifier/`. It parses the exact rational
`KNWIT003` witness, reconstructs the fixed Project 10 formulas without Julia
or the numerical solver, and checks the objective, all 35 univariate
coefficients, all 1,461 symmetric trivariate coefficients, and strict
positivity of every release matrix. Its public command is permanently pinned
to the dimension-11, degree-17 target.

The package verifier also checks the JSON manifest, witness hash and size,
all 70 block ranks, source and evidence hashes, provenance digests, and the
independently recomputed problem descriptor. The 56-test suite covers exact
formula replay, malformed witness encodings, package tampering, path safety,
published-hash mismatch, provenance recomputation, immutable-byte replay, and
the solver-produced low-degree certificate.

`evidence/explicit-schema-audit.json` rejects that first explicit affine JSON
design. The 1,663,458 nonzero three-point `F` terms alone require at least
93,153,648 bytes under that schema, before the SOS equations or witness are
encoded. The full expansion has an upper bound of 505,535,295 terms.

The replacement witness stores each exact rational symmetric upper triangle.
The release verifier proves strict positivity by directed 896-bit interval
Cholesky. The retained low-degree fixture is a 560-byte, 16-block witness with
dimension sum 28 and 46 stored rationals.
Fresh pilot solves can round to different exact feasible points and therefore
need not reproduce the fixture bytes. Julia reconstructs every original
matrix exactly. Python parses the same retained bytes and independently
verifies the exact objective and both polynomial identities.

The release-candidate certificate files are:

- manifest SHA-256
  `1a1f02f07f345129eb1541f30c38cedab2f141af429837d9dce6da41af6c6086`;
- witness SHA-256
  `bed94876a6275e7e680c682a0aeca8b8e65e6d55ba7b0b5f5833c5bd640e8229`;
- problem descriptor SHA-256
  `cd4c6e834cac9addee47196f36b5b7b96f6020eeaa56a00fe989033b4f4ed67d`.

The deterministic compressed-package preflight is 14,565,324 bytes, below
the 50 MB gate. Independent release-mode verification takes 907.16 seconds
and 187,596,800 bytes maximum RSS, below the two-hour and 16 GiB gates.

`evidence/cross-language-formulation.json`, SHA-256
`c13e32379d836474fce93b32821103aa08de9cfc2a8ca61c08fe93dce67e6b94`,
records nondegenerate comparisons between Julia's actual problem-generator
coefficients and the independent Python formulas. The checks cover all 35
scalar terms, three contractions for each of the 18 `F` blocks through degree
17, both interval SOS blocks, and three contractions for each of the 15
three-point SOS families at degree 6.

Evidence files are written only after a stage completes. A final result must
include numerical logs, exact-solution metadata, exact matrix and identity
checks, certificate hashes, and an independent verifier transcript.

Certificate export executes from a descriptor-anchored isolated snapshot
containing read-only copies of every bound source, evidence file, and exact
input. Startup files and compiled caches are disabled, and the bootstrap
checks all 27 pinned dependency source trees and 3 selected artifact trees
before and after execution. The wrapper publishes each output only to its
fixed filename through an atomic no-follow directory-descriptor replacement,
with the manifest installed last. An exclusive publication lock prevents
interleaved exporters. The exact input is hash-checked before deserialization,
and the independent package verifier replays immutable copies of the exact
captured output bytes that are later installed. Final replay is additionally
bound to a named clean Git commit, a copied SHA-256-pinned Julia 1.12.7
executable, and a complete runtime-tree digest. An externally supplied
`env -i` and `zsh -f` bootstrap starts before repository-controlled or
user-startup code, then loads the authoritative checker and manifest verifier
from the expected commit rather than the mutable worktree. The worktree
`make release-check` target refuses by design. Git replacement refs are
disabled and both certificate files are rehashed after replay.

## Reproduction

Use Julia 1.10 or later:

```bash
make instantiate
make test
make test-supervisor
make test-verifier
make test-compact-witness
make test-cpp-witness
make samples
make structure
make residual-space
make cross-language
make schema-audit
make smoke
make smoke-exact
```

Launch the published-objective reproduction with:

```bash
JULIA_NUM_THREADS=12 make reproduce
```

Launch the fixed-objective solve with:

```bash
JULIA_NUM_THREADS=12 make fixed
```

Exact rounding is a separate stage:

```bash
JULIA_NUM_THREADS=12 make round
```

The expensive affine projection is converted from process-local Nemo rationals
to value-serialized `Rational{BigInt}` upper triangles and saved atomically
before full verification, so a source- and input-matched restart can resume
without repeating it. A 2026-09-10 run reached exact zero projection slacks,
but its first checkpoint used unsafe generic serialization of FLINT handles;
that artifact was archived and rejected. The replacement portable checkpoint
and final exact bundle pass cross-process restoration and primary verification.
The exact bundle is
`build/degree17-exact-86899-over-100.jls`, SHA-256
`c772fc1608d68f2198a53e823047e37e60d496e74b1017b76bcb73a5a6398560`.

The full degree-17 solve is expected to require hours and tens of gigabytes of
memory. The standard targets enforce the declared wall-time and resident-memory
limits, use source-bound restart checkpoints, and leave no accepted artifact
after a failed gate. No GPU is used.

## Claims

The supported result is:

```text
The 11-dimensional kissing number satisfies tau_11 <= 868.
```

## Limitations And Nonclaims

This package proves `tau_11 <= 868`. It does not determine `tau_11`, improve
the reported numerical optimum, provide a new lower bound, or certify any
other dimension.

It does not determine the exact value of `tau_11`, settle the parent kissing-
number problem, establish a new numerical bound, or prove an optimal
certificate size. Independent external mathematical review and peer review
remain absent.

The numerical solver is not itself a proof. The proof is supplied by exact
affine identities, exact positivity checks, the compact certificate, both
verifier paths, and the theorem bridge. The final prior-art refresh completed
on 2026-09-10 without locating an equivalent public certificate.

The explicit affine schema is not release-eligible and its implementation has
been removed. Its measured rejection remains as evidence. The compact
verifier has now replayed the real dimension-11 witness successfully.

The full-rank sample result proves that zero residuals at the canonical
trivariate samples imply coefficient equality within the declared symmetric
degree-34 residual space. It does not prove feasibility of the target
dimension-11 solution.

`docs/THEOREM_BRIDGE.md` proves that any exact feasible solution of the
implemented reduced program gives the stated spherical-code upper bound. It
also explains why objective `86899/100` implies the integer result 868.

## Significance And Use

The exact certificate converts a widely quoted numerical upper bound into a
reproducible theorem and improves the rigorous integer upper bound from 869 to
868. The certificate format and streaming verifier could also support exact
validation of other spherical-code semidefinite bounds.

No direct industrial or physical application is claimed.

## Remaining Work And Future Directions

The numerical, exact projection, primary verification, compact export,
independent replay, size, and resource gates are complete.

The four-page manuscript builds without TeX warnings or errors and passes
visual inspection.

The immediate gates are:

1. Create the final release-readiness commit and pass public CI on that exact
   commit.
2. Freeze that exact commit, annotated `v0.1.0` tag, and immutable
   GitHub release assets.
3. Create, verify twice, publish, and independently download-verify the Zenodo
   version from those exact public assets.

The mathematical certificate no longer needs redesign. Remaining work is
publication hardening and external verification.

## Repository Layout

```text
src/          exact problem generator and certificate logic
scripts/      numerical, fixed-objective, and exact-rounding entry points
test/         formulation and smoke tests
verifier/     independent compact package and coefficient verifiers
docs/         prior-art, method, and research-plan records
research/     machine-readable claim and release gates
evidence/     completed-stage evidence
certificates/ final proof artifacts
paper/        technical paper source and compiled release PDF
```

## Publication Citation And Archive

The public repository and candidate hosted replay are complete. The final
release-commit replay, immutable GitHub release, version DOI, concept DOI, and
independent archive download verification remain pending the ordered
publication gates.

## Authorship

Ruturaj R Raval, Independent Researcher, ORCID
`0000-0003-4930-8981`, is responsible for the project claims and release
decisions.

## Licensing And Provenance

Project-original code and documentation are licensed under MIT.
`ClusteredLowRankSolver.jl` is MIT-licensed third-party software. Its example
formulation and publications are identified in `THIRD_PARTY_NOTICES.md`.

## References

1. C. Bachoc and F. Vallentin, "New upper bounds for kissing numbers from
   semidefinite programming," Journal of the American Mathematical Society
   21 (2008), 909-924.
2. F. C. Machado and F. M. de Oliveira Filho, "Improving the Semidefinite
   Programming Bound for the Kissing Number by Exploiting Polynomial
   Symmetry," Experimental Mathematics 27 (2018), 362-369.
3. N. Leijenhorst and D. de Laat, "Solving clustered low-rank semidefinite
   programs arising from polynomial optimization," arXiv:2202.12077.
4. H. Cohn, D. de Laat, and N. Leijenhorst, "Optimality of spherical codes
   via exact semidefinite programming bounds," arXiv:2403.16874.
