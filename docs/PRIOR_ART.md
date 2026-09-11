# Prior-Art Audit

Status date: 2026-09-10

## Exact Problem

Let `tau_11` denote the 11-dimensional kissing number. The target is a
rigorous certificate that

```text
tau_11 <= 868.
```

## Located Frontier

Machado and de Oliveira Filho's degree-16 verified computation gives
`869.244985`, hence the rigorous integer bound 869. Their paper and public
verification package state that the reported new bounds were rigorously
verified.

Leijenhorst and de Laat report these numerical values for dimension 11:

| Degree | Numerical bound |
| ---: | ---: |
| 16 | 869.23401 |
| 17 | 868.82650 |
| 18 | 868.45366 |
| 19 | 868.15131 |
| 20 | 868.01070 |

Their paper states that the table was not rigorously verified because its
purpose was to benchmark the solver. The 2025 dissertation repeats both the
values and the non-verification qualification. Later tables quote 868 as the
current integer upper bound and cite this computation, but the audit located
no separate public certificate.

## Located Certification Gap

The initial audit on 2026-09-09 and final prepublication refresh on
2026-09-10 searched papers, theses, public verification files, code
repositories, releases, data archives, citation indexes, and current
kissing-number tables for an exact rational or outward-rounded interval
certificate establishing a dimension-11 objective below 869. No such public
certificate was located.

This project therefore targets rigorous certification of a reported numerical
bound. It does not claim priority for the decimal value, the integer 868 in
published tables, exact SDP rounding, or interval verification methods.

The locally verified certificate at `868.99` establishes the integer result.
If the remaining publication gates pass, the defensible novelty statement is
limited to the first located public independently machine-checkable exact or
outward-rounded certificate for a dimension-11 three-point objective below
869. It does not certify the reported optimum `868.82650`.

## Pre-Release Refresh Result

The final public-artifact refresh was completed on 2026-09-10. It included:

1. Exact-phrase and variant searches for `tau_11 <= 868`, `868.82650`,
   `86899/100`, `868.99`, dimension-11 degree-17 three-point certificates,
   and exact or interval SDP verification.
2. GitHub code and repository searches for the same objective values and
   certificate descriptions. The only directly relevant upper-bound project
   located was this workbench. A separate repository for the exact lower
   bound `K(11) >= 604` is not an upper-bound certificate.
3. A current arXiv kissing-number scan through 2026-09-10. Located recent
   work concerned lower bounds, other dimensions, generalized variants, or
   exact SDP methods without a dimension-11 certificate.
4. The current `ClusteredLowRankSolver.jl` default branch, its
   `ThreePointBound.jl` example, and release `v2.2.0` published 2026-07-31.
   The pinned commit
   `09ac81aed031bdea714832cf515244f6eb223531` remains the current `main`
   commit. The release concerns solver fixes and interfaces, not a published
   exact dimension-11 certificate.
5. Citation trails for arXiv:2202.12077 and arXiv:2403.16874. Located citing
   works concerned solver methodology, exact SDP rounding, lower bounds, or
   other dimensions; none supplied an equivalent dimension-11 upper-bound
   certificate.
6. The Machado-de Oliveira Filho public verification directory and
   `README.txt`. The directory still provides the 2016 solution archives and
   Sage verifier for the bounds reported in their paper.
7. The January 16, 2026 MIT DSpace version of Cohn's kissing-number table.
   It lists the dimension-11 upper bound as 868 and attributes it to the
   numerical solver computation; it does not supply a new certificate.
8. Direct PDF text checks of the solver paper and exact-rounding paper. The
   solver paper contains the numerical value `868.82650` and its
   non-verification qualification. The exact-rounding paper contains no
   located occurrence of that value or a dimension-11 result.

The solver-paper PDF checked in this refresh had SHA-256
`e4aaa5337a2f7836010a53a975d9d91373b8e920b35487753f369428c806bedf`.
The exact-rounding-paper PDF had SHA-256
`3dd24b06606602a6df3c71a2734e670eaffa91b5de52a270af899c0733569141`.

No equivalent public exact rational or outward-rounded dimension-11
objective below 869 was located as of 2026-09-10. This is a dated
public-artifact search result, not a claim that unpublished or privately
circulated work does not exist. No author correspondence is used as evidence
for the claim.

## Primary Sources

1. Leijenhorst and de Laat, solver paper and dimension-11 numerical table:
   https://doi.org/10.1007/s12532-024-00264-w
2. Leijenhorst, 2025 dissertation:
   https://repository.tudelft.nl/record/uuid:91af805a-376c-4ef8-aec5-e6ce08ae20a7
3. Machado and de Oliveira Filho, verified bounds:
   https://arxiv.org/abs/1609.05167
4. Machado and de Oliveira Filho, public verification files:
   https://www.ime.usp.br/~fabcm/kissing-number/
5. Cohn, January 2026 kissing-number table, MIT DSpace record:
   https://hdl.handle.net/1721.1/168960
6. Cohn, de Laat, and Leijenhorst, exact SDP rounding:
   https://arxiv.org/abs/2403.16874
7. Current `ClusteredLowRankSolver.jl` repository and releases:
   https://github.com/nanleij/ClusteredLowRankSolver.jl
8. Located exact lower-bound repository, checked and excluded as
   non-equivalent:
   https://github.com/karlbaker75/kissing-number-k11-604-exact-certificate

## Refresh Checklist

Completed on 2026-09-10:

1. Exact phrases and objective variants searched.
2. Current solver repository, example, commit, and release notes checked.
3. Current kissing-number table and cited sources checked.
4. Citation trails and recent arXiv records checked.
5. GitHub repositories and code checked.
6. Public author-supplied verification files checked.
7. Audit date, queries, source URLs, and checked PDF hashes recorded.

If an equivalent public exact certificate appears, the novelty claim must be
withdrawn and the project must either become an independent reproduction or
select a different target.
