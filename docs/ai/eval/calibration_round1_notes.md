# Catatan Kalibrasi Putaran 1 (200 kasus sintetis)

**Status:** catatan proses. **Bukan hasil.** Label putaran 1 tidak dihitung kappa atau Precision@5 untuk dilaporkan.

## Ringkasan distribusi

| Evaluator | Reviewer | Customer (RELEVANT / NOT_RELEVANT / UNKNOWN) | Business (RELEVANT / NOT_RELEVANT / UNKNOWN) | Total UNKNOWN |
|---|---|---|---|---|
| Evaluator 1 | Bara | 12 / 12 / 76 | 13 / 13 / 74 | 150 / 200 (75%) |
| Evaluator 2 | Naya | 30 / 21 / 49 | 26 / 23 / 51 | 100 / 200 (50%) |

Target di rubrik v0.2: UNKNOWN di bawah 15% per evaluator.

## Alasan yang diberikan evaluator

**Evaluator 2 (Naya):** kombinasi dimensi kosong (null) dan standar penilaian yang berhati-hati. Ketika indikator memberi sinyal campuran atau belum cukup kuat, memilih UNKNOWN daripada kesimpulan yang berpotensi keliru.

**Evaluator 1 (Bara):** standar kepastian tinggi. Keputusan RELEVANT atau NOT_RELEVANT hanya diambil jika didukung indikator yang kuat. Tidak ingin mengasumsikan dimensi kosong, dan menghindari keputusan spekulatif. Bara sendiri menilai pendekatannya mungkin terlalu konservatif.

## Temuan kalibrasi

1. **Protokol tidak mendefinisikan arti RELEVANT/NOT_RELEVANT dan ambang skor.** Akibatnya tiap evaluator memakai aturan sendiri.
2. **Protokol tidak mengatur apakah dimensi kosong membuat kasus UNKNOWN.** Kedua evaluator menganggapnya bisa, dan itu menjelaskan sebagian besar UNKNOWN.
3. **Generator membuat sekitar 15% dimensi kosong secara acak.** Sebagian kasus memang sulit dinilai dengan jujur, jadi sebagian UNKNOWN wajar terhadap data itu. Kesalahan ada di desain dataset, bukan hanya di evaluator.
4. **Sebaran nilai merata** (acak 0–1). Akibatnya banyak kasus jatuh ke zona sedang yang ambigu. Dataset putaran 1 tidak cukup beragam untuk menguji rubrik.

## Yang diputuskan untuk putaran berikutnya

- Rubrik v0.2 (`docs/ai/eval/RUBRIC_v0.2.md`) menjadi acuan. Ambangnya masih usulan dan perlu divalidasi.
- Putaran 2 memakai **kasus baru**, tidak menilai ulang 200 kasus ini.
- Sebaran putaran 2 harus disengaja: jelas relevan, jelas tidak relevan, zona sedang, dan dimensi kunci kosong.
- 200 kasus putaran 1 **tidak** dipakai untuk melaporkan akurasi.

## Kode aturan yang diminta untuk putaran 2

Setiap label wajib menyebut kode aturan di `comment`: R1, R2, R3, atau R4. Ini memungkinkan kita menelusuri kenapa setiap label dipilih.
