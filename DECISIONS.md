# Decisions — HR Agent (Milestone P2M2)

Catatan keputusan teknis, alasannya, dan temuan yang memicunya. File ini menjadi bahan ADR, presentasi, dan technical interview. Task dan progress tetap dicatat di [TODO.md](TODO.md).

## Ringkasan

| ID | Topik | Status | Tanggal |
|---|---|---|---|
| K1 | Tanggal `leave-valid-008` sudah lewat | Menunggu instruktur | 2026-11-05 |
| K2 | `create_hr_ticket` berjalan tanpa konfirmasi | Menunggu instruktur | 2026-11-05 |
| K3 | Aturan pengajuan minimal 3 hari kerja | **Diputuskan** | 2026-11-05 |
| K4 | Waktu pengerjaan per hari | Asumsi sementara | 2026-11-05 |
| K5 | Kredensial model belum tersedia | Menunggu instruktur | 2026-11-05 |

Status yang dipakai:

- **Diputuskan:** sudah final dan menjadi acuan implementasi.
- **Menunggu instruktur:** ada rencana sementara, tetapi jawaban instruktur bisa mengubahnya.
- **Asumsi sementara:** dipakai untuk merencanakan sampai ada informasi yang pasti.

## K1 — Tanggal `leave-valid-008` sudah lewat

**Status:** Menunggu instruktur

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

**Rencana sementara:** Evaluator mengganti tanggal case ini ke hari kerja mendatang yang lolos aturan K3, dan penggantiannya dicatat di report.

**Alasan:** Opsi ini tidak mengubah artefak yang disediakan dan tidak menambah perilaku khusus di server.

**Yang ditanyakan ke instruktur:** Apakah evaluator boleh mengganti tanggal case ini, atau ada tanggal lain yang harus dipakai?

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

**Bukti pelaksanaan:** Belum ada. Test baru direncanakan di Hari 1.

## K4 — Waktu pengerjaan per hari

**Status:** Asumsi sementara

**Temuan:** Master prompt hanya menyebut 2 jam untuk sesi hari ini. Waktu untuk Hari 2–7 dan deadline belum diketahui.

**Asumsi:** 2 jam per hari selama 7 hari, atau 14 jam total.

**Alasan:** Ini angka paling konservatif yang tersedia. Roadmap perlu disusun ulang jika waktunya berbeda.

## K5 — Kredensial model belum tersedia

**Status:** Menunggu instruktur

**Temuan:** File `.env` belum ada. `OPENAI_API_KEY`, `AGENT_MODEL`, `EMBEDDING_MODEL`, dan `EMBEDDING_DIMENSIONS` harus berasal dari instruktur.

**Dampak:** Hari 1–3 tetap bisa berjalan dengan `DeterministicProvider`. Mulai Hari 4, indexing dan alur model sungguhan membutuhkan kredensial ini.

**Rencana sementara:** Kredensial diminta paling lambat Hari 3.

## Temuan kecil

Temuan berikut tidak memerlukan keputusan besar.

| ID | Temuan | Tindak lanjut |
|---|---|---|
| T1 | Master prompt menyebut `submission_checklist.md`, sedangkan nama file sebenarnya `submission-checklist.md`. | Pakai nama file sebenarnya. |
| T2 | README dan `docker-delivery.md` menyebut folder `participant/`, sedangkan isi folder itu berada di root workspace. | Jalankan perintah dari root workspace. |
| T3 | Workspace belum menjadi git repository, padahal grader memakai checkout bersih. | `git init` di Hari 1. |

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
