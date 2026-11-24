# 12ELEVATE — MASTER AI EXECUTION PLAN
## AI Network Building Intelligence | AI-First MVP

**Versi:** 1.0  
**Strategi produk:** Balanced Customer + Business Matching  
**Prospect Discovery:** Inbound + External Discovery sejak MVP  
**Prinsip utama:** AI-first, infrastructure-light, measurable, privacy-conscious, human-in-the-loop.

---

# 1. Product Vision

12ELEVATE membangun **AI Network Building Intelligence**, sebuah sistem kecerdasan untuk membantu setiap member mengambil keputusan dalam membangun jaringan secara lebih relevan, terarah, dan terukur.

Sistem harus mampu menjawab empat pertanyaan utama:

1. Siapa calon customer yang paling relevan untuk saya?
2. Siapa calon business builder yang paling relevan untuk saya?
3. Mengapa orang tersebut cocok untuk dihubungi?
4. Apa pendekatan dan langkah berikutnya yang paling tepat?

Produk bukan sekadar menyimpan data prospek. Produk harus mengubah data yang tersedia menjadi rekomendasi dan keputusan yang dapat ditindaklanjuti.

## Dua mesin utama

### A. AI Customer Matching

Mencocokkan calon customer berdasarkan:

- Minat terhadap topik wellness dan healthy lifestyle.
- Preferensi edukasi yang dinyatakan secara sukarela.
- Hasil lifestyle assessment yang diberikan dengan persetujuan.
- Partisipasi webinar dan interaksi edukasi.
- Minat terhadap kategori produk atau informasi tertentu.
- Riwayat komunikasi dan respons yang memang diizinkan untuk digunakan.

Output:
- Ranked customer matches.
- Match score dan confidence.
- Alasan kecocokan.
- Topik edukasi yang relevan.
- Rekomendasi pendekatan dan next best action.

### B. AI Business Builder Matching

Mencocokkan calon business builder berdasarkan:

- Minat entrepreneurship yang dinyatakan sendiri.
- Pengalaman bisnis atau network marketing yang diberikan secara sukarela.
- Tujuan bisnis dan aspirasi profesional.
- Kemampuan serta pengalaman yang relevan.
- Minat pada digital marketing, AI, leadership, dan business development.
- Respons terhadap materi edukasi bisnis.

Output:
- Ranked business builder matches.
- Business-fit score dan confidence.
- Alasan kecocokan.
- Potensi kebutuhan pengembangan.
- Rekomendasi pendekatan dan next best action.

**Prinsip:** Kedua mesin menggunakan fondasi teknologi yang sama, tetapi memiliki kriteria matching, bobot, dan evaluasi yang berbeda.

---

# 2. Product Architecture

Arsitektur konseptual:

```text
                 12ELEVATE ECOSYSTEM
                         |
              ONE MEMBER EXPERIENCE
                         |
             AI NETWORK INTELLIGENCE
                         |
          +--------------+--------------+
          |                             |
    CUSTOMER MATCHING            BUSINESS MATCHING
          |                             |
          +--------------+--------------+
                         |
               MATCHING ENGINE
                         |
       +-----------------+-----------------+
       |                 |                 |
   Intent Engine    Fit Scoring       AI Reasoning
       |                 |                 |
       +-----------------+-----------------+
                         |
                KNOWLEDGE / RAG
                         |
              PROSPECT INTELLIGENCE
                         |
          +--------------+--------------+
          |                             |
   INBOUND DISCOVERY             EXTERNAL DISCOVERY
          |                             |
   Website / Assessment       Approved Sources / APIs
   Webinar / Referral         Licensed Data / Opt-in
          |                             |
          +--------------+--------------+
                         |
                DATA FOUNDATION
                         |
            PostgreSQL + pgvector
                         |
             FastAPI + Python Services
                         |
                 n8n Automation
```

## Komponen inti

| Komponen | Fungsi |
|---|---|
| ONE Member Experience | Antarmuka AI untuk member |
| AI Matching Engine | Menghitung dan mengurutkan kecocokan |
| Intent Engine | Mengidentifikasi minat yang dinyatakan |
| AI Reasoning | Menjelaskan hasil dan memberikan rekomendasi |
| RAG Knowledge Base | Menyediakan konteks edukasi dan panduan |
| Inbound Intelligence | Mengolah prospek yang masuk |
| External Discovery | Menemukan prospek dari sumber yang diizinkan |
| FastAPI | Backend dan API |
| PostgreSQL + pgvector | Penyimpanan data dan pencarian semantik |
| n8n | Otomasi integrasi dan proses bisnis |

---

# 3. AI-First Execution Roadmap

Estimasi pelaksanaan: **10 minggu untuk MVP**, dengan asumsi akses sumber data, infrastruktur staging, dan keputusan produk tersedia. Ini merupakan target perencanaan, bukan jaminan durasi.

## PHASE 0 — Product Definition & AI Specification

**Estimasi: Minggu 1**

Tujuan: mengunci definisi produk dan memastikan semua pekerjaan teknis mengarah pada AI Matching.

Pekerjaan:

1. Menetapkan use case Customer Matching.
2. Menetapkan use case Business Builder Matching.
3. Mendefinisikan data input dan output kedua mesin.
4. Menentukan scoring dimensions dan bobot awal.
5. Menentukan data yang boleh dan tidak boleh digunakan.
6. Menentukan perbedaan antara match score, intent confidence, dan data confidence.
7. Menentukan acceptance criteria MVP.

Deliverables:

- Product Requirement Document (PRD).
- AI Matching Specification.
- Data Dictionary.
- Matching Scoring Specification.
- AI Governance & Privacy Rules.
- MVP Acceptance Test Plan.

**Exit criteria:**
- Kedua use case memiliki definisi input dan output.
- Seluruh variabel scoring terdokumentasi.
- Setiap jenis data memiliki sumber dan dasar penggunaan yang jelas.
- Tidak ada ketergantungan pada CRM lengkap untuk memulai AI.

## PHASE 1 — Minimum Data Foundation

**Estimasi: Minggu 2**

Tujuan: membangun fondasi data minimum yang langsung mendukung AI.

Pekerjaan:

1. Audit struktur database yang sudah tersedia.
2. Menetapkan canonical prospect ID dan member ID.
3. Menetapkan tenant isolation.
4. Menetapkan event identity dan idempotency.
5. Menetapkan consent dan provenance.
6. Menyediakan struktur data customer dan business prospect.
7. Menyiapkan API untuk memasukkan dan membaca data prospek.

Data minimum:

- Prospect identity.
- Source dan provenance.
- Member ownership / tenant.
- Declared interests.
- Declared goals.
- Relevant interactions.
- Consent status dan timestamp.
- Data freshness.
- Matching eligibility.

Deliverables:

- Canonical Data Model.
- API Contract.
- Database Migration.
- Data Validation Tests.
- Tenant Isolation Tests.
- Consent & Provenance Tests.

**Exit criteria:**
- Tidak ada duplikasi identitas yang tidak terkontrol.
- Pengiriman ulang event yang sama tidak menghasilkan duplikasi.
- Data antar-tenant terisolasi.
- Data tanpa dasar penggunaan yang sah tidak masuk ke matching.
- Minimal satu sumber inbound dan satu sumber external yang sah telah dipetakan.

**Batasan:** pekerjaan ini hanya menyediakan data foundation minimum. Tidak perlu membangun CRM lengkap, dashboard analytics besar, atau integrasi yang belum diperlukan AI.

## PHASE 2 — Core AI Matching Engine

**Estimasi: Minggu 3–4**

Ini adalah fase paling penting dalam MVP.

Tujuan: menghasilkan matching yang benar-benar dapat diuji, bukan sekadar AI chatbot.

Pekerjaan:

1. Membangun Customer Matching Engine.
2. Membangun Business Builder Matching Engine.
3. Mengembangkan feature extraction.
4. Mengembangkan scoring dan ranking.
5. Menghasilkan alasan kecocokan.
6. Menyediakan rekomendasi next best action.
7. Menguji hasil dengan data contoh yang telah divalidasi.

### Model scoring awal

Gunakan scoring deterministik yang transparan sebagai baseline.

**Customer Matching — contoh bobot awal**

| Dimensi 			| Bobot |
| ---				|  ---:	|
| Declared wellness interest 	| 30% 	|
| Education preference 		| 20% 	|
| Declared needs and goals 	| 20% 	|
| Engagement relevance 		| 15% 	|
| Product-category interest 	| 15% 	|
| Total 			| 100% 	|

**Business Builder Matching — contoh bobot awal**

| Dimensi 				| Bobot |
| ---					| ---:	|
| Declared entrepreneurship interest 	| 30% 	|
| Business goals alignment 		| 25% 	|
| Relevant experience 			| 15% 	|
| Digital/business interest 		| 15% 	|
| Leadership and development interest	| 15% 	|
| Total 				| 100%	|

Bobot di atas merupakan hipotesis awal yang harus diuji dan dikalibrasi. Jangan menganggap skor sebagai probabilitas seseorang akan membeli atau bergabung.

### Tiga indikator yang wajib dipisahkan

- **Match Score:** seberapa cocok profil dengan kriteria yang ditetapkan.
- **Intent Confidence:** seberapa kuat bukti minat yang dinyatakan atau diperlihatkan secara sah.
- **Data Confidence:** seberapa lengkap, relevan, dan mutakhir data yang digunakan.

Contoh hasil:

```json
{
  "match_type": "business_builder",
  "match_score": 86,
  "intent_confidence": 0.91,
  "data_confidence": 0.84,
  "reasons": [
    "Declared interest in entrepreneurship",
    "Relevant digital business experience",
    "Aligned business development goals"
  ],
  "recommended_action": "Invite to business education webinar"
}
```

**Exit criteria:**
- Kedua mesin dapat menghasilkan ranking.
- Setiap hasil memiliki alasan yang dapat ditelusuri.
- Skor dapat direproduksi dari input yang sama.
- Missing data tidak menghasilkan confidence palsu.
- Tersedia minimal 100 labeled test cases per jalur matching atau jumlah lain yang disetujui berdasarkan ketersediaan data.
- Evaluasi awal menghasilkan Precision@5 minimal 70% pada test set yang telah dinilai manusia.

Jika jumlah data belum mencukupi, gunakan synthetic test cases untuk menguji fungsi teknis, tetapi jangan menganggap hasilnya sebagai bukti akurasi dunia nyata.

## PHASE 3 — RAG Knowledge Intelligence

**Estimasi: Minggu 5**

Tujuan: membuat hasil matching dan rekomendasi AI memiliki konteks pengetahuan yang konsisten.

Knowledge base awal:

1. Wellness education.
2. Lifestyle education.
3. Product education dan informasi resmi.
4. Business education.
5. Network building training.
6. Leadership development.
7. 12ELEVATE Academy materials.

Pekerjaan:

- Menyiapkan dokumen dan metadata.
- Chunking dan embedding.
- Menyimpan vector embeddings.
- Menerapkan retrieval berdasarkan konteks.
- Menambahkan source references.
- Menerapkan batasan akses berdasarkan tenant dan role jika diperlukan.

### Pembagian tugas AI dan RAG

| Teknologi | Tanggung jawab |
|---|---|
| Python scoring engine | Menghitung match score |
| Rules engine | Memastikan batasan dan eligibility |
| RAG | Mengambil pengetahuan relevan |
| LLM | Menjelaskan hasil dan menyusun rekomendasi |
| Human member | Menentukan tindakan akhir |

**Exit criteria:**
- AI dapat menjawab berdasarkan knowledge base.
- Jawaban penting memiliki referensi sumber.
- Dokumen yang tidak relevan tidak masuk ke konteks.
- RAG tidak mengubah atau mengarang hasil scoring.
- Informasi produk dan wellness tidak menghasilkan diagnosis atau klaim kesehatan yang tidak didukung.

## PHASE 4 — Inbound Prospect Intelligence

**Estimasi: Minggu 6**

Tujuan: mengubah interaksi dari ekosistem 12ELEVATE menjadi data prospek yang siap dianalisis AI.

Sumber:

- Replicated member website.
- Wellness assessment.
- Webinar registration.
- Education interaction.
- Referral.
- Member-submitted prospect.
- Inquiry forms.

Pekerjaan:

1. Menstandarkan event.
2. Menghubungkan event ke canonical prospect ID.
3. Memvalidasi consent.
4. Mengidentifikasi source dan member ownership.
5. Mengubah data menjadi matching features.
6. Mengirim data yang memenuhi syarat ke Matching Engine.

Contoh event:

```text
PROSPECT_REGISTERED
ASSESSMENT_COMPLETED
WEBINAR_REGISTERED
EDUCATION_INTEREST_DECLARED
BUSINESS_INTEREST_DECLARED
REFERRAL_SUBMITTED
CONSENT_UPDATED
```

**Exit criteria:**
- Minimal dua sumber inbound aktif di staging.
- Event dapat diproses secara idempotent.
- Data memiliki provenance.
- Prospek dapat masuk ke Customer atau Business Matching berdasarkan minat yang dinyatakan.
- Marketing consent dipisahkan dari consent pemrosesan yang diperlukan untuk layanan.
- Prospek dapat meminta pembaruan atau penghapusan data sesuai kebijakan yang berlaku.

## PHASE 5 — External Prospect Discovery

**Estimasi: Minggu 7–8**

Tujuan: menyediakan kemampuan discovery dari luar ekosistem inbound sejak MVP.

External Discovery bukan berarti mengambil semua profil publik dan menganggap pemiliknya tertarik.

### Sumber yang diperbolehkan

Prioritas sumber:

1. Official APIs dengan izin penggunaan yang sesuai.
2. Licensed business directories.
3. Partner data dengan dasar penggunaan yang jelas.
4. Opt-in directories dan komunitas yang mengizinkan discovery.
5. Member-submitted contacts dengan dasar komunikasi yang sah.
6. Public business information yang boleh digunakan sesuai ketentuan sumber dan hukum yang berlaku.

### Alur External Discovery

```text
APPROVED SOURCE
      |
SOURCE VALIDATION
      |
PROVENANCE CHECK
      |
PERMISSION / ELIGIBILITY CHECK
      |
DATA NORMALIZATION
      |
AI RELEVANCE ANALYSIS
      |
CUSTOMER OR BUSINESS CLASSIFICATION
      |
MATCHING ENGINE
      |
MEMBER REVIEW
      |
AUTHORIZED OUTREACH
```

### Batasan penting

- Tidak melakukan scraping yang melanggar ketentuan platform.
- Tidak melewati login, CAPTCHA, rate limits, atau access controls.
- Tidak menyimpulkan minat wellness dari foto, kondisi fisik, atau profil umum.
- Tidak menyimpulkan minat MLM atau entrepreneurship hanya dari jabatan pekerjaan.
- Tidak mengirim pesan otomatis tanpa otorisasi dan dasar komunikasi yang sesuai.
- Setiap external prospect harus memiliki source provenance dan eligibility status.

**Exit criteria:**
- Minimal satu external source yang sah terintegrasi.
- Data source dan provenance tersimpan.
- Data yang tidak memenuhi syarat tidak masuk ke ranking.
- Hasil discovery dapat dipisahkan menjadi Customer dan Business.
- Member dapat memeriksa alasan rekomendasi sebelum melakukan outreach.

Jika sumber eksternal yang sah belum tersedia, fase ini tetap dapat diselesaikan pada level connector dan workflow menggunakan data partner/opt-in yang disetujui. Jangan mengganti sumber yang sah dengan scraping tidak resmi hanya untuk mengejar target MVP.

## PHASE 6 — ONE AI Member Copilot

**Estimasi: Minggu 9**

Tujuan: menghadirkan AI secara nyata dalam pengalaman member.

Fitur MVP:

1. AI Customer Matches.
2. AI Business Builder Matches.
3. Search and filter.
4. Match explanation.
5. Intent dan data confidence.
6. Recommended next action.
7. AI conversation untuk memahami hasil.
8. Member feedback: relevant / not relevant.
9. Feedback untuk meningkatkan evaluasi matching.

Contoh tampilan:

```text
AI NETWORK INTELLIGENCE

CUSTOMER MATCHES
--------------------------------
Prospect A
Match Score: 89
Intent Confidence: High
Data Confidence: High

Why this match?
- Declared wellness education interest
- Relevant assessment interaction
- Interested in lifestyle education

Recommended Action:
Invite to relevant education session

--------------------------------

BUSINESS BUILDER MATCHES
--------------------------------
Prospect B
Match Score: 86
Intent Confidence: High
Data Confidence: Medium

Why this match?
- Declared entrepreneurship interest
- Relevant business experience
- Aligned business development goals

Recommended Action:
Invite to business opportunity education
```

**Exit criteria:**
- Member dapat melihat kedua jenis matching.
- Member memahami alasan rekomendasi.
- Member dapat memberikan feedback.
- Member dapat memilih tindakan berikutnya.
- Tidak ada automatic outreach tanpa persetujuan member.

## PHASE 7 — MVP Validation & Controlled Pilot

**Estimasi: Minggu 10**

Tujuan: memastikan produk bekerja dalam kondisi penggunaan nyata.

Pilot:

- 10–20 member terpilih.
- Kedua kategori matching aktif.
- Inbound dan external discovery diuji.
- Human review wajib.
- Tidak ada automatic mass messaging.

### KPI dan acceptance criteria

| KPI | Target MVP |
|---|---:|
| Precision@5 | ≥70% |
| Match explanation coverage | 100% |
| Data provenance coverage | 100% |
| Consent/eligibility validation | 100% |
| Duplicate event handling | 100% pada test cases |
| Tenant isolation | 100% pada test cases |
| Member feedback capture | ≥80% dari hasil yang direview |
| Critical security issues | 0 |
| Unauthorized outreach | 0 |

Target tersebut adalah ambang penerimaan awal. Setelah tersedia data penggunaan nyata, target harus dikalibrasi berdasarkan hasil evaluasi, bukan dipertahankan hanya karena tercantum di dokumen.

### Evaluasi pilot

- Apakah rekomendasi relevan?
- Apakah kedua jenis matching sama-sama berguna?
- Apakah member memahami alasan rekomendasi?
- Apakah external discovery memberikan nilai tambahan?
- Apakah data yang digunakan benar dan memiliki izin?
- Apakah rekomendasi menghasilkan tindakan yang lebih baik dibanding pencarian manual?

**Exit criteria:** MVP dinyatakan siap untuk perluasan jika seluruh critical acceptance criteria terpenuhi dan tidak ada blocker keamanan, privasi, atau integritas data.

---

# 4. Infrastructure Boundaries

## Prinsip: Infrastructure supports AI, not the other way around.

Kita tidak perlu membangun infrastruktur enterprise-scale sebelum AI Matching terbukti berguna.

### Stack yang direkomendasikan

| Layer | Teknologi | Keputusan |
|---|---|---|
| Backend | FastAPI + Python | Gunakan |
| Database | PostgreSQL | Gunakan |
| Vector Search | pgvector | Gunakan untuk MVP |
| AI Model | Gemini / Claude provider layer | Gunakan melalui adapter |
| Matching | Python + deterministic scoring | Wajib |
| RAG | Embedding + retrieval pipeline | Gunakan |
| Automation | n8n | Gunakan untuk integrasi |
| Frontend | ONE 12ELEVATE | Integrasikan |
| Cache | Redis | Opsional, saat dibutuhkan |
| Background jobs | Worker sederhana | Tambahkan jika diperlukan |
| Kubernetes | Tidak diperlukan | Tunda |
| Microservices | Tidak diperlukan di awal | Tunda |

### Batasan infrastruktur MVP

1. Gunakan satu backend modular.
2. Gunakan satu PostgreSQL instance dengan pemisahan environment.
3. Gunakan pgvector sebelum mempertimbangkan vector database terpisah.
4. Gunakan model provider abstraction agar tidak terkunci pada satu vendor.
5. Gunakan n8n untuk workflow, bukan sebagai tempat menjalankan seluruh business logic AI.
6. Gunakan asynchronous jobs hanya untuk pekerjaan yang memang membutuhkan proses background.
7. Tidak membuat microservices terpisah tanpa kebutuhan yang terukur.
8. Tidak melakukan production deployment selama validasi masih di staging.
9. Tidak membangun CRM lengkap sebagai prasyarat AI.
10. Tidak membuat custom model training sebelum ada data evaluasi yang memadai.

## Infrastruktur yang sudah tersedia dan statusnya

| Komponen | Status yang diketahui | Tindakan |
|---|---|---|
| VPS / Docker | Sudah digunakan | Audit kapasitas |
| FastAPI staging | Sudah tersedia | Pertahankan |
| PostgreSQL staging | Sudah tersedia | Gunakan sebagai data foundation |
| n8n staging | Sudah tersedia | Gunakan untuk integrasi |
| Inbound event processing | Sebagian sudah diuji | Lengkapi blocker |
| Stable browser submission IDs | Belum terverifikasi penuh | Selesaikan hanya yang kritis |
| CRM staging | Masih blocked | Jangan jadikan dependency MVP |
| ONE Member UI | Sudah ada sebagai bagian ekosistem | Integrasikan secara bertahap |
| AI Matching Engine | Belum menjadi komponen tervalidasi | Prioritas pembangunan |
| RAG Knowledge Base | Belum menjadi komponen tervalidasi | Bangun setelah scoring baseline |

Catatan: status ini mengikuti catatan pekerjaan terakhir yang tersedia. Status deployment dan kode harus diperiksa kembali sebelum Hermes melakukan perubahan.

---

# 5. Infrastructure Work That Must NOT Become the Main Project

Pekerjaan berikut tidak boleh menggeser prioritas AI:

- Mengembangkan CRM lengkap.
- Membuat dashboard operasional yang kompleks.
- Memindahkan seluruh backend ke microservices.
- Mengganti PostgreSQL tanpa alasan performa.
- Membuat vector database terpisah sebelum pgvector terbukti tidak cukup.
- Mengembangkan browser automation yang tidak memiliki use case dan sumber sah.
- Menambahkan banyak model AI tanpa benchmark.
- Melakukan refactoring besar pada production.
- Mengubah seluruh workflow n8n hanya demi menyempurnakan arsitektur.

**Aturan keputusan:** setiap pekerjaan infrastruktur harus menjawab pertanyaan, “Fitur AI mana yang tidak bisa dibangun atau diuji tanpa pekerjaan ini?”

Jika tidak ada jawaban yang konkret, pekerjaan tersebut masuk backlog.

---

# 6. AI Quality & Governance

AI tidak boleh hanya terlihat pintar. Hasilnya harus bisa dijelaskan, diuji, dan dikendalikan.

## Data governance

Setiap prospek harus memiliki:

- Unique prospect ID.
- Data source.
- Data provenance.
- Data timestamp.
- Consent / eligibility status.
- Member ownership.
- Data freshness.
- Data usage permissions.

## Matching governance

- Skor berasal dari feature dan bobot yang terdokumentasi.
- LLM tidak boleh mengubah skor secara bebas.
- Confidence tidak boleh disamakan dengan probabilitas konversi.
- Data yang tidak tersedia harus ditandai sebagai missing.
- Member dapat melihat alasan matching.
- Member memiliki keputusan akhir untuk melakukan outreach.

## Privacy and safety

- Wellness assessment bukan diagnosis medis.
- Data sensitif tidak boleh digunakan untuk menyimpulkan kondisi seseorang tanpa dasar yang sah dan persetujuan yang sesuai.
- Data eksternal tidak otomatis boleh digunakan untuk pemasaran.
- Setiap proses discovery harus mematuhi hukum dan ketentuan sumber data.
- Hak akses antar-member dan antar-tenant harus diuji.

---

# 7. Definition of Done — AI MVP

MVP hanya dinyatakan selesai apabila seluruh komponen berikut tersedia:

**AI Core**
- [ ] Customer Matching Engine berjalan.
- [ ] Business Builder Matching Engine berjalan.
- [ ] Ranking dan scoring dapat direproduksi.
- [ ] Match explanation tersedia.
- [ ] Intent confidence dan data confidence tersedia.
- [ ] Next best action tersedia.

**Prospect Discovery**
- [ ] Inbound Prospect Intelligence berjalan.
- [ ] External Prospect Discovery memiliki minimal satu sumber sah.
- [ ] Source provenance tersedia.
- [ ] Eligibility dan consent divalidasi.
- [ ] Kedua jenis prospek dapat diproses.

**Knowledge Intelligence**
- [ ] RAG knowledge base tersedia.
- [ ] AI dapat mengambil konteks edukasi relevan.
- [ ] Referensi sumber tersedia.
- [ ] RAG tidak mengubah hasil scoring.

**Member Experience**
- [ ] ONE menampilkan Customer Matches.
- [ ] ONE menampilkan Business Builder Matches.
- [ ] Member dapat memahami alasan matching.
- [ ] Member dapat memberikan feedback.
- [ ] Member dapat menentukan tindakan.

**Quality & Security**
- [ ] Precision@5 memenuhi target pilot.
- [ ] Tenant isolation lulus.
- [ ] Idempotency lulus.
- [ ] Consent dan provenance tervalidasi.
- [ ] Tidak ada critical security blocker.
- [ ] Tidak ada automatic unauthorized outreach.

---

# 8. Execution Rules for Hermes Agent

Hermes Agent harus mengikuti urutan kerja berikut.

1. Jangan mengubah tujuan produk dari AI Network Building Intelligence menjadi CRM atau webhook platform.
2. Jangan memulai dengan refactoring infrastruktur besar.
3. Kerjakan satu fase dalam satu waktu.
4. Setiap fase harus menghasilkan artefak yang dapat diperiksa.
5. Setiap implementasi harus memiliki test cases dan bukti hasil.
6. Jangan menyatakan sebuah fitur selesai hanya karena kode sudah dibuat.
7. Bedakan status `IMPLEMENTED`, `TESTED`, `VERIFIED`, `BLOCKED`, dan `NOT STARTED`.
8. Gunakan staging untuk seluruh pengembangan dan pengujian.
9. Production tetap frozen sampai ada persetujuan eksplisit.
10. Jangan mengubah proyek IngatSehat atau asetnya ketika mengerjakan 12ELEVATE.
11. Jangan membuat credential atau secret baru tanpa persetujuan.
12. Jangan melakukan external discovery melalui scraping yang melanggar ketentuan sumber.
13. Jika ada blocker, jelaskan dampaknya terhadap fitur AI dan berikan solusi minimum.
14. Jangan melanjutkan ke fase berikutnya sebelum acceptance criteria fase saat ini terpenuhi atau blocker disetujui secara eksplisit.

## Format laporan wajib setiap fase

```text
PHASE:
OBJECTIVE:
STATUS:

DELIVERABLES:
1.
2.
3.

IMPLEMENTED:
TESTED:
VERIFIED:
BLOCKED:
NOT STARTED:

ACCEPTANCE CRITERIA:
- Criterion:
- Evidence:
- Result:

INFRASTRUCTURE CHANGES:
- Component:
- Reason:
- Impact:

AI PRODUCT IMPACT:
- Customer Matching:
- Business Matching:
- Inbound Discovery:
- External Discovery:

RISKS:
NEXT RECOMMENDED ACTION:
REQUIRES APPROVAL:
```

---

# 9. Milestone Summary

| Minggu | Milestone | Hasil utama 		 |
|---	 |---	     |---	   		 |
| 1 	 | Phase 0   | PRD dan AI specifications |
| 2 	 | Phase 1   | Minimum data foundation 	 |
| 3–4 	 | Phase 2   | Dua matching engines 	 |
| 5 	 | Phase 3   | RAG knowledge intelligence |
| 6 	 | Phase 4   | Inbound prospect intelligence |
| 7–8  	 | Phase 5   | External prospect discovery |
| 9 	 | Phase 6   | ONE AI Member Copilot 	 |
| 10 	 | Phase 7   | Controlled pilot dan evaluasi |

**Prioritas tertinggi:** Phase 2 — Core AI Matching Engine. Data foundation hanya dibangun secukupnya agar fase ini dapat berjalan dan diuji.

---

# 10. Final Strategic Direction

12ELEVATE tidak sedang membangun sistem untuk sekadar mengumpulkan lebih banyak nama prospek.

12ELEVATE sedang membangun sistem yang membantu member memahami:

- Siapa yang relevan untuk didekati.
- Apa dasar kecocokannya.
- Apakah minatnya benar-benar dinyatakan.
- Informasi apa yang masih kurang.
- Edukasi apa yang paling sesuai.
- Apa langkah berikutnya yang sebaiknya dilakukan.

**Product positioning:**

> AI Network Building Intelligence — Helping Every Member Find Better Connections, Build Meaningful Relationships, and Grow Smarter Networks.

**Keputusan final:** Customer Matching dan Business Builder Matching dibangun seimbang. Inbound dan External Prospect Discovery masuk dalam MVP. AI Matching Engine menjadi prioritas teknis utama. Infrastruktur hanya dibangun sejauh mendukung kemampuan AI yang dapat diukur.

**Urutan eksekusi pertama: PHASE 0 → PHASE 1 minimum foundation → PHASE 2 AI Matching Engine.** Jangan menunggu CRM lengkap, jangan menunggu seluruh infrastruktur sempurna, dan jangan menghabiskan waktu membangun fitur yang tidak memperkuat kecerdasan matching.
