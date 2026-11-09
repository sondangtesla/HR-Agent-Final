# Decisions — HR Agent (Milestone P2M2)

Catatan keputusan teknis, alasannya, dan temuan yang memicunya. File ini menjadi bahan ADR, presentasi, dan technical interview. Task dan progress tetap dicatat di [TODO.md](TODO.md).

## Ringkasan

| ID | Topik | Status | Tanggal |
|---|---|---|---|
| K1 | Tanggal `leave-valid-008` sudah lewat | **Diputuskan** | 2026-11-06 |
| K2 | `create_hr_ticket` berjalan tanpa konfirmasi | Menunggu instruktur | 2026-11-05 |
| K3 | Aturan pengajuan minimal 3 hari kerja | **Diputuskan** | 2026-11-05 |
| K4 | Target dan jadwal pengerjaan | **Diputuskan** | 2026-11-06 |
| K5 | Kredensial model | Selesai | 2026-11-06 |
| K6 | Setup Docker ditunda ke Tahap 4 | Digantikan K7 | 2026-11-06 |
| K7 | Urutan kerja mengikuti `lab.md` | **Diputuskan** | 2026-11-06 |
| K8 | Saldo efektif saat validasi cuti | **Diputuskan** | 2026-11-09 |
| K9 | Penjaga status dan keunikan di schema `leave_requests` | **Diputuskan** | 2026-11-09 |
| K10 | Cara menyimpan token: SHA-256 tanpa salt | **Diputuskan** | 2026-11-09 |
| K11 | `proposal_id` dibuat oleh backend | **Diputuskan** | 2026-11-09 |
| K12 | Pilihan teknis schema lainnya | **Diputuskan** | 2026-11-09 |

Status yang dipakai:

- **Diputuskan:** sudah final dan menjadi acuan implementasi.
- **Menunggu instruktur:** ada rencana sementara, tetapi jawaban instruktur bisa mengubahnya.
- **Asumsi sementara:** dipakai untuk merencanakan sampai ada informasi yang pasti.
- **Selesai:** masalahnya sudah tidak ada.
- **Digantikan:** tidak berlaku lagi, tetapi tetap disimpan sebagai riwayat.

## K1 — Tanggal `leave-valid-008` sudah lewat

**Status:** Diputuskan

**Temuan:** Case hard gate ini menguji proposal cuti valid dengan tanggal 2–3 November 2026, padahal project dimulai 5 November 2026. Test membekukan “hari ini” di 23 September 2026, sedangkan evaluator memanggil server live yang memakai tanggal sebenarnya. Akibatnya, test bisa hijau tetapi proposal ditolak saat evaluasi live.

**Dampak:** Case ini hanya mensyaratkan `prepare_leave_request` dipanggil. Jika evaluator hanya mengecek tool, case lulus tanpa membuktikan proposal valid. Jika evaluator juga mengecek proposal terbentuk, hasilnya NO-GO padahal sistem berperilaku benar.

**Bukti:**

- [data/evaluation_cases.json:9](data/evaluation_cases.json:9)
- [tests/conftest.py:60](tests/conftest.py:60)
- [assessment.md:8](assessment.md:8)

**Opsi:**

| Opsi | Kelebihan | Kekurangan |
|---|---|---|
| Ubah tanggal di `data/evaluation_cases.json` | Paling sederhana | `data/` adalah artefak yang disediakan, dan tanggal baru akan kedaluwarsa lagi |
| Tambah override tanggal di server | Input case tetap utuh | Menambah jalur pengubah waktu di kode aplikasi |
| Evaluator mengganti tanggal saat berjalan | `data/` dan server tidak berubah | Input berbeda dari file, jadi harus dicatat di report |

**Keputusan:** Evaluator mengganti tanggal case ini saat berjalan ke hari kerja mendatang yang lolos aturan K3, dan penggantiannya dicatat di report.

**Alasan:** Tanggal yang ditulis tetap di file akan kedaluwarsa lagi, sedangkan tanggal penilaian belum diketahui. Opsi ini juga tidak mengubah artefak yang disediakan dan tidak menambah perilaku khusus di server.

**Risiko:** Belum dikonfirmasi instruktur. Grader yang memakai evaluatornya sendiri tetap bisa melihat tanggal lama, jadi penggantian ini perlu disebut di report.

## K2 — `create_hr_ticket` berjalan tanpa konfirmasi

**Status:** Menunggu instruktur

**Temuan:** Membuat tiket menambah baris baru di database, dan model bisa memanggil tool ini langsung. Rubric melarang side effect tanpa konfirmasi eksplisit, tetapi endpoint konfirmasi hanya mendukung `leave_request`.

**Dampak:** Tool ini wajib menurut brief, tetapi bisa dianggap melanggar hard gate. Pelanggaran hard gate membuat nilai maksimum 69.

**Bukti:**

- [brief.md:27](brief.md:27)
- [rubric.md:21](rubric.md:21)
- [src/contracts.py:51](src/contracts.py:51)

**Opsi:**

| Opsi | Kelebihan | Kekurangan |
|---|---|---|
| Tiket hanya dibuat bila diminta jelas oleh pengguna | Kontrak API tidak berubah | Masih belum melewati tombol konfirmasi |
| Tambah alur konfirmasi untuk tiket | Paling ketat | Harus mengubah kontrak yang disediakan dan UI |
| Hapus tool | Tidak ada side effect | Melanggar brief |

**Rencana sementara:** Tiket hanya dibuat bila diminta jelas oleh pengguna, ringkasannya disamarkan, dan risikonya dicatat di risk register.

**Alasan:** Opsi ini memenuhi brief tanpa mengubah kontrak, dan membatasi dampaknya. Aturan ini harus ditegakkan dan diuji di backend, bukan hanya di prompt.

**Catatan:** Konfirmasi berarti pengguna sendiri menekan tombol. Ini berbeda dari validasi Python, yang hanya memeriksa kebenaran isi data dan tidak bisa mengetahui apakah pengguna memang menginginkan tindakan itu.

**Yang ditanyakan ke instruktur:** Apakah membuat tiket termasuk side effect yang wajib dikonfirmasi?

## K3 — Aturan pengajuan minimal 3 hari kerja

**Status:** Diputuskan

**Temuan:** Kebijakan cuti tahunan mewajibkan pengajuan paling lambat tiga hari kerja sebelum tanggal mulai, tetapi aturan ini tidak ada di daftar validasi brief dan lab.

**Bukti:**

- [data/policies/annual-leave.md:13](data/policies/annual-leave.md:13)
- [brief.md:29](brief.md:29)
- [lab.md:124](lab.md:124)

**Keputusan:** Aturan ditambahkan ke `validate_leave_request`, khusus cuti tahunan.

**Alasan:**

- Agent bisa menjelaskan aturan ini kepada pegawai, jadi sistem harus berperilaku sama.
- Aturan ini hanya tertulis di dokumen cuti tahunan.
- Cuti sakit tidak bisa direncanakan tiga hari sebelumnya.

**Alternatif yang ditolak:**

- Tidak menerapkan aturan: jawaban agent dan perilaku sistem bisa berbeda.
- Menerapkan ke semua tipe cuti: melampaui isi kebijakan.

**Risiko:** Bisa bertabrakan dengan hidden test yang memakai cuti tahunan kurang dari tiga hari kerja sebelum tanggal mulai. Mitigasinya, beri tahu instruktur.

**Bukti pelaksanaan:** Belum ada. Test baru direncanakan di Step 5.

## K4 — Target dan jadwal pengerjaan

**Status:** Diputuskan

**Temuan:** Deadline pengumpulan adalah 20 November 2026. Waktu yang tersedia sampai 13 November adalah 3 jam pada Senin 9 November dan sekitar 2 jam per hari pada 10–13 November, total sekitar 11 jam.

**Keputusan:** Pada 13 November, chat dan saldo ditargetkan berjalan lewat Streamlit dengan PostgreSQL dan model asli. Seluruh sistem ditargetkan selesai 15 November. Waktu 16–19 November dipakai untuk cadangan, review, dan latihan presentasi Bahasa Inggris.

**Alasan:** Urutan `lab.md` menaruh evaluasi dan Docker di akhir, jadi keduanya tidak realistis selesai pada 13 November (lihat K7). Jarak sampai deadline menjadi cadangan jika target meleset.

**Risiko:** Durasi tiap step masih perkiraan, dan jadwal 14–15 November padat. Jika meleset, 16–17 November dipakai lebih dulu, lalu waktu latihan berkurang.

## K5 — Kredensial model

**Status:** Selesai

**Temuan:** API key dan nama model sudah dimiliki, tetapi file `.env` belum dibuat.

**Keputusan:** `AGENT_MODEL` dan `EMBEDDING_MODEL` dilengkapi di Step 3, sebelum indexing.

**Risiko:** Mengisi `.env` saja tidak cukup. `OpenAIProvider` tetap harus ditulis, dan kualitas retrieval serta perilaku model asli baru bisa diuji setelah tersambung. Waktunya sudah dijadwalkan di Step 3 dan Step 6.

## K6 — Setup Docker ditunda ke Tahap 4

**Status:** Digantikan K7. Label Tahap di entri ini mengacu ke rencana lama.

**Temuan:** Plan awal menyiapkan Docker, PostgreSQL, Redis, dan `.env` di Tahap 1, padahal test Tahap 1–3 memakai `MemoryRepository`, `NullCache`, dan model tiruan.

**Bukti:** [tests/conftest.py:19-63](tests/conftest.py:19)

**Opsi:**

| Opsi | Kelebihan | Kekurangan |
|---|---|---|
| Setup lengkap di Tahap 1 | Lingkungan langsung lengkap | Memakai waktu untuk hal yang belum dibutuhkan |
| Setup minimal, Docker di Tahap 4 | Waktu Tahap 1 fokus ke kode, dan test tetap bisa jalan | Masalah Docker baru terlihat di Tahap 4 |
| Semua setup di akhir | Paling cepat mulai menulis kode | Tanpa pytest kode tidak bisa diuji, dan kegagalan Docker baru terlihat mendekati deadline |

**Keputusan:** `.venv` dan git disiapkan di Tahap 1. Docker Desktop, `.env`, PostgreSQL, dan Redis disiapkan di Tahap 4.

**Alasan:** Test sudah memberi umpan balik tanpa infrastruktur. Docker baru dibutuhkan saat kode mulai memakai database, tetapi tetap cukup awal untuk diperbaiki sebelum deadline.

**Risiko:** Masalah Docker baru terlihat di Tahap 4. Mitigasinya, uji pengiriman Docker tetap dijadwalkan di Tahap 5, bukan Tahap 7.

**Pembaruan (6 Nov 2026):** Docker Desktop, PostgreSQL, dan Redis ternyata siap lebih awal. `.env` belum lengkap, karena `AGENT_MODEL` dan `EMBEDDING_MODEL` masih kosong.

## K7 — Urutan kerja mengikuti `lab.md`

**Status:** Diputuskan

**Temuan:** `lab.md` memulai implementasi dari database dan seed. Rencana sebelumnya memulai dari `domain.py`, `security.py`, dan `MemoryRepository`.

**Bukti:**

- [lab.md:96](lab.md:96)
- [src/repository.py:1](src/repository.py:1)
- [tests/conftest.py:19-63](tests/conftest.py:19)

**Opsi:**

| Opsi | Kelebihan | Kekurangan |
|---|---|---|
| Inti logika lebih dulu | Test langsung memberi umpan balik, dan desain tabel lebih jelas | Berbeda dari urutan lab, dan database baru disentuh belakangan |
| Mengikuti `lab.md` | Sesuai checkpoint mentor, dan bekerja dengan data sungguhan dari awal | Sebagian kerja awal belum punya test otomatis, dan alur utuh baru terlihat belakangan |

**Keputusan:** Urutan kerja mengikuti Step 1–11 di `lab.md`.

**Alasan:** Ini jalur yang dirancang mentor, dan checkpoint-nya bisa langsung dipakai sebagai ukuran progres. Docker juga sudah siap, jadi tidak ada hambatan untuk mulai dari database.

**Risiko:**

- Step 2–4 lebih banyak diverifikasi manual, jadi perlu perintah pengecekan sendiri.
- `MemoryRepository` tetap wajib dibuat karena test bergantung padanya.
- Evaluasi dan Docker baru dikerjakan di akhir, jadi target sistem utuh bergeser dari 13 ke 15 November.

**Pembaruan (6 Nov 2026):** Project brief, ADR, dan diagram juga mengikuti lab, yaitu dikerjakan di Step 1 sebelum database.

## K8 — Saldo efektif saat validasi cuti

**Status:** Diputuskan

**Temuan:** Request yang masih pending tidak mengurangi saldo di database, karena asisten dilarang mengubah saldo. Akibatnya, beberapa request pending bisa melebihi saldo. Contoh: saldo cuti tahunan Alya 8 hari, request A 5 hari masih pending, lalu request B 5 hari tetap lolos karena dicek terhadap 8.

**Bukti:**

- [data/policies/escalation.md:13](data/policies/escalation.md:13)
- [brief.md:29](brief.md:29)

**Opsi:**

| Opsi | Kelebihan | Kekurangan |
|---|---|---|
| Dibiarkan, manajer yang menangkap | Paling sederhana | Pegawai baru tahu salah setelah ditolak |
| Tool kelima untuk menghitung saldo efektif | Logikanya terlihat jelas sebagai tool | Brief membatasi empat tool, dan model bisa lupa memanggilnya |
| Hitung saldo efektif di dalam validasi | Selalu berjalan, tidak bergantung pada keputusan model | Validasi butuh data request pending |

**Keputusan:** Saat `prepare_leave_request` memvalidasi, saldo efektif = saldo di database − total hari request `pending_manager_review` dengan tipe cuti yang sama.

- Saldo di database tidak berubah. Ini hanya perhitungan.
- Request `approved` tidak dihitung, karena sudah mengurangi saldo di sistem HR.
- Request `cancelled` dan proposal yang belum dikonfirmasi tidak dihitung.

**Alasan:** Pengaman tidak boleh bergantung pada keputusan model. Di dalam validasi, perhitungan ini selalu berjalan setiap kali proposal dibuat, dan tidak menambah tool di luar kontrak brief.

**Cek ulang saat konfirmasi:** Saldo efektif dihitung lagi di dalam transaksi konfirmasi, karena daftar request pending bisa berubah sejak proposal dibuat. Tanpa ini, dua proposal yang dibuat sebelum salah satunya dikonfirmasi tetap bisa sama-sama lolos.

**Tampilan saldo:** `get_my_leave_balance` mengembalikan saldo di database, total hari pending, dan saldo efektif per tipe cuti. Rincian ini membuat agent bisa menjelaskan kenapa saldo yang bisa diajukan lebih kecil, misalnya “8 hari, 5 hari sedang menunggu manajer, jadi bisa diajukan 3 hari.” Kontrak `LeaveBalance` di `src/contracts.py` tidak diubah, karena hasil tool tidak harus memakai model itu.

## K9 — Penjaga status dan keunikan di schema `leave_requests`

**Status:** Diputuskan

**Temuan:** Asisten hanya boleh menulis `pending_manager_review`. Tetapi `data/historical_requests.json` berisi `approved` dan `cancelled`, yang di dunia nyata ditulis oleh sistem HR. Jika constraint `status` hanya mengizinkan `pending_manager_review`, data historis tidak bisa di-seed. Jika ketiga status diizinkan tanpa penjaga lain, bug di kode bisa membuat `approved` (hard gate).

**Bukti:**

- [data/historical_requests.json](data/historical_requests.json)
- [brief.md:7](brief.md:7)

**Opsi:**

| Opsi | Bisa menahan | Kekurangan |
|---|---|---|
| A. Kode + test saja | Kesalahan logika di kode | Database menerima `approved` jika ada bug |
| B. Kolom penanda penulis + CHECK | Bug di kode (database ikut menolak) | Tidak menahan penyerang yang menguasai aplikasi |
| C. Role database terpisah untuk asisten dan sistem HR | Bug dan penyerang | Sistem HR di luar scope; Compose hanya punya satu user database |

**Keputusan:** A + B. C dicatat sebagai production gap.

- Status yang diizinkan: `pending_manager_review`, `approved`, `cancelled`.
- Kolom `status_set_by` (`assistant`, `hr_system`, `seed`) mencatat siapa yang **terakhir mengubah status**. CHECK: jika `status_set_by = 'assistant'`, status wajib `pending_manager_review`.
- Kolom ini sengaja tidak bernama `created_by`. Kalau penandanya “siapa yang membuat baris”, sistem HR tidak akan bisa menyetujui request yang dibuat asisten, karena barisnya tetap tercatat `assistant` dan CHECK akan menolak `approved`.
- Kolom `policy_version` mencatat versi kebijakan yang dipakai saat validasi, misalnya `HR-LEAVE-001@2.1`. Kolom ini wajib terisi untuk proposal dan untuk request dari asisten. Request historis boleh kosong karena versinya tidak diketahui.
- `UNIQUE(employee_id, idempotency_key)`: key milik dua pegawai berbeda tidak saling bertabrakan.
- `UNIQUE(proposal_id)`: lapis terakhir jika row lock di kode konfirmasi ternyata salah. Satu proposal paling banyak menjadi satu request.

**Alasan:** Pengaman pertama ada di kode, dan pengaman terakhir ada di database. Bug di salah satu lapis tidak langsung menjadi pelanggaran hard gate.

**Risiko:** Status `rejected` belum ada karena tidak muncul di data. Jika sistem HR memakainya, constraint perlu ditambah.

**Bukti implementasi (9 Nov 2026):** Sembilan uji constraint dijalankan di transaksi yang di-rollback, dan semuanya sesuai harapan. Asisten yang menulis `approved` ditolak oleh `assistant_writes_only_pending`. Sistem HR yang menyetujui request buatan asisten diterima. Proposal yang dikonfirmasi dua kali ditolak oleh `UNIQUE(proposal_id)`.

## K10 — Cara menyimpan token: SHA-256 tanpa salt

**Status:** Diputuskan

**Temuan:** Token tidak boleh disimpan apa adanya. Tetapi saat request masuk, backend harus bisa mencari pegawai berdasarkan token. Karena itu, fungsi hash-nya harus menghasilkan nilai yang sama setiap kali, termasuk setelah server restart.

**Bukti:** `hash('token-alya')` bawaan Python dijalankan di dua proses terpisah dan menghasilkan dua angka berbeda (hash randomization). `token_hash('token-alya')` menghasilkan hex 64 karakter yang sama di kedua proses.

**Opsi:**

| Opsi | Kelebihan | Kekurangan |
|---|---|---|
| `hash()` bawaan Python | Tidak perlu import | Berubah setiap proses, jadi semua login gagal setelah restart |
| SHA-256 tanpa salt | Deterministik, bisa dicari dengan index, cepat | Token yang mudah ditebak bisa dicoba satu per satu |
| HMAC-SHA256 dengan secret di server | Deterministik, dan hash curian tidak bisa dicocokkan tanpa secret | Ada secret tambahan yang harus dikelola |
| bcrypt atau argon2 dengan salt | Standar untuk password | Salt acak membuat pencarian berdasarkan hash tidak mungkin |

**Keputusan:** `hashlib.sha256(token.encode("utf-8")).hexdigest()`, sesuai TODO di starter.

**Alasan:** Token di sistem sungguhan berupa string acak yang panjang, sehingga tidak bisa ditebak walaupun hash-nya cepat. Bcrypt dirancang untuk password buatan manusia yang pendek.

**Risiko:** Token demo seperti `token-alya` mudah ditebak. Ini sudah tercatat di Production Gaps poin 1 (Login). Di production, HMAC dengan secret server bisa ditambahkan sebagai lapisan berikutnya.

## K11 — `proposal_id` dibuat oleh backend

**Status:** Diputuskan

**Temuan:** `proposal_id` dipakai di URL konfirmasi dan disalin ke `leave_requests.proposal_id`. Jika nilainya berasal dari model atau dari pengguna, ID bisa dikarang atau ditebak.

**Bukti:** [ui_contract.py:11](ui_contract.py:11) memakai `{proposal_id}` di path konfirmasi, dan [brief.md:44](brief.md:44) meminta proposal milik orang lain menghasilkan 404.

**Keputusan:**

- `prepare_leave_request` membuat `proposal_id` dengan `uuid4` setelah validasi lolos.
- Model tidak pernah mengirim `proposal_id`. Pengguna hanya mengembalikan ID yang sebelumnya diberikan backend.
- Endpoint konfirmasi tetap mengecek pemilik proposal. Jika bukan milik pemilik token, hasilnya 404.

**Alasan:** ID acak tidak bisa ditebak, dan pengecekan pemilik tetap menjadi penjaga utama. Model tidak dipercaya untuk membuat identitas apa pun (lihat tabel trust boundary di `templates/architecture.md`).

**Risiko:** Prefix ID (misalnya `PROP-`) belum ditentukan. Tentukan di Step 5 dan pakai secara konsisten.

## K12 — Pilihan teknis schema lainnya

**Status:** Diputuskan

| Pilihan | Alasan | Trade-off |
|---|---|---|
| Full-text memakai konfigurasi `simple` | PostgreSQL tidak punya konfigurasi Bahasa Indonesia | Tanpa stemming: “mengajukan” dan “ajukan” dianggap kata berbeda. Kelemahan ini dibantu oleh pencarian vector. |
| Kolom `search` berupa `tsvector GENERATED ... STORED` + index GIN | Selalu sinkron dengan `content` tanpa kode tambahan | Butuh ruang penyimpanan sedikit lebih besar |
| Belum ada index vector (HNSW/IVFFlat) | Korpus hanya puluhan chunk, jadi scan penuh cukup cepat dan hasilnya exact | Perlu ditambahkan jika dokumen bertambah banyak |
| Dimensi `embedding` dari `Settings.embedding_dimensions` | Mengganti model embedding cukup lewat `.env` | Nilai ini masuk ke DDL lewat `format`. Aman karena bertipe `int` dan divalidasi 64–4096, tidak pernah berasal dari input pengguna. |
| `embedding` boleh kosong | Schema dan seed identitas bisa berjalan sebelum API key dan model diisi | Retrieval vector harus mengabaikan baris tanpa embedding |
| Constraint penting diberi nama | Log error langsung menunjukkan aturan yang dilanggar, misalnya `assistant_writes_only_pending` | Tidak ada |
| `CREATE ... IF NOT EXISTS` | Schema aman dijalankan berkali-kali | Tidak mengubah tabel yang sudah ada (lihat T6) |

## Temuan kecil

Temuan berikut tidak memerlukan keputusan besar.

| ID | Temuan | Tindak lanjut |
|---|---|---|
| T1 | Master prompt menyebut `submission_checklist.md`, sedangkan nama file sebenarnya `submission-checklist.md`. | Pakai nama file sebenarnya. |
| T2 | README dan `docker-delivery.md` menyebut folder `participant/`, sedangkan isi folder itu berada di root workspace. | Jalankan perintah dari root workspace. |
| T3 | Workspace belum menjadi git repository, padahal grader memakai checkout bersih. | Selesai: baseline commit `754e288`. |
| T4 | Nama `brief.md` dan `templates/project-brief.md` mirip, padahal isinya berbeda. `brief.md` adalah soal dari mentor, sedangkan `templates/project-brief.md` adalah jawaban kita. | `brief.md` tidak diubah. |
| T5 | Docker Desktop yang sudah hidup tidak otomatis menjalankan container. | Awal setiap sesi: `docker compose up -d postgres redis`, lalu cek status `healthy`. |
| T6 | `CREATE TABLE IF NOT EXISTS` tidak mengubah tabel yang sudah ada. Perubahan schema tidak akan berlaku tanpa menghapus tabel. Pada 9 Nov, tujuh tabel yang masih kosong dihapus manual setelah constraint diberi nama. | `--reset` di task seed harus menghapus lalu membuat ulang semua tabel. |
| T7 | `ActionProposal` di `src/contracts.py` tidak punya field `policy_version`, padahal kolomnya wajib di `action_proposals` (K9). `contracts.py` tidak boleh diubah. | Tentukan sumber nilainya di Step 5, misalnya konstanta versi aturan di `src/domain.py`. |
| T8 | Package Python `pgvector` tidak ada di `requirements.txt`. | Di Step 3, kirim embedding sebagai teks `'[0.1,0.2,...]'` lalu cast ke `vector` di SQL. |
| T9 | Diagram menyatakan `/readyz` tidak `ready` saat PostgreSQL mati. Ini masih asumsi. | Verifikasi di Step 7. |
| T10 | Sembilan uji constraint K9 baru ada sebagai script sementara di scratchpad, belum menjadi test di repo. | Pindahkan ke test di Step 8. |
| T11 | `.claude/settings.local.json` ter-track git. Isinya daftar izin tool lokal, termasuk path folder pribadi, dan berubah di setiap sesi. | Selesai 9 Nov: masuk `.gitignore` dan dikeluarkan dengan `git rm --cached`. File lokal tetap ada. Versi lama masih tersimpan di riwayat commit sebelumnya, tetapi isinya hanya izin tool dan path, bukan secret. |

## Format entri baru

Salin format ini untuk setiap keputusan baru:

```markdown
## K<nomor> — <judul>

**Status:** Diputuskan | Menunggu instruktur | Asumsi sementara

**Temuan:** Apa masalahnya.

**Bukti:** File dan baris, test, atau trace.

**Opsi:** Alternatif beserta trade-off.

**Keputusan:** Apa yang dipilih.

**Alasan:** Kenapa opsi ini dipilih.

**Risiko:** Apa yang bisa salah dan bagaimana mengatasinya.
```
