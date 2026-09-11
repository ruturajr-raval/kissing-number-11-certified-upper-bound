# Claim Ledger

Status date: 2026-09-11

| Claim | Status | Evidence required |
| --- | --- | --- |
| The implementation matches the pinned published degree-17 code path | Checked | Formula review and low-degree construction tests |
| Canonical samples determine every declared symmetric degree-34 residual | Verified | Rank 1,461 modulo 65,521 and sample SHA-256 |
| Every generated residual belongs to the declared interpolation space | Verified | `evidence/residual-space.json` and independent formula audit |
| The reduced dual formulation implies a kissing-number upper bound | Verified | `docs/THEOREM_BRIDGE.md` and primary-source correspondence |
| The independent verifier reconstructs the exact formulas and verifies the compact pilot certificate | Verified | Independent Python tests and retained solver-produced 560-byte fixture |
| Julia and Python agree on nondegenerate formulation checks | Verified | `evidence/cross-language-formulation.json`; 35 scalar, 54 `F`, 6 interval-SOS, and 45 three-point-SOS checks |
| The package-manifest verifier checks every required source, evidence file, block rank, and witness byte | Verified | Adversarial manifest tests and independent descriptor recomputation on test packages |
| A final dimension-11 package manifest binds the accepted exact witness and all certificate trust anchors | Verified locally | Manifest SHA-256 `1a1f02f07f345129eb1541f30c38cedab2f141af429837d9dce6da41af6c6086`; release-mode replay |
| Explicit affine JSON can satisfy the 50 MB certificate gate | Refuted | `evidence/explicit-schema-audit.json`; the nonzero three-point `F` terms alone need at least 93,153,648 bytes |
| Julia, Python, and C++ agree on the deterministic compact rational upper-triangle writer output | Verified | Byte fixture and solver-produced low-degree witness |
| The numerical objective is below `868.84` | Verified | Retained 256-bit solve with status `pdOpt` and objective `868.8264995079022987424...` |
| A stable numerical fixed-objective point exists at `86899/100` | Verified | Accepted 384-bit recovery with objective error about `1.17e-68`, maximum sampled affine residual about `1.63e-71`, and minimum eigenvalue about `9.58e-15` |
| An exact feasible solution exists at `86899/100` | Verified by both implementations | Portable exact bundle SHA-256 `c772fc1608d68f2198a53e823047e37e60d496e74b1017b76bcb73a5a6398560`; compact witness SHA-256 `bed94876a6275e7e680c682a0aeca8b8e65e6d55ba7b0b5f5833c5bd640e8229` |
| The direct exact projection algorithm has reached zero rational linear-system slacks | Verified with a portable checkpoint | 2026-09-10 log and checkpoint SHA-256 `b39c3d218dd5d459018d6f112ef57e9ebe12d083751a594bd7a53bf8b6909826`; the first nonportable checkpoint remains rejected |
| The exact certificate proves `tau_11 <= 868` | Verified locally | Both verifiers pass and `docs/THEOREM_BRIDGE.md` derives the integer bound |
| The certificate is compact and commodity-verifiable | Verified locally | 14,565,324 compressed bytes; 907.16 seconds; 187,596,800 bytes maximum RSS |
| No equivalent public exact or outward-rounded dimension-11 certificate below 869 was located before release | Verified by dated public-artifact search | Final refresh completed 2026-09-10; `docs/PRIOR_ART.md` |

The theorem is verified. Public release and archive binding remain pending.
