# Laporan Implementasi — 12ELEVATE AI Network Building Intelligence

**Dasar:** Persetujuan pekerjaan teknis (dua item) dan arahan Directive 002, Addendum 003, dan Adopsi 12E-DIR-ADP-001.
**Prinsip proyek:** *Development Must Continue, Compliance Must Be Enforced, and Production Activation Must Be Authorized.*
**Tanggal:** 24 November 2026
**Commit:** `20a62f2` (branch `ai/matching-prototype`)
**Sifat:** laporan teknis dan status internal. Bukan opini hukum, bukan persetujuan pemrosesan data nyata.

---

## 1. Integrasi field_policy pada setiap matching service

| Jalur | Pemeriksaan field | Urutan | Bukti |
|---|---|---|---|
| Customer Matching (`customer_matches`) | Ya, sebelum consent dan ranking | 1 otorisasi → 1b field → 2 consent → 3 ranking → audit | `matching_service.py`, tes 23/23 |
| Business Matching (`business_matches`) | Ya, sebelum gate direktif | field → gate direktif (selalu menolak selama flag OFF) → audit | `matching_service.py`, tes business |

**Catatan:** pemeriksaan field pada jalur business tetap berjalan saat flag OFF. Dengan begitu, aktivasi di masa depan tidak bisa melewati pemeriksaan ini.

---

## 2. Data Classification Matrix

| Field | Kelas | Status | Boleh dipakai untuk |
|---|---|---|---|
| declared_wellness_interest | GENERAL_WELLNESS | PENDING_REVIEW (O4) | Customer (setelah review) |
| education_preference | GENERAL_WELLNESS | PENDING_REVIEW | Customer (setelah review) |
| product_category_interest | GENERAL_WELLNESS | PENDING_REVIEW | Customer (setelah review) |
| declared_needs_goals | GENERAL_WELLNESS | PENDING_REVIEW (O5) | Customer; berisiko free-text |
| engagement_relevance | GENERAL_WELLNESS | PENDING_REVIEW | Customer (setelah review) |
| declared_entrepreneurship_interest | BUSINESS_INTEREST | PENDING_REVIEW | Business (setelah preconditions) |
| business_goals_alignment | BUSINESS_INTEREST | PENDING_REVIEW | Business |
| digital_business_interest | BUSINESS_INTEREST | PENDING_REVIEW | Business |
| leadership_development_interest | BUSINESS_INTEREST | PENDING_REVIEW | Business |
| relevant_experience_declared | BUSINESS_INTEREST | PENDING_REVIEW | Business; hanya pernyataan sukarela |
| medical_diagnosis, declared_condition, medication, medical_history, health_indicator, assessment_medical_answers | HEALTH_CONDITION | EXCLUDED | Tidak untuk matching umum |
| marketing_opt_in | MARKETING | PENDING_REVIEW | Tujuan terpisah, bukan matching |
| Field tidak terdaftar | UNCLASSIFIED | DITOLAK (fail closed) | Tidak ada |

**Tidak ada field yang berstatus APPROVED.** Tes memastikan ini.

---

## 3. Data Processing Purpose dan Lawful Basis Matrix

| Tujuan | Dasar hukum | Status | Blocker |
|---|---|---|---|
| matching_customer | **Belum ditetapkan** | BELUM | O1 (keputusan Pengendali Data, dibantu analisis Legal) |
| matching_business | **Belum ditetapkan** | BELUM | O1 |
| marketing | **Belum ditetapkan** | BELUM | O1; terpisah dari matching |
| Consent (jika dipilih sebagai dasar) | Notice APPROVED diperlukan | BELUM | O2 |

Catatan: sesuai persetujuan, dasar hukum adalah keputusan Pengendali Data Pribadi. Hermes tidak menetapkannya. Sistem mendukung pencatatan dasar per tujuan. Jika consent yang dipilih, pencatatannya memakai ledger yang sudah ada.

---

## 4. Daftar Fitur

**Boleh berjalan sekarang (dengan data sintetis atau internal testing):**
- Pengembangan dan pengujian Customer Matching dan Business Matching.
- Consent ledger, RBAC, audit trail (sintetis).
- Field policy pada kedua jalur.
- Labelling dan evaluasi dengan data sintetis.
- Penyusunan dokumen legal dan compliance.

**Dibatasi (boleh dikembangkan, tidak boleh untuk data nyata):**
- Customer Matching: hanya setelah klasifikasi field diverifikasi (O4) dan dasar hukum ditetapkan (O1).
- Business Matching: `BUSINESS_MATCHING_ENABLED` tetap OFF.
- Consent notice: hanya draf DRAFT; GRANTED ditolak oleh ledger dan oleh trigger DB (proposal).

**Belum boleh diaktifkan:**
- Pemrosesan data pribadi nyata untuk matching apa pun.
- Business Matching untuk data nyata (flag).
- Outreach otomatis, marketing, external prospect discovery dengan data pribadi.
- Pemrosesan kategori data spesifik (kesehatan) untuk profiling bisnis.
- Penerapan skema DB ke staging (menunggu persetujuan eksplisit).

---

## 5. DPIA Status dan Outstanding Findings

| Item | Status |
|---|---|
| DPIA dimulai | Belum. Paralel dengan pengembangan (Addendum 003 V). |
| Kriteria risiko tinggi | Belum dinilai. Matching, profiling, scoring, dan AI baru termasuk yang perlu dinilai. |
| Data flow mapping | Belum dibuat. |
| Finding yang sudah diketahui | (1) O9: belum diverifikasi apakah jawaban assessment medis masuk ke sumber matching. (2) `declared_needs_goals` free-text berisiko memuat konten medis. (3) Retensi belum diputuskan dan berbenturan dengan hak penghapusan. (4) Autentikasi API belum ada. (5) Rantai hash dihitung aplikasi, belum database. |

DPIA harus selesai sebelum pemrosesan berisiko tinggi aktif di produksi. Tidak menghentikan pengembangan.

---

## 6. Hasil uji bypass

**Tes yang dijalankan (semua lulus):**
- Customer dan business: field kesehatan menolak seluruh permintaan.
- Penolakan dicatat di audit dengan nama field, tanpa nilai.
- Field tidak terklasifikasi ditolak.
- Business diblokir oleh gate direktif walaupun field sah.
- Lintas tenant ditolak; platform admin tidak punya akses data member.
- Tanpa consent GRANTED dengan notice APPROVED, prospek tidak diranking.
- Ranking tidak mungkin dipanggil lewat jalur layanan tanpa lolos semua pemeriksaan.

**Mutan (setiap pemeriksaan dihapus satu per satu, tes harus gagal):**
- Gerbang consent dilewati → 5 tes gagal.
- Pemeriksaan field pada customer dihapus → 3 tes gagal.
- Pemeriksaan field pada business dihapus → 1 tes gagal.
- Pemeriksaan lintas tenant dihapus → 5 tes gagal.
- Pengecekan DRAFT di ledger dihapus → 2 tes gagal.
- Pengecekan kelas kesehatan dan field policy dimatikan → 8 tes gagal.

**Temuan bypass yang belum tertutup:**
- `backend/ai/eval/build_engine_eval.py` memanggil `rank` langsung, tanpa jalur layanan. Saat ini hanya memakai data sintetis. Perlu dibatasi (tandai sebagai hanya-sintetis, atau pindah ke jalur layanan) sebelum ada data nyata di sekitarnya.
- Fungsi `rank` dan `score` di modul matching tidak memeriksa field atau consent sendiri. Keamanannya bergantung pada jalur layanan sebagai satu-satunya pemanggil di luar tes.
- `ai/rbac.py` dan `ai/consent.py` masing-masing menyimpan konstanta flag. Tidak ada mekanisme yang memastikan keduanya sama. Perlu satu sumber kebenaran.

---

## 7. Yang belum saya klaim

- Belum ada autentikasi nyata.
- Belum ada penyimpanan di PostgreSQL staging.
- Belum ada pengujian pada data nyata atau staging.
- Belum ada keputusan retensi atau penghapusan.
- Tes adalah pengujian logika pada data sintetis, bukan audit keamanan eksternal.

---

## Update: Option 1 — Environment Variable Activation Removed

**Decision reference:** "Pilih opsi 1 — Remove Environment Variable Activation".
**Commit:** `9786427587a7` (branch `ai/matching-prototype`, pushed to origin; remote and local hashes match).
**Final status:** `BUSINESS_MATCHING_ENABLED = False`. Business Matching is not enabled. Real personal data is not processed.
**Production:** no activation authorized by this update. No production server was changed.

### Files changed (commit 9786427)
- `backend/ai/config.py`: single permanent source of the flag. The environment read was removed.
- `backend/ai/consent.py`: now imports the flag from `config.py`. Its own copy was removed.
- `backend/ai/rbac.py`: now imports the flag from `config.py`. Its own copy was removed.
- `backend/tests/test_config_flag.py`: new, 14 dedicated tests.

### Single-source configuration architecture
- Exactly one assignment exists in the repo: `backend/ai/config.py`, `BUSINESS_MATCHING_ENABLED: bool = False`.
- `consent.py` and `rbac.py` read that object. Checked by a test that scans every `ai/*.py` module for another assignment. The scan found none.
- No environment variable, runtime override, or fallback can change the value.

### Fail-closed behavior
- The flag is a constant, so there is no configuration that can fail to load and turn it on.
- The default and the only value is `False`.
- Activation requires a code change with: a written Data Controller decision, review, audit trail, automated tests, lawful basis, Privacy Notice, data classification, and DPIA. These are stated in the module docstring.

### Test results
- Dedicated configuration tests: **14 passed, 0 failed** (`test_config_flag.py`).
  - Environment values `true`, `True`, `1`, `yes`, `on`, empty string, and `x` each leave the flag `False`.
  - `BUSINESS_MATCHING_ENABLED=true` in the environment leaves it `False`.
  - No environment: `False`.
  - No other module assigns the flag.
  - `consent` and `rbac` read the same object.
  - Business matching is refused with no candidates.
- Full repository suite: **10 suites, 161 tests, all passed** (customer 15, business 15, data_collection 15, evaluation 8, labelling 20, consent 19, rbac 16, matching_service 23, field_policy 17, config_flag 14).

### Mutation test evidence
- Environment read re-introduced into `config.py` (`os.environ.get(...) == "true"`): `test_config_flag` **1 failed**. Restored: 14/14.
- Earlier mutants from previous steps, still in the suite: consent gate bypassed (5 failed), field policy removed from customer path (3 failed), field policy removed from business path (1 failed), cross-tenant check removed (5 failed), DRAFT check disabled (2 failed), health-class check removed plus class check disabled (8 failed).

### Confirmation: environment variable activation removed from repository code
- `git grep AI_BUSINESS_MATCHING_ENABLED` on the tip of `ai/matching-prototype` returns **only** `backend/tests/test_config_flag.py`. That file uses the name to prove the variable has no effect. No code reads it.
- The same holds on `origin/ai/matching-prototype`.
- Other branches (`main`, `docs/ai-network-intelligence-plan`, `gold-pool-phase3`, `production-baseline-2026-11-23`) do not contain the string. Their state was not separately audited beyond this search.

### Deployment configuration audit (repository level, read-only)
Method: `git ls-files` and `git grep` on the tip of `ai/matching-prototype`.

| Item | Found | Reference to env flag | Note |
|---|---|---|---|
| `infra/Dockerfile` | Yes | No | Does not copy `backend/ai`. The AI modules are not part of this image. |
| `infra/docker-compose.yml` | Yes | No | Loads `env_file: .env`. The tracked repo has no `.env`, so its contents are unknown here. |
| `infra/requirements.txt` | Yes | No | No AI-specific packages. |
| CI/CD workflows (`.github/`) | None tracked | No | No CI in this repo. |
| Tracked `.env` or env templates | None | No | |
| README / deployment docs | Docs only in `docs/` | No active instruction to use the variable | |
| systemd unit files | None tracked | — | Not in repo. |

Conclusion: no deployment file in the repo references `AI_BUSINESS_MATCHING_ENABLED`.

### Outstanding deployment verification items (server-level, NOT verified)
These require access to the VPS, which was **not reachable** from this session (`srv1964287` does not resolve, and no SSH alias exists on this PC). Nothing below has been checked.
1. Whether the production or staging `.env` file used by `docker-compose.yml` sets `AI_BUSINESS_MATCHING_ENABLED`. The file is intentionally not read. Check with the server owner or by a key-only grep that does not print values.
2. Whether any systemd unit, shell profile, or Docker environment on the VPS sets the variable.
3. Whether any deployment documentation outside this repo (for example, the VPS runbook or n8n settings) instructs its use.
4. Whether the running container image was built from a commit that predates `9786427`. The image in use is `elevate-api:academy-mitra3-422eb9a`, which does not contain `backend/ai` at all.

Note on item 4: the currently deployed API image does not include the AI modules, so the environment variable has no effect on production today. The risk is for any future image that includes `backend/ai`.

### Remaining scope (unchanged)
- Legal basis per purpose (O1), approved notice (O2), DPIA (O3), review of `declared_wellness_interest` (O4), decision on `declared_needs_goals` (O5), retention (O6), deletion (O7), provenance (O8), assessment medical-data verification (O9), DB role grants (O10), API authentication (O11), staging schema apply (O12, awaiting approval), member transparency (O13).
- The `build_engine_eval.py` direct-rank call and the unclosed bypass findings from the previous report are still open.
---

## Implementation update 2 — Closure of direct-ranking bypass (commit cdff4a7)

**Date:** 24 November 2026
**Commit reference:** `cdff4a7ab5d6` (branch `ai/matching-prototype`).
**Decision basis:** technical closure approval for the direct `rank()` call in `build_engine_eval.py`, subject to the documentation requirements recorded here.
**Status:** `BUSINESS_MATCHING_ENABLED = False`. Business Matching is not activated. Real personal data is not processed. No production change.

### 1. What was implemented
- **New `backend/ai/synthetic_guard.py`.** Provenance guard for synthetic evaluation data. A candidate passes only if its id was registered by the synthetic generator in the current process, its id and member match the synthetic patterns, `synthetic=True`, it is not declared from `job_title`, its dimensions are allowed for the engine, and its values are in [0, 1].
- **New `synthetic_eval_rank` in `backend/ai/matching_service.py`.** The only entry point evaluation code may use to rank. Order: RBAC (`run_on_synthetic`, developer role only), synthetic guard, field policy, ranking, audit. Business engine requests are refused and audited.
- **Changed `backend/ai/eval/build_engine_eval.py`.** It no longer calls `rank_customer` or `rank_business` directly. It registers generated ids, then ranks through `synthetic_eval_rank`. Business is skipped and produces no items.
- **New `backend/tests/test_synthetic_guard.py`.** 22 dedicated tests.

### 2. Test evidence
- **11 suites, 183 tests, all passed.**
  - customer 15, business 15, data_collection 15, evaluation 8, labelling 20, consent 19, rbac 16, matching_service 23, field_policy 17, config_flag 14, synthetic_guard 22.
- The 22 dedicated synthetic guard tests cover:
  - positive control (valid synthetic input ranks);
  - non-synthetic flag refused;
  - real-looking id refused;
  - synthetic-looking id not registered by the generator refused;
  - the generator cannot register a non-synthetic id;
  - non-synthetic member id refused;
  - cross-member candidate refused;
  - `job_title` experience refused;
  - unknown dimension refused;
  - health dimension refused;
  - out-of-range and negative values refused;
  - member and platform_admin roles refused;
  - business and unknown engines refused;
  - refused and allowed runs audited, chain verifies, no profile values in audit;
  - source check: the evaluation script does not call `rank()` directly and uses `synthetic_eval_rank`.

### 3. Mutation testing
Each mutant was applied to the working copy, the tests were run, and the file was restored. The restored state passed 22/22.
- **Provenance registry check removed** in `synthetic_guard.py`: **1 test failed**.
- **Synthetic flag check removed** in `synthetic_guard.py`: the run failed, caught by the existing `customer_matching` guard (`RefusedInput`), not by a dedicated test in this suite. Recorded as such.
- **`build_engine_eval.py` reverted to a direct `rank()` call:** **1 test failed**.
- Earlier mutants from previous reports remain in force (consent gate, field policy on both paths, cross-tenant, DRAFT check, config flag env read).

Honest note on the second mutant: that check is not independently covered by a test in the new suite. It should get a dedicated test in a later change.

### 4. Synthetic-only limitation (required statement)
Provenance registration is **process-memory based**.
- It is a **safeguard against accidental use of real data** in the evaluation path.
- It is **not a security guarantee**. It does not protect against intentional modification of the source code or a malicious developer. Such a person could edit the generator, the guard, or the tests.
- The residual risk is governed by code review, branch protection, and the RBAC developer role. None of these is enforced by this module.
- It must not be described as an absolute guarantee.

### 5. Consent boundary (required statement)
- The consent ledger check is **bypassed only for verified synthetic evaluation data**. The bypass is in `synthetic_eval_rank`, and it applies only when the synthetic guard passes.
- The exception **must never apply** to real member data, personal data, or production matching.
- Production and real-person matching continue to use `customer_matches`, which keeps the consent check. Business matching remains refused.
- Because the bypass sits behind the guard, a non-synthetic candidate cannot reach it through the guarded entry point. That property is covered by tests, subject to the limitation in section 4.

### 6. Business evaluation artifacts
- **Not deleted, overwritten, or regenerated.** The committed artifacts `docs/ai/eval/engine_eval/evaluator_1_engine_eval.json` (sha256 prefix `dcdbe3c7ca863632`) and `evaluator_2_engine_eval.json` (sha256 prefix `476497f11bd5228c`) are unchanged. Each still contains 125 business items and 0 filled labels. Private keys are unchanged.
- A separate notice was created: `docs/ai/eval/engine_eval/DEPRECATION_NOTICE_BUSINESS_ITEMS.md`. Status: **SUPERSEDED — NOT VALID FOR CURRENT BUSINESS MATCHING EVALUATION.**
- The notice records the reason: the items were generated without the guarded path. It does **not** claim that previously distributed copies have been recalled or deleted. Those copies exist outside this repository.
- Open question: whether the 125 customer items in the same files should also be superseded. They were generated with `rank_customer` directly, before the guarded entry point existed. Not decided.

### 7. Evaluation integrity
- A **dry-run** was performed: the build logic was executed in memory, and nothing was written to disk.
- Result: **125 Customer items, 0 Business items.**
- A **full regeneration was intentionally not performed**, to protect the existing evaluator artifacts and private keys. Regenerating would overwrite files already distributed to evaluators and would make them inconsistent with their keys.
- The committed artifacts were therefore not produced by the new code path. The dry-run shows what the current code would produce, not what is in the repository.

### 8. Changed files
- `backend/ai/synthetic_guard.py` (new), commit `cdff4a7`
- `backend/ai/matching_service.py` (added `synthetic_eval_rank`), commit `cdff4a7`
- `backend/ai/eval/build_engine_eval.py` (direct `rank()` removed), commit `cdff4a7`
- `backend/tests/test_synthetic_guard.py` (new, 22 tests), commit `cdff4a7`
- `docs/ai/eval/engine_eval/DEPRECATION_NOTICE_BUSINESS_ITEMS.md` (new), this report commit
- `docs/ai/legal/IMPLEMENTATION_REPORT_20261124.md` (this update), this report commit

### 9. Limitations
- The provenance registry is process-memory only (section 4).
- The synthetic-flag mutant is covered only by a lower layer, not by a dedicated test (section 3).
- The evaluation path bypasses consent for synthetic data only. This is intentional, and it is limited by the guard.
- The committed engine-eval artifacts were not regenerated, so they still contain the superseded business items.
- The customer items in those artifacts were generated without the guarded entry point. Their status is undecided.

### 10. Outstanding risks
- **R1. Superseded artifacts remain in circulation.** Copies distributed outside the repo cannot be recalled by this report.
- **R2. Process-memory registry** can be bypassed by source modification. Mitigation is review and branch protection, not yet enforced.
- **R3. Customer evaluation artifacts** are of undecided validity.
- **R4. Server-level deployment verification is NOT VERIFIED.** The VPS (`srv1964287`) was not reachable from this session. The four items from the previous report remain open. The repo-level finding does not extend to other environments.
- **R5. Legal items O1–O13** remain open, per their individual status. Technical implementation passing tests does not close any of them.
- **R6. Business Matching activation** requires the governance path in the decision record (written Data Controller decision, review, audit, tests, lawful basis, Privacy Notice, data classification, DPIA). None of those is complete.

### 11. Final status
`BUSINESS_MATCHING_ENABLED = False`. Business Matching is not enabled. No real personal data is processed. No production activation is authorized by this update.
---

## Implementation update 3 — Customer evaluator items superseded (methodology)

**Date:** 24 November 2026
**Decision:** the 125 legacy Customer items in the engine-output evaluator files are marked as superseded for current official evaluation purposes.
**Notice:** `docs/ai/eval/engine_eval/DEPRECATION_NOTICE_CUSTOMER_ITEMS.md`
**Status label:** SUPERSEDED — NOT VALID FOR CURRENT OFFICIAL CUSTOMER MATCHING EVALUATION

### Reason
The Customer items were generated by calling `rank_customer` directly, before the synthetic evaluation guard (`synthetic_guard.py`) and the controlled entry point (`synthetic_eval_rank`) existed. They therefore lack the current control chain: RBAC role check, synthetic provenance check, field-policy check, and audit entry.

### What this decision means and does not mean
- **It concerns evaluation methodology and control consistency.**
- **It does not establish that the historical results were incorrect.** It also does not establish that they were correct.
- **It does not claim that copies already distributed have been recalled or deleted.**

### Actions taken
- Created `DEPRECATION_NOTICE_CUSTOMER_ITEMS.md`.
- Did not delete, overwrite, or regenerate the evaluator artifacts.
- Did not modify or regenerate private keys.
- Did not change any artifact hash or historical record.

### Artifact status (verified before this update)
| Artifact | Commit introduced | SHA-256 (first 16) | Customer items | Business items | Labels filled | Status |
|---|---|---|---|---|---|---|
| `evaluator_1_engine_eval.json` | `3fef253` | `dcdbe3c7ca863632` | 125 | 125 | 0 | SUPERSEDED (Customer and Business) |
| `evaluator_2_engine_eval.json` | `3fef253` | `476497f11bd5228c` | 125 | 125 | 0 | SUPERSEDED (Customer and Business) |

Both files were confirmed unchanged since `3fef253` at the time of this update.

### Current approved path
- The synthetic evaluation path (`synthetic_eval_rank`, commit `cdff4a7`) is the **only approved path for new official evaluation runs**.
- New runs must use a new artifact set, generated under the current methodology with a new key. No existing artifact may be reused for official evaluation.

### Limits that remain
- No Precision@5 result from these artifacts exists in the repository, because the labels are empty. Any figure quoted elsewhere must be verified before use.
- Copies distributed outside the repository cannot be recalled by this report.
- The synthetic-only guard is process-memory based (see update 2, section 4). It is a safeguard, not a security guarantee.

### Flags and boundaries
- `BUSINESS_MATCHING_ENABLED = False`. Unchanged.
- No production activation. No real personal-data processing.
- Server-level deployment verification remains NOT VERIFIED (R4).
- Legal items O1–O13 remain open.
