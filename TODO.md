# TODO — HR Agent (Milestone P2M2)

Panduan kerja utama. Kerjakan satu task pada satu waktu, centang sesudah **Done when** terbukti.

Urutan kerja mengikuti Step 1–11 di [lab.md](lab.md) (keputusan K7).

- **Mulai:** Kamis, 5 November 2026
- **Target internal:** chat dan saldo berjalan lewat Streamlit pada 13 November; seluruh sistem selesai pada 15 November 2026.
- **Deadline pengumpulan:** 20 November 2026.
- **Status saat ini:** Step 1 selesai (Checkpoint 1), kecuali peta failure yang ditunda. Implementasi belum dimulai.
- **Task berikutnya:** seed idempotent dan `--reset` di `src/setup_lab.py` (Step 2).

## Target rilis

| Syarat | Target |
|---|---:|
| Hard gates | 100% |
| Overall pass rate | ≥ 80% |
| Retrieval recall@3 | ≥ 80% |
| Citation validity | 100% |
| Leave request `approved` buatan sistem | 0 |

**Nilai maksimum 69** jika terjadi salah satu: bisa membaca data pegawai lain, ada status `approved`, side effect tanpa konfirmasi, API key/data nyata masuk repo/trace, atau tidak ada evaluation evidence yang bisa dijalankan.

## Keputusan terbuka

Isi kolom keputusan sebelum mengerjakan task terkait. Alasan lengkap dan opsi yang dipertimbangkan ada di [DECISIONS.md](DECISIONS.md).

| ID | Masalah | Rekomendasi sementara | Keputusan |
|---|---|---|---|
| K1 | `leave-valid-008` (hard gate) memakai 2–3 Nov 2026, yang sudah lewat. Test membekukan tanggal di 23 Sep 2026, sedangkan server live memakai tanggal sebenarnya. | `data/` tidak diubah. Evaluator mengganti tanggal saat berjalan ke hari kerja mendatang yang lolos aturan K3, lalu mencatatnya di report. | **Tanggal diganti** (6 Nov 2026). Belum dikonfirmasi instruktur. |
| K2 | `create_hr_ticket` menulis ke database tanpa konfirmasi, padahal rubric melarang side effect tanpa konfirmasi eksplisit. Endpoint confirm hanya mendukung `leave_request`. | Tanya instruktur. Jika tidak ada jawaban: tiket hanya dibuat bila diminta jelas oleh pengguna, ringkasannya disamarkan, dan alasannya dicatat di risk register. | |
| K3 | Kebijakan `HR-LEAVE-001` mewajibkan pengajuan minimal 3 hari kerja sebelumnya, tetapi aturan ini tidak ada di daftar validasi lab/brief. | Terapkan agar jawaban dan perilaku sistem konsisten. Risiko: bisa bertabrakan dengan hidden test. | **Diterapkan** (5 Nov 2026), khusus cuti tahunan. Beri tahu instruktur. |
| K4 | Waktu pengerjaan terbatas. | Ikuti tabel Jadwal. | **Diputuskan** (6 Nov 2026): Senin 3 jam, Selasa–Jumat sekitar 2 jam per hari. |
| K5 | `.env` sudah ada, tetapi `AGENT_MODEL` dan `EMBEDDING_MODEL` masih kosong. | Lengkapi di Step 3, sebelum indexing. | **Selesai** (6 Nov 2026): kredensial tersedia. |
| K7 | Urutan kerja: `lab.md` atau inti logika lebih dulu. | Inti logika lebih dulu, kecuali mentor mengecek checkpoint sesuai urutan lab. | **Ikuti `lab.md`** (6 Nov 2026). |
| K8 | Request pending tidak mengurangi saldo, jadi total request pending bisa melebihi saldo. | Hitung saldo efektif di dalam validasi, lalu cek ulang saat konfirmasi. | **Diputuskan** (9 Nov 2026): saldo efektif di validasi, cek ulang saat konfirmasi, dan rincian saldo di `get_my_leave_balance`. |

## Jadwal

**Target 13 November:** chat dan saldo berjalan lewat Streamlit dengan PostgreSQL dan model asli (Checkpoint 3).

**Target 15 November:** seluruh sistem selesai, termasuk konfirmasi, evaluasi, dan Docker.

Sisa kerja masih perkiraan, jadi Sabtu dan Minggu 7–8 November adalah bonus. Jadwal 14–15 November padat; jika meleset, 16–17 November menjadi cadangan.

| Tanggal | Waktu | Step | Hasil akhir sesi |
|---|---|---|---|
| Sabtu–Minggu, 7–8 Nov | Bonus | Step 1 | Project brief, ADR, dan draft diagram. |
| Senin, 9 Nov | 3 jam, 04:00–07:00 | Step 1–2 | Sisa Step 1, lalu schema dan seed. |
| Selasa, 10 Nov | 2 jam | Step 2–3 | `PostgresRepository` dasar dan dokumen kebijakan ter-index ke pgvector. |
| Rabu, 11 Nov | 2 jam | Step 4 | Hybrid retrieval bekerja, Checkpoint 2 lulus. |
| Kamis, 12 Nov | 2 jam | Step 5 | Aturan cuti, penyamaran, dan empat tool selesai. |
| Jumat, 13 Nov | 2 jam | Step 6–7 | Agent dan API dasar jalan, Checkpoint 3 lulus. |
| Sabtu–Minggu, 14–15 Nov | Fleksibel | Step 8–11 | Konfirmasi, telemetry, evaluator, monitoring, Docker. |
| Senin–Kamis, 16–19 Nov | Fleksibel | Finalisasi | Cadangan, dokumen, review, latihan presentasi Bahasa Inggris. |
| Jumat, 20 Nov | | | Pengumpulan. |

Jika tertinggal, potong stretch goal dan polish lebih dulu. Jangan potong hard gate, evaluator, atau Docker.

## Rencana Senin, 9 November (04:00–07:00)

| Waktu | Aktivitas | Output |
|---|---|---|
| 04:00–04:10 | Baca `TODO.md`, hidupkan Docker Desktop, cek `postgres` dan `redis`. | Siap mulai. |
| 04:10–04:50 | Selesaikan sisa Step 1: project brief, ADR, dan draft diagram. | Checkpoint 1 terpenuhi. |
| 04:50–05:05 | `token_hash`. | Hash stabil untuk token yang sama. |
| 05:05–05:50 | Schema di `src/setup_lab.py`: extension `vector`, tujuh tabel, status constraint. | Semua tabel terbentuk. |
| 05:50–06:00 | Istirahat. | |
| 06:00–06:45 | Seed idempotent dan opsi `--reset`. | Seed dua kali tidak menduplikasi data. |
| 06:45–07:00 | Commit, centang TODO, catat blocker. | Sesi tertutup. |

Jika Step 1 sudah selesai saat akhir pekan, waktu sisanya dipakai untuk `PostgresRepository` dasar.

# Sesi Lab 1 — Scope, data, dan retrieval

## Step 1 — Preflight dan desain

- [x] **Setup Python.** Done when: `.venv` aktif dan dependency terpasang. Terbukti: pytest 8.4.2 berjalan.
- [x] **`git init` dan commit awal.** Done when: `git status` bersih dan `.env` tidak ter-track. Terbukti: commit `754e288`.
- [x] **Setup Docker.** Done when: `postgres` dan `redis` keduanya `healthy`. Terbukti pada 6 Nov 2026.
- [x] **Preflight test.** Done when: hasil awal dicatat. Terbukti: 4 passed, 12 failed, 5 errors, 1 deselected.
- [ ] **Peta failure per TODO (ditunda).** Done when: tiap failure dipetakan ke modul penyebabnya.
- [x] **`templates/project-brief.md`.** Done when: semua heading terisi dengan kata-katamu sendiri.
- [x] **ADR di `templates/architecture.md`.** Done when: keputusan, konteks, alternatif, trade-off, dan production follow-up terisi.
- [x] **Draft diagram trust boundary.** Done when: Checkpoint 1 terpenuhi (identity flow, confirmation boundary, telemetry, cache degradation, failure path).

## Step 2 — Database dan seed

- [x] **`token_hash` di `src/security.py`.** Done when: token yang sama selalu menghasilkan SHA-256 hex yang sama. Terbukti: dua proses terpisah menghasilkan hash 64 karakter yang sama.
- [x] **Schema di `src/setup_lab.py`.** Done when: extension `vector` aktif; tabel employee, balance, request, proposal, ticket, policy chunk, dan trace terbentuk; status ber-constraint. Terbukti 9 Nov: 7 tabel + `vector` 0.8.7, dijalankan 2x tanpa error, 9 uji constraint K9 sesuai harapan.
- [ ] **Seed idempotent.** Done when: `python -m src.setup_lab` dua kali tidak menduplikasi data, dan `--reset` tersedia. Token tersimpan sebagai hash. `--reset` menghapus lalu membuat ulang semua tabel, karena `IF NOT EXISTS` tidak mengubah tabel lama (T6). Data historis memakai `status_set_by = 'seed'` (K9).
- [ ] **`PostgresRepository` dasar.** Done when: pool, `health`, `authenticate`, dan `get_balances` bekerja tanpa interpolasi input ke SQL.

Pertanyaan pemandu:

- Kenapa token disimpan sebagai hash? Kenapa SHA-256 polos cukup untuk token demo, tetapi tidak cocok untuk password?
- `data/historical_requests.json` memuat status `approved` dan `cancelled`. Apa dampaknya pada status constraint, dan bagaimana sistem tetap tidak bisa membuat `approved`?
- Apa yang membuat seed aman dijalankan dua kali?

## Step 3 — Policy indexing

- [ ] **Lengkapi `.env`.** Done when: `AGENT_MODEL` dan `EMBEDDING_MODEL` terisi, dan `EMBEDDING_DIMENSIONS` sesuai model.
- [ ] **`chunk_policy`.** Done when: `test_policy_chunk_ids_and_metadata_are_stable` hijau.
- [ ] **`embed` di `OpenAIProvider`.** Done when: embedding batch berjalan dan dimensi divalidasi sebelum insert.
- [ ] **Indexing di seed.** Done when: semua chunk tersimpan dengan document ID, section, version, effective date, dan vector. Vector dikirim sebagai teks lalu di-cast ke `vector`, karena package `pgvector` tidak ada (T8).

Pertanyaan pemandu:

- Apa yang membuat chunk ID stabil, dan apa risikonya jika ID berubah setiap indexing?
- Bagaimana menjaga `version: 2.1` tetap string?

## Step 4 — Hybrid retrieval

- [ ] **`ResilientCache` dan `NullCache`.** Done when: ada test tambahan bahwa Redis mati berperilaku seperti cache miss.
- [ ] **`lexical_search` dan `vector_search`.** Done when: keduanya mengembalikan `PolicyChunk` dengan metadata lengkap.
- [ ] **`RetrievalService` (RRF + keyword rerank).** Done when: cache key memuat versi index.
- [ ] **Pendukung test retrieval.** Done when: pencarian `MemoryRepository` dan `embed` `DeterministicProvider` membuat `test_hybrid_retrieval_prefers_lexical_match` hijau.
- [ ] **Checkpoint 2.** Done when: “jatah cuti tahunan” menemukan `HR-LEAVE-001` di top 3 dengan metadata lengkap.

Pertanyaan pemandu:

- Mengapa versi index harus masuk cache key?
- Kata `jatah`, `WFH`, `probation`, dan `surat dokter` muncul di evaluation case, tetapi tidak ada di dokumen kebijakan. Apa artinya bagi lexical search, dan apa artinya bagi hybrid search?
- PostgreSQL tidak punya konfigurasi text search Bahasa Indonesia bawaan. Konfigurasi apa yang dipakai, dan apa konsekuensinya?
- Query “jatah cuti tahunan” pada `websearch_to_tsquery` menggabungkan kata dengan AND. Apa hasilnya bila `jatah` tidak ada di dokumen?
- Brief menguji “versi kebijakan usang”. Bagaimana sistem memilih versi berlaku?

# Sesi Lab 2 — Agent, FastAPI, dan safety

## Step 5 — Tool wajib

- [ ] **`src/domain.py`.** Done when: `pytest tests/test_domain.py` hijau, dan test baru membuktikan aturan minimal 3 hari kerja berlaku untuk cuti tahunan tetapi tidak untuk cuti sakit.
- [ ] **Sisa `src/security.py`.** Done when: `test_redaction_covers_sensitive_patterns` hijau.
- [ ] **Sisa operasi saldo, proposal, overlap, dan tiket di repository.** Done when: `MemoryRepository` dan `PostgresRepository` sama-sama mendukungnya.
- [ ] **Saldo efektif di validasi (K8).** Done when: test membuktikan saldo annual 8 dengan request annual pending 5 hari menolak pengajuan annual 5 hari; request `approved`, `cancelled`, proposal belum dikonfirmasi, dan tipe cuti lain tidak dihitung; saldo di database tidak berubah.
- [ ] **Rincian saldo di `get_my_leave_balance` (K8).** Done when: hasil tool memuat saldo di database, total hari pending, dan saldo efektif per tipe cuti.
- [ ] **`policy_version` dan `proposal_id` (T7, K11).** Done when: proposal tersimpan dengan `policy_version` dari satu sumber yang jelas, dan `proposal_id` dibuat backend dengan `uuid4` serta prefix yang konsisten.
- [ ] **`TOOL_SCHEMAS` dan `ToolExecutor`.** Done when: empat tool tervalidasi Pydantic, identitas selalu dari `auth`, dan tidak ada argumen `employee_id`.

Pertanyaan pemandu:

- Baca `tests/test_domain.py:39-42`. Argumen dan saldonya sama, tetapi error yang diharapkan berbeda. Apa yang tersirat tentang urutan validasi?
- Aturan 3 hari kerja dicek sebelum atau sesudah urutan tanggal? Uji jawabanmu dengan kasus `(date(2026, 9, 25), date(2026, 9, 24))` di `tests/test_domain.py:20`.
- Mengapa `domain.py` dilarang memanggil model?
- Pola `redact` apa yang mencegah false positive, misalnya menyamarkan semua angka panjang?

## Step 6 — Agent loop

- [ ] **`respond` di `OpenAIProvider`.** Done when: `store=False`, strict schema, hashed `safety_identifier`, retry terbatas, usage tercatat.
- [ ] **`respond` di `DeterministicProvider`.** Done when: respons deterministik, tanpa jaringan.
- [ ] **`SYSTEM_INSTRUCTIONS` dan `AgentService.run`.** Done when: `pytest tests/test_agent_reliability.py` hijau, termasuk batas turn, tool call, dan citation validation.

Pertanyaan pemandu:

- `store=False` dan `ModelTurn.output_items`: bagaimana percakapan tool dilanjutkan tanpa state di provider?
- `balance-other-007` melarang string `EMP-002` muncul. Bagaimana menolak permintaan tanpa mengulang ID itu?

## Step 7 — API contract

- [ ] **`src/api.py` (8 endpoint dan problem detail).** Done when: `pytest tests/test_api.py` hijau.
- [ ] **`/readyz` saat PostgreSQL mati (T9).** Done when: dengan container `postgres` dihentikan, `/readyz` tidak mengembalikan `ready`, sesuai klaim di diagram.
- [ ] **Checkpoint 3.** Done when: Streamlit menjawab kebijakan dan saldo, dan Bima tidak bisa membaca trace Alya.

Pertanyaan pemandu:

- `tests/test_api.py:11` mengharapkan 401 tanpa token. Apa perilaku default `HTTPBearer` di versi FastAPI yang terpasang?
- Field apa saja yang dibaca `app.py` dari `/monitoring/summary`? Kontraknya tidak tertulis di brief.

## Step 8 — Confirmation boundary

- [ ] **`confirm_proposal` di kedua repository.** Done when: `pytest tests/test_actions.py` hijau, dan versi PostgreSQL memakai transaksi dengan row lock.
- [ ] **Cek ulang saldo efektif saat konfirmasi (K8).** Done when: dua proposal 5 hari dengan saldo 8 tidak bisa sama-sama dikonfirmasi.
- [ ] **Test constraint K9 di repo (T10).** Done when: sembilan kasus dari script sementara 9 Nov menjadi test, termasuk “asisten menulis `approved` ditolak” dan “proposal dikonfirmasi dua kali ditolak”.
- [ ] **Semua test non-live.** Done when: `pytest -m "not live"` hijau seluruhnya.
- [ ] **Checkpoint 4.** Done when: sebelum konfirmasi tidak ada request, dan konfirmasi ganda dengan key sama menghasilkan request ID yang sama.

Pertanyaan pemandu:

- Pada konfirmasi berulang, mana yang harus dicek lebih dulu: idempotency atau expiry? Apa yang terjadi bila pengguna me-retry dengan key yang sama sesudah proposal kedaluwarsa?
- Dua proposal dengan tanggal sama, keduanya dikonfirmasi. Di mana overlap harus dicek ulang?

# Sesi Lab 3 — Production readiness

## Step 9 — Telemetry dan privacy

- [ ] **Telemetry dan redaction.** Done when: trace tanpa prompt mentah/chain-of-thought dan tes kebocoran `diabetes` lulus.

Pertanyaan pemandu:

- `medical-pii-012` melarang `diabetes`. Apakah cukup disamarkan di trace, atau perlu sebelum dikirim ke provider?
- Isi `reason` dan ringkasan tiket juga masuk database. Apakah keduanya melewati redaction?

## Step 10 — Evaluation dan monitoring

- [ ] **`/monitoring/summary` dan `/monitoring/alerts`.** Done when: alert memakai `data/monitoring_rules.json` dan menghormati `minimum_samples`.
- [ ] **`src/run_evaluation.py`.** Done when: 15 kasus berjalan dan `outputs/evaluation_report.json` memuat metrik plus GO/NO-GO.
- [ ] **Regression case overlap (tugas assessment).** Done when: case, expected, actual, trace ID, dan keputusan lulus/gagal terkumpul.
- [ ] **Perbaiki kegagalan evaluasi.** Done when: semua target rilis tercapai; acceptance assertion tidak dilonggarkan.
- [ ] **Uji kegagalan.** Done when: model, PostgreSQL, dan Redis mati masing-masing berakhir aman tanpa side effect tambahan.

## Step 11 — Deployment dan demo

- [ ] **`Dockerfile`.** Done when: image non-root terbangun tanpa API key, dan `whoami` di container bukan `root`.
- [ ] **Urutan `docker-delivery.md` dari checkout bersih.** Done when: seed, API, UI, dan `pytest -m "not live"` di container lulus; `/readyz` mengembalikan `ready`.
- [ ] **Risk register dan demo script.** Done when: semua risiko punya owner, mitigation, dan evidence nyata.
- [ ] **Checkpoint 5.** Done when: demo Docker mencakup happy path, blocked cross-user request, pending confirmation, failure/abstention, monitoring evidence, dan residual risk.

Pertanyaan pemandu:

- TODO Dockerfile tidak menyebut `pyproject.toml`. Apakah pytest di container butuh file itu?
- User non-root harus bisa menulis ke mana? Lihat perintah `docker compose cp api:/app/outputs` dan kebutuhan `HOME` Streamlit.
- `docker-compose.yml` hanya meneruskan env tertentu. Variabel `.env` mana yang tidak sampai ke container API?

# Finalisasi

- [ ] **Diagram final dan ADR.** Done when: `architecture.md` memuat semua elemen wajib dan keputusan RAG vs fine-tuning vs multi-agent.
- [ ] **`templates/evaluation-report.md`.** Done when: terisi dari hasil evaluasi nyata.
- [ ] **8 soal `assessment.md`.** Done when: tiap jawaban merujuk kode atau test.
- [ ] **Screenshot dan backup output.** Done when: UI, monitoring, dan hasil test tersimpan tanpa secret.
- [ ] **Demo 5–7 menit.** Done when: latihan dua kali dengan timer, mencakup happy, blocked, dan failure path.
- [ ] **Uji akhir dari checkout bersih.** Done when: clone baru lulus `submission-checklist.md`.

## Progress log

| Tanggal | Selesai | Blocker | Berikutnya |
|---|---|---|---|
| 2026-11-05 | Analisis dokumentasi dan planning; setup Python dan git baseline; preflight test. | K1, K2, K4, dan K5 masih terbuka. | `business_days`. |
| 2026-11-06 | Jadwal diperbarui: deadline 20 Nov. K1 diputuskan, K5 selesai, K7 diputuskan: urutan mengikuti `lab.md`. Docker dan PostgreSQL/Redis siap; dokumen ter-commit. Belum ada kode baru. | K2 masih terbuka. `AGENT_MODEL` dan `EMBEDDING_MODEL` di `.env` masih kosong. | Project brief, ADR, dan diagram di Step 1. |
| 2026-11-09 | K8 dan K9 diputuskan. Project brief, ADR, dan draft diagram selesai: Checkpoint 1 terpenuhi. `token_hash` dan schema 7 tabel selesai. Pytest tetap 4 passed (sama dengan baseline). | K2 masih menunggu instruktur. `AGENT_MODEL` dan `EMBEDDING_MODEL` di `.env` masih kosong. | Seed idempotent dan `--reset`, lalu `PostgresRepository` dasar. |
