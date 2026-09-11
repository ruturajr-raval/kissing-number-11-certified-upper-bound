# Independent Compact Certificate Verifier

This directory contains the independent verifier for the published exact
certificate of

```text
tau_11 <= 868.
```

The public command-line interface is permanently pinned to:

```text
dimension = 11
degree = 17
cos(theta) = 1/2
objective = 86899/100
```

It does not import Julia, Nemo, `ClusteredLowRankSolver.jl`, a numerical
solver, or a serialized solver object.

## What It Checks

The Python verifier:

1. Parses the strict `KNWIT003` binary witness under fixed resource limits.
2. Requires the exact 70-block Project 10 layout.
3. Proves all release matrices strictly positive by 896-bit directed interval
   Cholesky.
4. Reconstructs the normalized Gegenbauer and Chebyshev bases independently.
5. Reconstructs the three-point kernels and all 15 weighted invariant SOS
   families independently.
6. Checks the objective exactly.
7. Checks all 35 univariate coefficients exactly.
8. Checks all 1,461 symmetric trivariate coefficients exactly.
9. Rejects malformed encodings, wrong dimensions, wrong targets, nonreduced
   rationals, failed positivity proofs, trailing bytes, and resource-limit
   violations.

`compact_witness.py` implements the strict binary parser.
`formulation.py` implements exact polynomial arithmetic.
`compact_certificate.py` performs coefficient replay.

The C++20 GMP parser in `cpp/` independently checks the witness encoding and
reconstructs exact matrices. The Julia implementation remains the primary
problem generator, exact rounder, and sampled-identity verifier.

## Run

After a final package exists, use the package verifier:

```bash
python3 verifier/verify_compact_package.py \
  certificates/kn11-degree17-certificate-v2.json \
  --release \
  --expected-manifest-sha256 PUBLISHED_MANIFEST_SHA256 \
  --expected-witness-sha256 PUBLISHED_WITNESS_SHA256 \
  --expected-source-specification PUBLISHED_SOURCE_SPECIFICATION \
  --expected-rounding-specification PUBLISHED_ROUNDING_SPECIFICATION \
  --expected-verification-specification PUBLISHED_VERIFICATION_SPECIFICATION
```

The witness-only command is a diagnostic:

```bash
python3 verifier/verify_compact_certificate.py \
  certificates/kn11-degree17-witness-v2.bin
```

No command-line option can change the mathematical target. Release mode
requires every published artifact and provenance trust anchor. The verifier
independently recomputes the fixed-objective and exact-rounding specification
digests, plus the exact-verification specification, from the bound source
files and reuses one authenticated witness byte snapshot throughout
verification.

## Test

```bash
python3 -m unittest discover -s verifier/tests -v
```

The solver-produced fixture
`tests/fixtures/smoke-exact-witness-v2.bin` is a 560-byte exact certificate
for the dimension-3, degree-2 pilot at objective 15. It exercises the generic
library end to end, including the bounded exact-PSD fallback for singular
small blocks. It is not a certificate for the dimension-11 theorem.

The real degree-17 witness passes this verifier under the published time and
memory limits. Clean hosted replay, immutable GitHub publication, and
independent Zenodo archive verification all pass.
