# Hasil uji proposal skema consent/audit (LOKAL, bukan staging)

- Database: PostgreSQL lokal sementara (embedded binary), port 54329, cluster baru. Bukan staging, bukan VPS, bukan production.
- Skema: `consent_audit_schema.PROPOSAL.sql`. Belum diterapkan ke mana pun.
- Data: sintetis saja.

## Hasil (putaran kedua, setelah trigger approved-notice ditambahkan)
| Uji | Hasil yang diharapkan | Hasil |
|---|---|---|
| GRANTED dengan notice DRAFT | ditolak | ditolak |
| GRANTED dengan notice APPROVED tetapi purpose berbeda | ditolak | ditolak |
| GRANTED dengan notice APPROVED dan purpose cocok | diterima | diterima |
| WITHDRAWN | diterima | diterima |
| purpose matching_business | ditolak | ditolak |
| UPDATE / DELETE / TRUNCATE consent | ditolak | ditolak |
| UPDATE / DELETE audit | ditolak | ditolak |
| hash duplikat | ditolak | ditolak |
| baris audit setelah percobaan ubah | utuh | utuh |

## Temuan putaran pertama (diperbaiki)
- GRANTED dengan notice DRAFT **diterima** database. Aturan itu hanya ada di Python. Ditambahkan trigger `ai_require_approved_notice`.
- Tes UPDATE audit pada putaran pertama tidak valid, karena dijalankan saat tabel audit masih kosong. Diulang dengan baris yang sudah ada.

## Yang belum diuji
- Hak akses role aplikasi (GRANT/REVOKE): skema placeholder, belum dibuat role-nya.
- Kinerja pada volume besar.
- Retensi dan penghapusan: belum diputuskan secara hukum.
