# Dependensi Implementasi — Direktif 12E-LEGAL-AI-NBI-002

**Status dokumen sumber:** "Internal Legal & Compliance Directive — Draft for Management Adoption". Berlaku efektif setelah diadopsi manajemen. Dokumen itu sendiri menyatakan penerbitan resmi perlu adopsi perwakilan manajemen yang berwenang.
**Status file ini:** catatan dependensi. Bukan persetujuan legal dan bukan dasar hukum.

## Yang sekarang diizinkan (tanpa data nyata)
- Pengembangan Customer dan Business Matching dengan data sintetis.
- Consent management, RBAC, audit trail, pengujian.
- Business Matching boleh masuk tahap aktivasi terkontrol **setelah** dependensi di bawah terpenuhi. Saat ini flag `BUSINESS_MATCHING_ENABLED` tetap `False`.

## Dependensi per item (status per hari ini)

| No | Syarat (dari direktif) | Status | Bukti/Catatan |
|---|---|---|---|
| D1 | Direktif diadopsi manajemen | BELUM DIVERIFIKASI | Perlu konfirmasi tertulis dari manajemen |
| D2 | Dasar hukum per tujuan (Art. 20 UU PDP 27/2022, sesuai rujukan direktif) | BELUM ADA | Harus didokumentasikan per tujuan: matching_customer, matching_business, marketing |
| D3 | Consent notice APPROVED (versi + referensi legal tertulis) | BELUM ADA | Draf DRAFT — BELUM DISETUJUI; `consent.py` menolak GRANTED dengan notice DRAFT |
| D4 | Sumber data terverifikasi dan terlacak per record | BELUM ADA | Field provenance belum diisi pada data nyata |
| D5 | Record yang tidak terverifikasi masuk status restricted/pending | BELUM ADA | Mekanisme status belum dibangun |
| D6 | Penilaian DPIA (pemrosesan sistematis, scoring, AI baru) | BELUM ADA | Direktif mewajibkan penilaian; belum dikerjakan |
| D7 | Data kategori C (kesehatan, dll.) dikeluarkan dari Business Matching default | PERLU TINJAUAN | Assessment wellness 12ELEVATE berpotensi memuat data kesehatan. Perlu klasifikasi sebelum dipakai untuk matching |
| D8 | Akses hasil matching hanya untuk peran berwenang | SEBAGIAN | RBAC dan audit sudah ada sebagai modul; belum ada API nyata |
| D9 | Withdrawal consent berfungsi | SEBAGIAN | Ledger sintetis sudah ada; belum tersambung database |
| D10 | Transparansi kepada member (controller, tujuan, retensi, hak, kontak) | BELUM ADA | Perlu teks notice APPROVED |
| D11 | Tidak ada keanggotaan yang otomatis memberi akses data member lain | SEBAGIAN | Diuji di RBAC sintetis |

## Keputusan teknis
1. **Flag `BUSINESS_MATCHING_ENABLED` tidak diubah.** Direktif membolehkan aktivasi terkontrol, tetapi aktivasi global tanpa D2–D6 akan membuka matching untuk data nyata tanpa dasar yang terdokumentasi.
2. **Outreach otomatis dan external discovery tetap di luar scope** (direktif bagian III dan IX.P2).
3. Setiap record nyata tanpa D4 dan D5 wajib ditandai restricted dan tidak masuk matching.

## Pertanyaan untuk legal (spesifik, bukan "masih menunggu")
1. Apa dasar hukum yang dipilih untuk matching_business: consent, kontrak, atau kepentingan sah? Apakah berbeda untuk data yang sudah ada di database member?
2. Apakah assessment wellness dikategorikan data kesehatan (kategori C)? Jika ya, apakah matching customer boleh memakai `declared_wellness_interest` yang diturunkan dari jawaban assessment?
3. Siapa yang menjadi controller, dan apakah ada joint controller dengan pihak lain (partner, IngatSehat)?
4. Kapan DPIA harus selesai, dan apakah P1 boleh berjalan sementara DPIA dikerjakan?
5. Mohon konfirmasi tertulis bahwa direktif ini sudah diadopsi manajemen.
