# Test Fixture

`smoke-exact-witness-v2.bin` was emitted by the Julia exact-rounding pilot for
dimension 3, degree 2, maximum inner product `1/2`, and fixed objective 15.

Its properties are:

```text
bytes = 674
blocks = 16
rank sum = 10
stored rationals = 14
SHA-256 = 61a62110b2a51b26765c5a9449ea8baf752b4d2b19fed60b1689a15e9e1a8e96
```

Julia reconstructs every source matrix from the witness. The independent
Python verifier parses the same bytes and proves the exact objective,
univariate identity, trivariate identity, and PSD conditions.

This fixture validates the certificate machinery. It does not establish the
dimension-11 kissing-number bound.
