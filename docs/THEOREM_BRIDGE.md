# Theorem Bridge

Status date: 2026-09-09

## Purpose

This note connects the implemented reduced three-point semidefinite program to
an upper bound for spherical codes. It does not assume that solver status is a
proof. The final theorem still requires an exact feasible solution and exact
verification.

## Reduced Three-Point Proposition

Let `P_k^n` be the degree-`k` Gegenbauer polynomial normalized by
`P_k^n(1) = 1`, and let

```text
Delta_s = {
  (u,v,t) in [-1,s]^3 :
  1 + 2uvt - u^2 - v^2 - t^2 >= 0
}.
```

For nonnegative scalars `a_0,...,a_r` and positive-semidefinite matrices
`F_0,...,F_d`, define

```text
G(u) = sum_{k=0}^r a_k P_k^n(u)
H(u,v,t) = sum_{k=0}^d <bar(Y)_k^n(u,v,t), F_k>.
```

Suppose

```text
G(u) + 3 H(u,u,1) <= -1                  for u in [-1,s],
H(u,v,t) <= 0                            for (u,v,t) in Delta_s.
```

Then

```text
A(n, arccos(s)) <=
1 + sum_{k=0}^r a_k + <J,F_0>,
```

where `J` is the all-ones matrix.

This is the reduced formulation used in Problem (8) and Lemma 2.4 of
Dostert, de Laat, and Moustrou. Leijenhorst and de Laat, Section 6.1, state
the same mixed-degree program used by this repository. It is a valid reduced
form of the Bachoc-Vallentin bound, not a literal transcription of
Bachoc-Vallentin Theorem 4.2, which includes an auxiliary `2 x 2` block.

## Proof

Let `C` be a spherical code and `N = |C| > 0`. Positive definiteness of the
three-point kernels gives

```text
T = sum_{x,y,z in C}
    H(x dot z, y dot z, x dot y) >= 0.
```

Partition the ordered triples by whether they contain three, two, or one
distinct code points. The all-distinct terms are nonpositive by the second
constraint, so

```text
T <= N H(1,1,1)
     + 3 sum_{x != y} H(x dot y, x dot y, 1).
```

The first constraint implies

```text
T <= N H(1,1,1) - N(N-1)
     - sum_{k=0}^r a_k
       sum_{x != y} P_k^n(x dot y).
```

Schoenberg positivity and `P_k^n(1) = 1` imply

```text
sum_{x != y} P_k^n(x dot y) >= -N.
```

Therefore

```text
0 <= T
   <= N (H(1,1,1) + sum_{k=0}^r a_k - (N-1))
   = N (M-N),
```

where

```text
M = 1 + sum_{k=0}^r a_k + <J,F_0>.
```

The final equality uses

```text
bar(Y)_0^n(1,1,1) = J,
bar(Y)_k^n(1,1,1) = 0 for k >= 1.
```

Hence `N <= M`.

## Implementation Correspondence

The project uses

```text
n = 11
s = 1/2
r = 34
d = 17.
```

`d2 = 17` creates `a_0,...,a_34`, and `d3 = 17` creates
`F_0,...,F_17`.

The univariate identity has the form

```text
1 + G(u) + 3 H(u,u,1)
+ sigma_0(u)
+ (u+1)(s-u) sigma_1(u)
= 0,
```

where both `sigma_i` are sums of squares. This proves the required
univariate inequality on `[-1,s]`.

The trivariate identity has the form

```text
H(u,v,t) + weighted invariant sums of squares = 0.
```

The five domain weights are nonnegative on `Delta_s`: the constant weight,
the first three elementary symmetric combinations of
`(u+1)(s-u)`, `(v+1)(s-v)`, and `(t+1)(s-t)`, and the Gram determinant
`1 + 2uvt - u^2 - v^2 - t^2`. This proves `H <= 0` on the required domain.

The univariate residual has degree at most 34 and is checked at 35 distinct
points. The trivariate residual is symmetric of degree at most 34. Its
symmetric polynomial space has basis

```text
(u+v+t)^a (uv+ut+vt)^j (uvt)^k,
a + 2j + 3k <= 34,
```

of dimension 1,461. The canonical `1461 x 1461` evaluation matrix has rank
1,461 modulo 65,521, so evaluation at the canonical samples is injective over
the rationals.

The fixed-objective constraint enforces

```text
sum_{k=0}^{34} a_k + <J,F_0>
= 86899/100 - 1.
```

Thus any exact feasible certificate has

```text
M = 86899/100 < 869.
```

Since the kissing number is the integer
`tau_11 = A(11, pi/3)`, exact feasibility implies

```text
tau_11 <= 868.
```

## Claim Boundary

The theorem bridge is complete. The repository does not yet contain the
dimension-11 exact feasible solution required to apply it. No claim
`tau_11 <= 868` is made until all 70 PSD blocks, all affine identities, the
objective, the compact certificate, and the independent verifier pass.

## Primary References

1. C. Bachoc and F. Vallentin, "New upper bounds for kissing numbers from
   semidefinite programming," JAMS 21 (2008), 909-924,
   https://doi.org/10.1090/S0894-0347-07-00589-9.
2. M. Dostert, D. de Laat, and P. Moustrou, "Exact Semidefinite Programming
   Bounds for Packing Problems," SIAM Journal on Optimization 31 (2021),
   1433-1458, https://doi.org/10.1137/20M1351692.
3. F. C. Machado and F. M. de Oliveira Filho, "Improving the Semidefinite
   Programming Bound for the Kissing Number by Exploiting Polynomial
   Symmetry," Experimental Mathematics 27 (2018), 362-369,
   https://doi.org/10.1080/10586458.2017.1286273.
4. N. Leijenhorst and D. de Laat, "Solving clustered low-rank semidefinite
   programs arising from polynomial optimization," Mathematical Programming
   Computation 16 (2024),
   https://doi.org/10.1007/s12532-024-00264-w.
