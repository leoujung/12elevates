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
