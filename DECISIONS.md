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

## Temuan kecil

Temuan berikut tidak memerlukan keputusan besar.

| ID | Temuan | Tindak lanjut |
|---|---|---|
| T1 | Master prompt menyebut `submission_checklist.md`, sedangkan nama file sebenarnya `submission-checklist.md`. | Pakai nama file sebenarnya. |
| T2 | README dan `docker-delivery.md` menyebut folder `participant/`, sedangkan isi folder itu berada di root workspace. | Jalankan perintah dari root workspace. |
| T3 | Workspace belum menjadi git repository, padahal grader memakai checkout bersih. | Selesai: baseline commit `754e288`. |

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
