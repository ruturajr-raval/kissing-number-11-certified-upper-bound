# Research Plan

Status date: 2026-09-11

## Objective

Construct and independently verify a compact exact rational certificate for a
degree-17 Bachoc-Vallentin bound below 869 in dimension 11.

## Stage 1 - Formulation Audit

- Compare every matrix polynomial, normalization, domain weight, and objective
  term against the published problem and the pinned upstream implementation.
- Test small-degree instances against independently computed values.
- Bind the generated problem to deterministic parameter and source hashes.
- Prove that the canonical sampled residual map is injective on the declared
  symmetric polynomial space.

Acceptance gate: two construction paths agree on dimensions, samples,
constraints, objective terms, and a small numerical solution.

Current evidence: the 1,461 canonical trivariate samples have full evaluation
rank 1,461 modulo 65,521 for the symmetric degree-34 basis. The residual-space
audit verifies that every generated identity lies in that basis, and the
theorem bridge is recorded in `docs/THEOREM_BRIDGE.md`.

## Stage 2 - Numerical Reproduction

- Solve `n = 11`, `d = 17`, `cos(theta) = 1/2` at 256-bit precision.
- Retain the complete solver log and serialized primal-dual point.

Acceptance gate: objective below `868.84` with primal and dual residuals below
the declared thresholds.

Current evidence: complete. The retained 256-bit run returned status `pdOpt`,
zero solver error code, and objective
`868.826499507902298742415116214534666...`.

## Stage 3 - Fixed-Objective Interior Point

- Add the exact equality `objective = 86899/100`.
- Solve as a feasibility problem at 384 to 512 bits.
- Measure the minimum numerical eigenvalue and maximum affine residual.

Acceptance gate: successful primal-feasible status, exact target objective
within the declared tolerance, bounded affine residuals, and no materially
negative numerical eigenvalue. Exact PSD remains the proof-stage gate.

Current evidence: complete. The accepted 384-bit recovery has objective error
about `1.17e-68`, maximum sampled affine residual about `1.63e-71`, and
minimum matrix eigenvalue about `9.58e-15`.

## Stage 4 - Exact Rounding

- Project the numerical point into the exact rational affine space.
- Prefer common dyadic denominators and sparse corrections.
- Prove every matrix block positive semidefinite exactly.

Acceptance gate: all exact identities and positivity checks pass.

Current evidence: an exact projection run reached zero rational linear-system
slacks on 2026-09-10. Its first checkpoint used nonportable generic
serialization of Nemo FLINT handles and was rejected after a cross-process
crash. The replacement value-serialized `Rational{BigInt}` checkpoint passes
cross-process restoration. Primary verification of the final exact bundle
passes all 1,497 affine identities, the exact objective, and strict positivity
for all 70 matrix blocks. The exact bundle SHA-256 is
`c772fc1608d68f2198a53e823047e37e60d496e74b1017b76bcb73a5a6398560`.

## Stage 5 - Independent Verification

- Export a deterministic certificate independent of Julia serialization.
- Implement a streaming verifier using only integer or rational arithmetic.
- Compare certificate and problem hashes against the primary verifier.

Acceptance gate: both verifiers pass from a clean checkout.

Current evidence: the measured size audit rejects the explicit affine JSON
schema. The replacement direct-matrix witness has matching Julia, Python, and
C++ parsing behavior. The independent Python suite performs complete
coefficient replay on the solver-produced low-degree certificate and verifies
the package-manifest trust chain and recomputes both provenance digests.
Nondegenerate cross-language checks compare
all degree-17 `F` blocks and all 15 three-point SOS families. The final
dimension-11 package passes export-time captured-byte replay and a second
installed-file release-mode replay. The 14,850,075-byte witness has SHA-256
`bed94876a6275e7e680c682a0aeca8b8e65e6d55ba7b0b5f5833c5bd640e8229`;
the 12,458-byte manifest has SHA-256
`1a1f02f07f345129eb1541f30c38cedab2f141af429837d9dce6da41af6c6086`.
All 70 blocks are strictly positive, and every exact coefficient identity
passes.

## Stage 6 - Publication Gate

- Refresh prior art.
- Build the technical paper and release assets.
- Run local and hosted clean-room verification.
- Release only if the theorem, claim boundary, certificate, and paper agree.

Current evidence: the local mathematical, compactness, resource, and
manuscript gates pass. The four-page manuscript builds without TeX errors or
warnings and passes visual inspection. The final prior-art refresh completed
on 2026-09-10 without locating an equivalent public certificate. Public
candidate, final-main, tag, and release workflows pass. GitHub release
`386719977` is immutable, and Zenodo record `22699475` was published from the
exact verified GitHub asset set and independently download-verified. Stage 6
is complete.

## Resource And Kill Gates

- Maximum initial solve time: 24 hours.
- Maximum memory: 48 GiB.
- Maximum exact projection and primary verification: six hours and 24 GiB,
  with an input- and source-bound resumable projection checkpoint.
- Maximum compressed certificate: 50 MB.
- Maximum independent verification: two hours and 16 GiB.
- No result release before exact verification.
- Stop or redesign if the degree-17 objective is not below `868.84`.
- Stop or redesign if fixed-objective slack is insufficient for stable exact
  rounding.
