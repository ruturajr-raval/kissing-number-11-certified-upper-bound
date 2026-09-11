# Release Notes

## v0.1.0 - 2026-09-11

Public release:
https://github.com/ruturajr-raval/kissing-number-11-certified-upper-bound/releases/tag/v0.1.0

- Implements the exact rational degree-17 reduced three-point problem.
- Adds fixed-objective feasibility at `86899/100`.
- Reproduces the dimension-11 degree-17 numerical objective at
  `868.8264995079022987424...` with status `pdOpt`.
- Retains an accepted 384-bit fixed-objective numerical point with maximum
  sampled affine residual about `1.63e-71` and minimum matrix eigenvalue about
  `9.58e-15`.
- Proves canonical sample unisolvence and the residual-space premise.
- Records the theorem bridge from exact feasibility to `tau_11 <= 868`.
- Rejects the oversized explicit affine JSON certificate design.
- Implements deterministic exact rational symmetric upper-triangle witness
  writing with `KNWIT003`.
- Adds strict Julia, Python, and C++ witness parsers and tests.
- Adds complete independent coefficient replay for the exact pilot.
- Adds nondegenerate Julia-Python formulation checks.
- Adds strict package-manifest, provenance, and published-hash binding.
- Recomputes fixed-objective, rounding, and primary-verification provenance
  from bound source files.
- Replaces unsafe generic serialization of Nemo FLINT-backed rationals with a
  process-portable `Rational{BigInt}` upper-triangle checkpoint and final
  bundle representation.
- Verifies affine identities sample by sample in process-isolated,
  two-thread, 100-sample chunks to bound retained FLINT allocator memory.
- Produces and independently restores a 24,196,706-byte portable exact bundle,
  SHA-256
  `c772fc1608d68f2198a53e823047e37e60d496e74b1017b76bcb73a5a6398560`,
  after verifying all 1,497 affine identities, the exact objective, and all 70
  strict-positive matrix blocks.
- Exports a 14,850,075-byte `KNWIT003` witness with SHA-256
  `bed94876a6275e7e680c682a0aeca8b8e65e6d55ba7b0b5f5833c5bd640e8229`
  and a 12,458-byte manifest with SHA-256
  `1a1f02f07f345129eb1541f30c38cedab2f141af429837d9dce6da41af6c6086`.
- Passes release-mode independent verification with 70 strict-positive
  blocks, zero PSD fallbacks, 35 univariate coefficients, and 1,461 symmetric
  trivariate coefficients in 907.16 seconds using 187,596,800 bytes maximum
  RSS.
- Passes the compactness gate with a deterministic compressed-package size of
  14,565,324 bytes.
- Reuses one no-follow immutable witness snapshot for package and coefficient
  verification.
- Adds descriptor-anchored export snapshots, read-only source copies,
  dependency and artifact tree verification, fixed fail-closed publication,
  an exclusive publication lock, exact-input authentication, captured-byte
  independent replay before installation, and supervised certificate export.
- Adds a commit-sourced trust-anchor release orchestrator requiring a named
  clean Git commit, a commit-tree-derived repository manifest, an isolated
  Python interpreter, a copied SHA-256-pinned Julia 1.12.7 executable, a full
  runtime-tree digest, and all four certificate trust anchors.
- Disables Git replacement refs and rehashes both certificate files after
  replay.
- Rejects artifact overrides, loader-variable injection, and mutable
  worktree bootstrapping of the authoritative release check. The release gate
  starts under an externally supplied empty environment with shell startup
  files disabled.
- Enforces process-tree wall-time and resident-memory limits.
- Completes the final 2026-09-10 prior-art refresh without locating an
  equivalent public exact or outward-rounded dimension-11 certificate below
  869.
- Adds a public hosted workflow that replays the exact certificate, rebuilds
  the paper from the tagged source, constructs deterministic release archives,
  and verifies local and remote asset digests.
- Records successful public candidate run `34547450259` on commit
  `ca28575103a1342d443d23fdc96ad2d67b162fb0`; the downloaded hosted paper and
  release inventory match the local files byte for byte.
- Adds 16 tests for deterministic release assets, committed-paper binding, and
  Zenodo metadata and file verification.
- Publishes the release through a verified draft and only then makes the
  GitHub release immutable.
- Includes the inspected paper PDF, deterministic source archive, standalone
  certificate-and-verifier archive, and `SHA256SUMS`.
- Establishes `tau_11 <= 868`.
- Leaves DOI fields unassigned until Zenodo archives and independently
  verifies the exact immutable GitHub release files.
