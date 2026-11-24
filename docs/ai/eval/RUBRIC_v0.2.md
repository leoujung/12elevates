# RUBRIK PENILAIAN — 12ELEVATE Blind Labelling (v0.2, untuk putaran kalibrasi 2)

**Status:** DRAFT untuk disetujui. Ambang angka di bawah adalah usulan awal, bukan nilai yang sudah divalidasi. Revisi setelah putaran 2.
**Berlaku untuk:** kasus baru pada putaran 2. Tidak berlaku surut untuk 200 kasus putaran 1 (lihat `calibration_round1_notes.md`).
**Data:** sintetis saja (ID `syn-*`).

---

## 1. Aturan dasar

- Evaluator hanya menilai dari **nilai profile yang tertulis di file**. Tidak boleh mengira-ngira isi dimensi yang kosong.
- Evaluator **tidak melihat** skor, ranking, atau penjelasan dari sistem apa pun.
- Setiap label wajib disertai `comment` yang menyebut **kode aturan** (R1, R2, R3, R4), contoh: `R2: declared_wellness_interest 0.45, pendukung campuran`.

---

## 2. Arti RELEVANT dan NOT_RELEVANT

**RELEVANT** berarti: minat yang dinyatakan kandidat **cocok dengan topik yang ditawarkan** (edukasi wellness untuk customer; pengembangan bisnis untuk business). Bukan berarti "pasti akan membeli" atau "pasti akan bergabung".

**NOT_RELEVANT** berarti: minat yang dinyatakan kandidat **jelas tidak cocok** dengan topik tersebut.

**Dimensi kunci per mesin** (menentukan keputusan utama):

| Mesin | Dimensi kunci | Dimensi pendukung |
|---|---|---|
| Customer | `declared_wellness_interest` | `education_preference`, `product_category_interest`, `declared_needs_goals`, `engagement_relevance` |
| Business | `declared_entrepreneurship_interest` | `business_goals_alignment`, `digital_business_interest`, `leadership_development_interest`, `relevant_experience_declared` |

Catatan: `relevant_experience_declared` hanya dipakai bila terisi dari pernyataan sukarela. Tidak boleh disimpulkan dari jabatan.

---

## 3. Ambang (usulan)

- **Tinggi:** nilai ≥ 0,60
- **Rendah:** nilai ≤ 0,30
- **Sedang:** di antara keduanya (0,30 – 0,60)

---

## 4. Aturan keputusan (urutan dibaca dari atas)

**R1. Dimensi kunci terisi dan tinggi (≥ 0,60)** → **RELEVANT**.

**R2. Dimensi kunci terisi dan rendah (≤ 0,30)** → **NOT_RELEVANT**.

**R3. Dimensi kunci terisi, nilai sedang (0,30 – 0,60):** lihat dimensi pendukung yang terisi.
- Jika **mayoritas** pendukung ≥ 0,60 → **RELEVANT**.
- Jika **mayoritas** pendukung ≤ 0,30 → **NOT_RELEVANT**.
- Jika tidak ada mayoritas jelas (sinyal campuran) → **UNKNOWN**.

**R4. Dimensi kunci kosong (null):** lihat dimensi pendukung yang terisi.
- Jika semua pendukung yang terisi ≥ 0,60 → **RELEVANT**.
- Jika semua pendukung yang terisi ≤ 0,30 → **NOT_RELEVANT**.
- Jika tidak ada pendukung yang terisi, atau sinyalnya campuran → **UNKNOWN**.

---

## 5. Kapan UNKNOWN boleh dipakai

UNKNOWN **hanya** boleh dipakai jika salah satu berlaku:
- **R3 sinyal campuran**: dimensi kunci sedang dan pendukung tidak mengarah jelas ke satu sisi.
- **R4 tidak ada bukti**: dimensi kunci kosong dan tidak ada pendukung yang terisi, atau pendukung saling bertentangan.

UNKNOWN **tidak boleh dipakai** karena:
- Dimensi **pendukung** yang kosong. Kekosongan pendukung tidak membuat kasus jadi UNKNOWN jika dimensi kunci sudah jelas (R1/R2).
- Evaluator merasa "harus yakin 100%". Standarnya adalah keputusan terbaik dari bukti yang tertulis, bukan kepastian mutlak.
- Kasus terasa sulit. Kesulitan bukan alasan UNKNOWN.

**Target distribusi wajar:** UNKNOWN idealnya di bawah 15% per evaluator. Jika di atas itu, evaluator perlu memeriksa ulang R3 dan R4, dan catatan alasan wajib ditulis.

---

## 6. Yang dicatat untuk setiap label

- `human_label`: RELEVANT / NOT_RELEVANT / UNKNOWN
- `comment`: kode aturan + nilai dimensi yang dipakai. **Wajib** jika UNKNOWN.
- `reviewer_id`, `reviewed_at`: wajib.

---

## 7. Yang belum diputuskan (BLOCKED)

1. Ambang 0,60 dan 0,30 sudah benar atau perlu disesuaikan? Ini perlu diuji dengan data putaran 2, bukan ditebak.
2. Apakah perlu aturan untuk pendukung yang bertentangan secara ekstrem (satu ≥ 0,60, satu ≤ 0,30)?
3. Ambang kappa yang dianggap layak (usulan awal ≥ 0,6, belum diputuskan).

---

## 8. Catatan penting untuk putaran 2

Dataset putaran 1 dibuat dengan nilai acak merata. Akibatnya sebagian besar kasus jatuh ke zona sedang, dan rubrik ini akan sering memberi UNKNOWN. Putaran 2 harus punya kasus yang **sebarannya disengaja**: sebagian jelas RELEVANT, sebagian jelas NOT_RELEVANT, sebagian sedang, dan sebagian dimensi kunci kosong. Tanpa itu, kita tidak bisa tahu apakah rubrik ini bekerja.
