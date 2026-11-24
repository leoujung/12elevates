# DEPRECATION NOTICE — Business evaluator artifacts

**Status:** SUPERSEDED — NOT VALID FOR CURRENT BUSINESS MATCHING EVALUATION
**Date:** 24 November 2026
**Applies to:** Business items inside the engine-output evaluator files produced in commit `3fef253`.
**Superseded by:** commit `cdff4a7` (direct-ranking bypass closed; business evaluation refused by directive gate).

## Artifacts affected
| Repo path | Introduced in | Business items | SHA-256 (first 16) | Labels filled |
|---|---|---|---|---|
| `docs/ai/eval/engine_eval/evaluator_1_engine_eval.json` | `3fef253` | 125 | `dcdbe3c7ca863632` | 0 |
| `docs/ai/eval/engine_eval/evaluator_2_engine_eval.json` | `3fef253` | 125 | `476497f11bd5228c` | 0 |

## Why superseded
1. Those business items were produced by calling `rank_business` directly, with no consent, RBAC, field-policy, or synthetic-provenance check. That is the bypass closed in `cdff4a7`.
2. Business Matching is disabled by directive (`BUSINESS_MATCHING_ENABLED = False`). No business evaluation result from that process is a valid measure of the current business matching behaviour.
3. The files are not a valid basis for any Precision@5 claim for business.

## What this notice does NOT do
- It does not delete, overwrite, or regenerate the artifacts or their private key.
- It does not claim that previously distributed copies have been recalled or deleted. Those copies exist outside this repository and remain as they are.
- The customer items in the same files are not affected by this notice. They were produced by the same generator, but they are not covered here and are listed as a separate open question below.

## Open question
Whether the customer items in those two files should also be treated as superseded. They used `rank_customer` directly, without the guarded entry point. The guarded entry point was added after they were generated. Decision pending; not decided in this notice.

## Private keys
The private keys matching these files are outside the repo (`C:/Users/ASUS/AppData/Local/hermes/cache/scratch/private_keys/`). They are retained unchanged.
