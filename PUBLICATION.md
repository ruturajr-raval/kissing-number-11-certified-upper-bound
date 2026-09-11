# Publication Dossier

## Release Identity

| Field | Value |
| --- | --- |
| Title | Exact Certification of the 11-Dimensional Kissing-Number Upper Bound |
| Author | Ruturaj R Raval |
| Affiliation | Independent Researcher |
| ORCID | `0000-0003-4930-8981` |
| Candidate version | `v0.1.0` |
| Release date | 2026-09-11 |
| License | MIT |
| Package status | public hosted-replay verified release candidate |

## Claim-Safe Public Summary

This package contains a compact exact certificate for the reported degree-17
upper bound on the 11-dimensional kissing number. The certificate fixes the
objective at `86899/100` and passes primary and independent exact
verification, establishing `tau_11 <= 868`.

## Current Supported Result

The supported result and proof infrastructure are:

1. Exact rational construction of the reduced three-point program.
2. Canonical degree-17 sample binding and modular unisolvence.
3. A residual-space certificate and complete theorem bridge.
4. Rejection of an explicit affine schema that cannot meet the size gate.
5. A deterministic compact rational upper-triangle writer with Julia, Python,
   and C++ parser agreement.
6. Complete independent coefficient replay of a solver-produced exact pilot.
7. Nondegenerate cross-language checks of all 35 scalar kernels, three
   contractions for every degree-17 `F` block, three contractions for every
   three-point SOS family at degree 6, and six interval-SOS contractions.
8. A strict package-manifest verifier with tests for source, evidence,
   block-rank, witness, provenance, and published-hash binding.
9. Descriptor-anchored export snapshots containing read-only source copies,
   dependency and artifact tree verification, exact-input authentication,
   captured-byte replay, fixed fail-closed publication, and externally
   bootstrapped commit-sourced release binding for Git, Julia, and certificate
   anchors.
10. A completed 256-bit dimension-11 numerical reproduction with status
    `pdOpt` and objective `868.8264995079022987424...`.
11. An accepted 384-bit fixed-objective point with maximum sampled affine
    residual about `1.63e-71` and minimum matrix eigenvalue about `9.58e-15`.
12. A process-portable dimension-11 exact bundle whose primary replay verifies
    all 1,497 affine identities, the exact target objective, and strict
    positivity of all 70 matrix blocks.
13. A 14,850,075-byte compact witness and 12,458-byte manifest whose
    release-mode independent replay passes all exact coefficient and
    positivity checks in 907.16 seconds with 187,596,800 bytes maximum RSS.

Both dependency audits, in-snapshot captured-byte replay, fail-closed
publication, installed-file release-mode replay, and the final prior-art
refresh pass. Public candidate run `34547450259` passes on commit
`ca28575103a1342d443d23fdc96ad2d67b162fb0`, and its uploaded paper and
release assets are byte-identical to the local inventory. Publication remains
fail-closed pending CI on the final release commit and immutable tag-bound
assets.

## Verification Evidence

The current evidence includes:

- sample rank `1461` modulo `65521`;
- sample SHA-256
  `9b8af0d4133749c485c9e36269d2f606a18427a3c17af7875665c5d293f97351`;
- residual-space SHA-256
  `8c8ba60be47d795ef7ddc960d9cc0b99044839b93ad93ddfbbec77e11402776b`;
- cross-language check SHA-256
  `c13e32379d836474fce93b32821103aa08de9cfc2a8ca61c08fe93dce67e6b94`;
- 56 passing independent Python tests;
- nine passing process-supervisor tests and eight passing repository-manifest
  tests;
- 14 passing descriptor-anchored export tests;
- 10 passing release-orchestrator tests;
- 11 passing deterministic release-asset tests;
- four passing Zenodo metadata and file-verifier tests;
- one passing committed-paper binding test;
- 24 passing Julia compact-witness tests;
- 92 additional passing Julia construction, portable-recovery,
  strict-verification,
  dependency-integrity, and
  adversarial checks;
- passing C++20 GMP parser tests;
- a retained 560-byte exact pilot fixture with 16 blocks and dimension sum 28;
- complete exact Julia and Python verification of that pilot.
- retained dimension-11 numerical and fixed-objective logs, with fixed bundle
  SHA-256
  `ceed3e884625b2ff6365ea6c68eecdcdddd900d8aac0fa4d9955d8f1894f003a`;
- a 24,196,706-byte exact bundle with SHA-256
  `c772fc1608d68f2198a53e823047e37e60d496e74b1017b76bcb73a5a6398560`
  and verification-specification digest
  `a72606e8fc55123da96e7e76f577b48265b57a34f915f4033f3bc14a44aa2fe3`.
- compact manifest SHA-256
  `1a1f02f07f345129eb1541f30c38cedab2f141af429837d9dce6da41af6c6086`;
- compact witness SHA-256
  `bed94876a6275e7e680c682a0aeca8b8e65e6d55ba7b0b5f5833c5bd640e8229`;
- deterministic compressed-package size 14,565,324 bytes;
- release-mode verification time 907.16 seconds and maximum RSS
  187,596,800 bytes.

These records constitute the final dimension-11 certificate.

## Significance And Reuse

The project addresses the gap between a reported numerical objective and a
compact exact proof object. The result improves the rigorous integer upper
bound from 869 to 868.

The deterministic witness format, package binding, and coefficient verifier
can be reused for other spherical-code semidefinite bounds.

## Claim Boundary And Limitations

This package locally proves `tau_11 <= 868`, but does not determine `tau_11`,
improve the reported numerical optimum, or provide a new lower bound.

The certificate size, verification runtime, and peak-memory gates pass.
The manuscript builds and passes four-page visual inspection. Public candidate
hosted replay passes. External peer review and immutable publication binding
remain open. The final prior-art refresh passes.

## Provenance Boundary

Project-original code and documentation are MIT licensed.
`ClusteredLowRankSolver.jl` and its three-point example are MIT-licensed
third-party software by Nando Leijenhorst and contributors. The dependency is
pinned to commit `09ac81aed031bdea714832cf515244f6eb223531`.

## Review Status

Formula normalization, basis order, theorem correspondence, package identity,
resource controls, malformed-input handling, claim scope, and publication
language have undergone internal adversarial review. The paper
build and page layout also pass local inspection. External peer review and
formal proof-assistant verification have not occurred.

Public candidate run `34547450259` passed all 16 workflow steps from
2026-09-11T00:40:00Z through 2026-09-11T00:46:52Z. Artifact `10179696591`
contains the exact paper, verification log, and deterministic release files.

## Archive And Citation

Candidate `v0.1.0` has passed public hosted replay. The final release commit,
immutable tag, GitHub release, version DOI, and concept DOI remain pending.

The citation record and archive metadata are prepared. Zenodo creation and
publication occur only after the exact GitHub release assets are public and
verified.

## Remaining Acceptance Gate

Release requires:

1. numerical objective below `868.84` (passed);
2. a stable fixed-objective point at `86899/100` (passed);
3. exact rational feasibility for all 70 blocks (passed);
4. complete Julia and independent package verification (passed);
5. compressed certificate below 50 MB (passed);
6. verification below two hours and 16 GiB RAM (passed);
7. refreshed prior art (passed);
8. inspected paper (passed);
9. clean local replay and public candidate hosted replay (passed; run
   `34547450259`);
10. immutable public `v0.1.0` tag and GitHub release;
11. Zenodo draft replacement and duplicate verification from the exact GitHub
    asset set;
12. Zenodo publication and independent byte-for-byte download verification.
