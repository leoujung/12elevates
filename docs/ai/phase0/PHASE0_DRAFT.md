# 12ELEVATE — AI Network Building Intelligence
## Phase 0 — Product Definition & AI Specification (DRAFT v0.1)

**Status dokumen:** DRAFT. Belum disetujui. Setiap keputusan bertanda `[KEPUTUSAN TERBUKA]` harus diputuskan oleh Leo sebelum Phase 1.
**Sumber acuan:** `12ELEVATE_MASTER_AI_EXECUTION_PLAN.md` (v1.0).
**Batas:** dokumen ini tidak berisi kode, tidak mengubah production, dan tidak mengandung data nyata.

---

## 1. PRD ringkas

### 1.1 Masalah
Member 12ELEVATE punya prospek dan kontak, tapi tidak tahu siapa yang paling relevan untuk didekati, kenapa, dan langkah apa berikutnya. Data yang ada tersebar (form, webinar, assessment) dan belum dinilai.

### 1.2 Tujuan MVP
Member mendapat daftar kandidat yang diurutkan, dengan alasan yang bisa ditelusuri, dan keputusan tetap di tangan member.

### 1.3 Di luar scope MVP
- CRM lengkap, dashboard analytics besar, microservices, vector database terpisah.
- Outreach otomatis tanpa persetujuan member.
- Diagnosis atau klaim kesehatan.
- Scraping sumber yang melanggar ketentuan.
- Mesin B (Business Builder) sampai legal review selesai `[KEPUTUSAN TERBUKA: urutan Mesin B]`.

### 1.4 Pengguna
Member 12ELEVATE (coach/business owner) yang ingin menentukan siapa yang akan dihubungi.

### 1.5 Use case
- **UC-A (Customer Matching):** member melihat daftar calon customer, skornya, alasannya, dan saran pendekatan.
- **UC-B (Business Builder Matching):** sama, untuk calon builder. Ditunda, lihat 1.3.

### 1.6 Tiga indikator yang dipisah (wajib)
| Indikator | Arti | Sumber |
|---|---|---|
| Match Score | seberapa cocok dengan kriteria | bobot scoring deterministik |
| Intent Confidence | seberapa kuat bukti minat yang dinyatakan/diizinkan | jumlah dan jenis sinyal yang sah |
| Data Confidence | seberapa lengkap dan mutakhir data | kelengkapan field dan umur data |

Ketiganya **bukan** probabilitas beli atau bergabung.

---

## 2. Data Dictionary (draft)

Setiap field wajib punya: sumber, dasar penggunaan (consent purpose), retensi, dan status ketersediaan.

| Field | Tipe | Sumber | Dasar penggunaan | Dipakai matching? | Catatan |
|---|---|---|---|---|---|
| `prospect_id` | string | sistem | — | tidak | ID canonical, bukan PII |
| `member_id` (tenant) | string | sistem | — | ya (isolasi) | wajib pada setiap baris |
| `source_type` | enum | sistem | — | ya | INBOUND / EXTERNAL |
| `source_ref` | string | sistem | — | tidak | provenance |
| `received_at` | timestamp | sistem | — | ya (freshness) | |
| `declared_interests` | list | form sukarela | consent minat (BELUM ADA) | ya (Mesin A) | `[KEPUTUSAN TERBUKA]` |
| `education_preference` | enum | form sukarela | consent minat (BELUM ADA) | ya | |
| `assessment_features` | map turunan | assessment | consent assessment | ya | jawaban mentah TIDAK disimpan di log |
| `webinar_attendance` | event | webinar | consent webinar (DITUNDA) | ya | belum ada event kehadiran |
| `product_category_interest` | list | form/klik | consent minat | ya | belum ada sumbernya |
| `communication_response` | event | komunikasi | consent komunikasi | ya | belum ada sumbernya |
| `business_interest` | list | form sukarela | consent profiling (BELUM ADA) | ya (Mesin B) | ditunda |
| `consent_status` | per purpose | ledger | — | gerbang | append-only |
| `suppression` | flag | suppression list | — | gerbang | opt-out selalu menang |

**Aturan data:**
- Field tanpa dasar penggunaan yang sah **tidak boleh** masuk ke scoring. Kolom yang kosong dihitung sebagai *missing*, bukan 0.
- Data assessment dipakai hanya lewat fitur turunan dan consent khusus, bukan jawaban mentah.
- Data eksternal tidak otomatis boleh untuk pemasaran.

**Status ketersediaan saat ini (verifikasi, bukan asumsi):**
- Tersedia di staging: identitas prospect, sumber, consent ledger, suppression, tenant (`member_id`).
- **Belum ada:** `declared_interests`, `education_preference`, `webinar_attendance`, `product_category_interest`, `communication_response`, `business_interest`, fitur assessment turunan.

---

## 3. Spesifikasi scoring (baseline deterministik)

Bobot di bawah adalah **hipotesis awal** dari master plan, belum dikalibrasi.

### 3.1 UC-A Customer Matching
| Dimensi | Bobot awal |
|---|---:|
| Declared wellness interest | 30% |
| Education preference | 20% |
| Declared needs and goals | 20% |
| Engagement relevance | 15% |
| Product-category interest | 15% |

**Aturan perhitungan:**
- Skor per dimensi = nilai ternormalisasi 0–1 × bobot. Dimensi tanpa data = **missing**, bobotnya dikeluarkan dan skor dinormalisasi ulang, lalu **Data Confidence diturunkan**. Missing tidak pernah dihitung sebagai nilai rendah yang tampak pasti.
- Confidence tidak boleh dihitung dari angka acak. Intent Confidence dihitung dari jumlah dan jenis sinyal yang sah; Data Confidence dari kelengkapan dan umur data.
- Hasil harus dapat direproduksi: input yang sama → skor yang sama. Versi bobot dicatat pada setiap hasil.

### 3.2 UC-B Business Builder (ditunda, draft)
| Dimensi | Bobot awal |
|---|---:|
| Declared entrepreneurship interest | 30% |
| Business goals alignment | 25% |
| Relevant experience | 15% |
| Digital/business interest | 15% |
| Leadership and development interest | 15% |

Catatan: pengalaman bisnis/MLM hanya dipakai bila diberikan sukarela. Tidak boleh disimpulkan dari jabatan pekerjaan.

### 3.3 Peran LLM
- LLM **tidak** menghitung atau mengubah skor.
- LLM hanya menjelaskan hasil dari alasan yang sudah dihitung, dan menyusun saran pendekatan.
- RAG hanya memberi konteks edukasi dengan referensi sumber.

### 3.4 Format output (contoh, bukan data nyata)
Field output mengikuti master plan: `match_score`, `intent_confidence`, `data_confidence`, `reasons`, `missing_fields`, `recommended_action`, `weights_version`.

---

## 4. AI Governance & Privacy Rules

1. **Dasar penggunaan terpisah:** consent pemrosesan layanan, consent marketing (opsional, tidak pre-checked), dan consent profiling/matching dicatat terpisah dengan timestamp, versi notice, dan sumber. `[KEPUTUSAN TERBUKA: teks notice dan versinya, butuh legal]`
2. **Tidak ada consent palsu:** submit form publik bukan izin marketing.
3. **Opt-out menang:** suppression dicek sebelum proses apa pun.
4. **Human-in-the-loop:** tidak ada outreach otomatis. Member memutuskan.
5. **Wellness:** assessment bukan diagnosis. Tidak ada klaim kesehatan yang tidak didukung sumber.
6. **External discovery:** hanya sumber resmi/berizin. Tidak ada scraping yang melanggar ketentuan, tidak melewati login/CAPTCHA/rate limit. Tidak menyimpulkan minat dari foto, kondisi fisik, atau jabatan.
7. **Retensi dan hak subjek:** `[KEPUTUSAN TERBUKA: masa retensi]`. Prospek dapat meminta pembaruan atau penghapusan.
8. **MLM/direct selling:** regulasi dan aturan rekrutmen perlu dicek legal sebelum Mesin B. Belum diverifikasi.
9. **Kebijakan isolasi:** member hanya melihat prospeknya sendiri. Pertemuan lintas member (untuk Mesin B) butuh desain tersendiri, tidak bisa diasumsikan dari isolasi tenant.

---

## 5. MVP Acceptance Test Plan (draft)

Setiap kriteria punya bukti yang harus dihasilkan. Status: `NOT STARTED` untuk semua pada Phase 0.

| ID | Kriteria | Bukti yang harus ada | Status |
|---|---|---|---|
| AC-01 | Setiap hasil punya alasan yang bisa ditelusuri | reason per dimensi | NOT STARTED |
| AC-02 | Skor dapat direproduksi | uji determinisme dengan input tetap | NOT STARTED |
| AC-03 | Missing data tidak menghasilkan confidence palsu | uji data kosong → confidence turun | NOT STARTED |
| AC-04 | Duplikat event tidak menghasilkan duplikasi | uji idempotency | BLOCKED (Blocker 1, PRIORITAS 1) |
| AC-05 | Isolasi tenant | uji cross-tenant | PARTIAL (E1.2 PG 27/27; belum untuk matching) |
| AC-06 | Consent/eligibility sebelum matching | uji gerbang | NOT STARTED |
| AC-07 | Precision@5 ≥ 70% | test set berlabel manusia | BLOCKED (belum ada label) |
| AC-08 | Tidak ada outreach otomatis | uji tidak ada pengiriman tanpa persetujuan | NOT STARTED |

**Catatan penting:** Precision@5 tidak bisa diukur tanpa test set berlabel yang dinilai manusia. Synthetic test case hanya untuk menguji fungsi teknis, bukan akurasi dunia nyata.

---

## 6. Keputusan yang harus diambil Leo (sebelum Phase 1)

1. Urutan: Mesin A dulu, Mesin B ditunda? (usulan: ya)
2. Teks notice dan versi consent untuk profiling/matching (butuh legal).
3. Masa retensi data prospek.
4. Sumber data pertama untuk Phase 4 (inbound) dan Phase 5 (external) yang sah.
5. Siapa yang membuat label test set untuk Precision@5, dan berapa jumlahnya.
6. Apakah fitur assessment turunan boleh dipakai untuk matching, dan dengan consent apa.

## 7. Blocker yang mempengaruhi Phase 0–1
- Blocker 1 (event/registration ID acak di browser) → memengaruhi AC-04.
- E1.3 pending, PRIORITAS 1 pending.
- Consent webinar ditunda (`WEBINAR_CONSENT_GATE` off).
- Identitas repo `ingatsehat-network-funnel` masih NOT VERIFIED.
