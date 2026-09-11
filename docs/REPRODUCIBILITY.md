# Reproducibility

## Environment

The workbench uses Julia 1.10 or later and a project-local package depot.
The lock file pins every dependency, including
`ClusteredLowRankSolver.jl` commit
`09ac81aed031bdea714832cf515244f6eb223531`.

Instantiate and test with:

```bash
make instantiate
make dependency-integrity
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

`make samples` regenerates `evidence/sample-unisolvence.json`. The expected
degree-17 result is rank `1461` modulo `65521` for a `1461 x 1461` matrix and
sample SHA-256
`9b8af0d4133749c485c9e36269d2f606a18427a3c17af7875665c5d293f97351`.

`make structure` regenerates `evidence/problem-structure.json`. The expected
fixed-objective layout has 3 constraints, 70 PSD blocks, 346,343
upper-triangular rational entries, and largest block order 378.

`make residual-space` regenerates `evidence/residual-space.json`. It verifies
the degree-34 bound and symmetry premise needed to combine sampled exact
equalities with the modular unisolvence certificate.

`make test-verifier` runs 56 standard-library Python tests. They cover the
complete 70-block target layout, strict witness parsing, exact polynomial
arithmetic, complete coefficient replay on the solver-produced pilot,
manifest and published-hash binding, independently recomputed provenance,
immutable-byte replay, malformed inputs, path safety, and resource limits.
The pilot is not a dimension-11 certificate.

`make test-supervisor` runs nine process-supervisor tests, eight
repository-manifest tests, 14 descriptor-anchored export tests, and 10
release-orchestrator tests. These reject incomplete process tables, surviving
child groups, symlink inputs, unsafe paths, unstable hash inputs, dirty
release trees, release-commit mismatches, Git redirection, loader injection,
mutable worktree bootstrapping, parent-directory symlinks, destructive cleanup
races, partial temporary files, redirected publication writes, and
manifest-install interruption.

`make schema-audit` regenerates `evidence/explicit-schema-audit.json`. It
measures the first explicit affine schema and rejects it before release: the
nonzero three-point `F` terms alone exceed 50 MiB under the schema's minimum
term encoding.

`make test-compact-witness` checks that Julia and Python produce and consume
the same deterministic upper-triangle writer output. `make test-cpp-witness`
adds the strict C++20 GMP parser. `make smoke-exact` additionally rounds the
degree-2 pilot, audits its exact matrix factors, writes a compact 16-block
witness, and replays every pilot coefficient independently.

`make cross-language` regenerates
`evidence/cross-language-formulation.json`. It uses nondegenerate rational
points and three deterministic columns per block to compare Julia and Python
on all 35 scalar kernels, all 18 degree-17 `F` blocks, both interval SOS
blocks, and all 15 three-point SOS families at degree 6.

## Full Numerical Reproduction

The target parameters are:

```text
dimension = 11
degree = 17
cos(theta) = 1/2
precision = 256 bits
```

Run:

```bash
JULIA_NUM_THREADS=12 make reproduce
```

Acceptance requires a successful solver status, zero solver error code, an
objective below `868.84`, bounded directly measured affine residuals, and no
materially negative matrix eigenvalue.

The retained 256-bit run completed with status `pdOpt`, zero solver error code,
and objective
`868.8264995079022987424151162145346662832468103455548564226535701359837263671181`.
Its transcript is `logs/degree17-numerical-2026-09-09.log`.

## Fixed-Objective Solve

The exact target objective is:

```text
86899/100
```

Run:

```bash
JULIA_NUM_THREADS=12 make fixed
```

The output is a temporary serialized high-precision primal-dual point. It is
written atomically only after every numerical gate passes. It includes a
digest binding the exact parameters, canonical samples, source files,
dependency manifest, solver revision, and entry-point script. It is not a
proof object.

The accepted recovery bundle is
`build/degree17-fixed-86899-over-100.jls`, with SHA-256
`ceed3e884625b2ff6365ea6c68eecdcdddd900d8aac0fa4d9955d8f1894f003a`.
Its objective error is about `1.17e-68`, maximum sampled affine residual about
`1.63e-71`, and minimum matrix eigenvalue about `9.58e-15`. The retained
transcript is `logs/degree17-fixed-resume.log`.

## Exact Rounding

Run:

```bash
JULIA_NUM_THREADS=12 make round
```

The rounding script rejects stale or mismatched inputs and reconstructs the
canonical fixed-objective problem. It converts every Nemo rational to a
process-portable `Rational{BigInt}` upper-triangle payload and writes the
expensive rational affine projection atomically to
`build/degree17-projected-86899-over-100.jls` before full verification. A
restart accepts that checkpoint only when its numerical-input hash, source
specification, rounding specification, and exact-projection gate all match.
The portable representation is required because generic Julia serialization
of Nemo `QQFieldElem` values preserves process-local FLINT handles rather than
their mathematical values.

Primary verification checks exact scalar types, expected block keys and
sizes, the original objective, and every affine residual sample by sample,
without constructing 1,461-entry sampled-polynomial temporaries during each
matrix operation. Affine replay runs in sequential 100-sample worker
processes, each with two Julia threads, so process exit releases retained
FLINT allocator pages before the next range. Each exact rational matrix is
then embedded into Arb balls; a successful interval Cholesky
factorization rigorously proves strict positive definiteness, which is
stronger than the required positive-semidefinite gate. The standard target
allows four hours and 24 GiB for projection plus primary verification.

The accepted 2026-09-10 primary-verification output is
`build/degree17-exact-86899-over-100.jls`, with 24,196,706 bytes and SHA-256
`c772fc1608d68f2198a53e823047e37e60d496e74b1017b76bcb73a5a6398560`.
Its verification-specification digest is
`a72606e8fc55123da96e7e76f577b48265b57a34f915f4033f3bc14a44aa2fe3`.
The stored record covers 1,497 exact affine residuals, 17 isolated worker
processes, and 70 strict-positive matrix blocks. A separate Julia process
scanned all 346,343 `Rational{BigInt}` coefficients and restored all 70
matrices as fresh Nemo rationals.

The deterministic compact certificate passes the independently implemented
package and coefficient verifier in `verifier/`. The release-mode replay binds
the real exact certificate to the manifest, witness, source-specification,
rounding-specification, and verification-specification hashes.

The release format uses a small JSON manifest plus a binary witness of exact
rational symmetric upper triangles. The dense explicit affine JSON
implementation was
removed after its size rejection; the audit evidence is retained.

Run `make export-certificate` only after exact rounding succeeds. The Python
wrapper copies every bound source, evidence file, and exact input through
no-follow descriptors into an isolated snapshot containing read-only copies. A
shell-free launcher enters the snapshot with `fchdir`; Julia startup files and
compiled-module caches are disabled. The bootstrap verifies 27 dependency
source trees and 3 selected artifact trees in the pinned environment before
and after project execution, with artifact overrides forbidden. Before
starting the export, set `KN11_EXPECTED_JULIA_SHA256` and
`KN11_EXPECTED_JULIA_TREE_SHA256` to the published Julia 1.12.7 executable and
runtime-tree hashes, and set `KN11_EXPECTED_EXACT_INPUT_SHA256` to the external
digest recorded immediately after accepted exact rounding. The exporter
checks that input before Julia deserializes it and executes an isolated copy of
the verified Julia executable. The independent package verifier then replays
immutable copies of the exact captured certificate bytes. Only after that
replay passes does an exclusive publication lock permit those same bytes to be
installed through atomic no-follow directory-descriptor replacements, with
the authenticating manifest installed last. The complete export runs under
the four-hour and 16 GiB producer supervisor. The standalone independent
verification acceptance gate remains two hours and 16 GiB.

The accepted compact package contains:

```text
manifest_sha256 = 1a1f02f07f345129eb1541f30c38cedab2f141af429837d9dce6da41af6c6086
witness_sha256 = bed94876a6275e7e680c682a0aeca8b8e65e6d55ba7b0b5f5833c5bd640e8229
witness_bytes = 14850075
compressed_package_bytes = 14565324
rational_count = 346343
block_dimension_sum = 3198
```

Both export-time captured-byte replay and a second installed-file
release-mode replay verify all 70 blocks, 35 univariate coefficients, and
1,461 symmetric trivariate coefficients. The standalone replay took 907.16
seconds and used 187,596,800 bytes maximum RSS, with zero exact PSD fallbacks.

The current local macOS Julia 1.12.7 candidate anchors are:

```text
executable_sha256 = 81f22191668e32ddc48010024e33dbcc4e17d5e39e332f81959b179e430fa94f
runtime_tree_sha256 = b47999dfded86578d8edae980ae168a7367073729fd6e71fe615848fd4064bb8
```

They are installation-specific and must be recomputed and published for the
runtime used by the final release.

The accepted real-input export completed both dependency audits for 27 package
trees and 3 selected artifact trees. The post-export audit, in-snapshot
captured-byte replay, atomic installation, and installed-file release-mode
replay all pass.

The authoritative release gate must not start from `make`, a worktree script,
or a user-shell startup file. The `make release-check` target refuses by
design. Begin with an independently retained and audited copy of this minimal
bootstrap, replacing all ten positional placeholders with literal values:

```bash
/usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C \
/bin/zsh -f -c '
  set -eu
  set -o pipefail
  [[ $# -eq 10 ]] || exit 2
  root=$1
  julia=$2
  commit=$3
  julia_sha=$4
  julia_tree_sha=$5
  manifest_sha=$6
  witness_sha=$7
  source_sha=$8
  rounding_sha=$9
  verification_sha=${10}
  [[ ${#commit} -eq 40 && $commit != *[^0-9a-f]* ]] || exit 2
  for digest in \
    $julia_sha $julia_tree_sha $manifest_sha $witness_sha \
    $source_sha $rounding_sha $verification_sha
  do
    [[ ${#digest} -eq 64 && $digest != *[^0-9a-f]* ]] || exit 2
  done
  /usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
    GIT_NO_REPLACE_OBJECTS=1 \
    /usr/bin/git -C "$root" \
      -c core.fsmonitor=false \
      -c core.untrackedCache=false \
      -c core.useReplaceRefs=false \
      show "${commit}:tools/release_check.py" |
  /usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C \
    JULIA="$julia" \
    KN11_EXPECTED_RELEASE_COMMIT="$commit" \
    KN11_EXPECTED_JULIA_SHA256="$julia_sha" \
    KN11_EXPECTED_JULIA_TREE_SHA256="$julia_tree_sha" \
    KN11_EXPECTED_MANIFEST_SHA256="$manifest_sha" \
    KN11_EXPECTED_WITNESS_SHA256="$witness_sha" \
    KN11_EXPECTED_SOURCE_SPECIFICATION="$source_sha" \
    KN11_EXPECTED_ROUNDING_SPECIFICATION="$rounding_sha" \
    KN11_EXPECTED_VERIFICATION_SPECIFICATION="$verification_sha" \
    /usr/bin/python3 -I -E -s - --repository-root "$root"
' kn11-release \
  /absolute/path/to/repository \
  /absolute/path/to/julia \
  RELEASE_COMMIT \
  JULIA_EXECUTABLE_SHA256 \
  JULIA_RUNTIME_TREE_SHA256 \
  CERTIFICATE_MANIFEST_SHA256 \
  CERTIFICATE_WITNESS_SHA256 \
  SOURCE_SPECIFICATION_SHA256 \
  ROUNDING_SPECIFICATION_SHA256 \
  VERIFICATION_SPECIFICATION_SHA256
```

The first `/usr/bin/env -i` removes the caller environment before `zsh -f`
starts, so neither repository files nor `.zshenv` can alter the commit or
anchors. The bootstrap validates every anchor, loads the isolated Python
orchestrator from the expected commit, and supplies the eight release anchors
through a second empty environment. That orchestrator loads the repository
manifest verifier from the same commit, validates the clean-commit anchor,
the Julia executable and runtime-tree anchors, and all five certificate
anchors. It disables Git replacement refs, derives
`release-manifest.sha256` from the named commit tree, independently compares
the working files with that tree, executes an isolated copy of the pinned Julia
1.12.7 binary, reruns every repository check as an argument array, requires
real-package replay, rehashes both certificate files, and confirms the same
clean commit afterward. The exact-input hash is a separate export-stage
anchor.

## Hosted Portable Replay

`.github/workflows/ci.yml` runs the portable release replay on an Ubuntu
24.04 clean checkout. It verifies the named commit against
`release-manifest.sha256`, runs the independent Python and C++ test suites,
then invokes the isolated `--certificate-only` release checker with all five
certificate anchors. That replay verifies every exact coefficient and all 70
strict-positive matrix blocks under the two-hour and 16 GiB limits, rehashes
both certificate files afterward, and rebuilds the candidate manuscript with
the hash-pinned Tectonic 0.17.0 Linux binary.

The hosted job intentionally does not claim the platform-specific Julia
runtime anchor. The authoritative full local gate separately binds the named
commit to the recorded Julia 1.12.7 executable and complete runtime-tree
hashes. Together, these checks distinguish portable independent certificate
replay from the stronger same-runtime reconstruction gate.

## Resource Envelope

- Numerical solve: at most 24 hours and 48 GiB RAM.
- Exact rounding and primary verification: at most six hours and 24 GiB RAM.
- Compressed final certificate: below 50 MB.
- Either final verifier: below two hours and 16 GiB RAM.
- GPU: not used.

The accepted compact package is 14,565,324 bytes after deterministic
compression. Independent release-mode replay takes 907.16 seconds and
187,596,800 bytes maximum RSS.

The standard `make` targets enforce these process-tree limits under explicit
allowlisted environments. Individual accepted file replacements are atomic,
and a certificate package is accepted only after manifest-bound replay. The
long solves write source-bound restart checkpoints every 30 minutes by
default. Exceeding a limit triggers redesign rather than an unsupported
release claim. The local release controls assume that no concurrently
malicious process is running under the same user identity with write access to
the repository, dependency depot, or Julia installation.
