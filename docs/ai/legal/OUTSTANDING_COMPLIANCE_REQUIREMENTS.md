# Outstanding Compliance Requirements — 12ELEVATE AI Network Building Intelligence

**Untuk:** Project Management, System Administrator, Legal & Compliance Advisory
**Dasar:** 12E-DIR-ADP-001 bagian 6 (laporan progres dan daftar outstanding requirements)
**Tanggal status:** 24 November 2026
**Sifat dokumen:** status internal, bukan opini hukum dan bukan persetujuan.

## 1. Yang sudah dikerjakan (teknis, data sintetis)
| Komponen | Bukti | Status |
|---|---|---|
| Customer Matching (scoring deterministik, ranking, explanation) | `backend/ai/customer_matching.py`, 15 tes | Selesai, sintetis |
| Business Matching (scoring, opt-in, eligibility) | `backend/ai/business_matching.py`, 15 tes | Selesai, sintetis; flag tetap OFF |
| Consent management (notice versi, ledger append-only, withdrawal) | `backend/ai/consent.py`, 19 tes | Selesai, sintetis |
| RBAC dan audit trail | `backend/ai/rbac.py`, 16 tes | Selesai, sintetis |
| Jalur layanan terpadu (otorisasi → consent → field policy → ranking → audit) | `backend/ai/matching_service.py`, 18 tes | Selesai, sintetis |
| Klasifikasi field (wellness umum vs kondisi kesehatan) | `backend/ai/field_policy.py`, 17 tes | Selesai, sintetis; semua field PENDING_REVIEW |
| Skema DB consent/audit (proposal) | `docs/ai/db/consent_audit_schema.PROPOSAL.sql` | Diuji lokal; belum diterapkan |
| Labelling dan evaluasi (putaran 1, putaran 2, engine output) | `docs/ai/eval/` | Putaran 1 kalibrasi; putaran 2 konsistensi rubrik; engine output menunggu label |

Total tes sintetis: 9 suite, lebih dari 140 tes. Semua lulus. Setiap komponen juga diuji dengan mutan untuk memastikan tes menangkap pelanggaran aturan.

## 2. Outstanding — wajib sebelum data pribadi nyata diproses

| No | Requirement | Pemilik | Sumber | Status |
|---|---|---|---|---|
| O1 | Dasar hukum tertulis per tujuan: matching_customer, matching_business, marketing | Legal (Ibu Alexandra) | Direktif 002 IV.4.2; Art. 20 UU PDP | BELUM ADA |
| O2 | Teks consent notice APPROVED dengan referensi legal tertulis, per tujuan | Legal + Direktur | Direktif 002 IV.4.4, VIII | BELUM ADA; draf tidak sah |
| O3 | DPIA (pemrosesan sistematis/scoring, AI baru) | Legal + Project Management | Addendum 003 V; Art. 34 UU PDP | BELUM DIMULAI |
| O4 | Review `declared_wellness_interest` terhadap nilai aktual dan cara pengumpulan | Legal + Product | Addendum 003 III | PENDING_REVIEW |
| O5 | Keputusan untuk `declared_needs_goals` (free-text, berisiko memuat konten medis) | Legal + Product | Addendum 003 III/IV | PENDING; disarankan batasi ke pilihan tetap |
| O6 | Kebijakan retensi consent dan audit | Legal | Direktif 002 VII.g; Direktif 001 | BELUM DIPUTUSKAN; berbenturan dengan hak penghapusan |
| O7 | Mekanisme hak penghapusan dan koreksi data | Legal + Engineering | UU PDP | BELUM ADA |
| O8 | Verifikasi provenance per record nyata (sumber terlacak) | Data owner | Direktif 002 IV.4.1, IV.4.3 | BELUM ADA; record tanpa provenance harus restricted |
| O9 | Pemeriksaan data kesehatan pada assessment (apakah jawaban assessment masuk ke sumber matching) | Legal + Engineering | Addendum 003 IV | BELUM DIVERIFIKASI |
| O10 | Role akses DB aplikasi (GRANT/REVOKE) untuk tabel consent/audit | System Admin | Direktif 002 VII | Skema placeholder |
| O11 | Autentikasi nyata untuk API matching (saat ini Actor diisi manual) | Engineering | Direktif 001 III.a | BELUM ADA |
| O12 | Penerapan skema DB ke staging, lalu uji dengan PostgreSQL staging | Engineering + persetujuan Direktur | — | MENUNGGU PERSETUJUAN |
| O13 | Transparansi kepada member (controller, tujuan, retensi, hak, kontak) | Legal + Product | Direktif 002 IV.4.4 | BELUM ADA |
| O14 | Kebijakan penggunaan data pihak ketiga (external prospect discovery) | Legal | Direktif 002 III (P2) | Di luar scope sekarang |

## 3. Yang masih dilarang sampai O1–O4 dan O8 terpenuhi
- Mengaktifkan `BUSINESS_MATCHING_ENABLED` untuk data pribadi nyata.
- Menjalankan matching customer atau business terhadap record member nyata.
- Outreach otomatis, marketing, external discovery dengan data pribadi.

## 4. Catatan
- Adopsi direktur membuka **pengembangan**. Tidak membuka **pemrosesan data nyata**. Keduanya dibedakan oleh dokumen itu sendiri (bagian 2 dan 7).
- O1 dan O2 adalah dua hal yang paling menentukan. Tanpa keduanya, tidak ada dasar untuk aktivasi, sekalipun teknisnya sudah siap.
