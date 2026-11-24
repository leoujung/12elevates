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
