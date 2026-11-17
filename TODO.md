# TODO — HR Agent (Milestone P2M2)

Panduan kerja utama. Kerjakan satu task pada satu waktu, centang sesudah **Done when** terbukti.

Urutan kerja mengikuti Step 1–11 di [lab.md](lab.md) (keputusan K7).

- **Mulai:** Kamis, 5 November 2026
- **Target internal:** chat dan saldo berjalan lewat Streamlit pada 13 November; seluruh sistem selesai pada 15 November 2026.
- **Deadline pengumpulan:** 20 November 2026.
- **Status saat ini (10 Nov):** Step 1–10 selesai, plus K25–K28. Step 11: Dockerfile dan alur `docker-delivery.md` lulus dari salinan bersih (K29). Evaluator di Docker **GO** 3 kali berturut-turut (16/16). Pytest 255 passed di host dan di container.
- **Task berikutnya:** commit, lalu risk register, README, diagram final, demo script, dan screenshot. Terakhir, uji ulang dari `git clone` baru.

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
| K2 | `create_hr_ticket` menulis ke database tanpa konfirmasi, padahal rubric melarang side effect tanpa konfirmasi eksplisit. Endpoint confirm hanya mendukung `leave_request`. | Tanya instruktur. Jika tidak ada jawaban: tiket hanya dibuat bila diminta jelas oleh pengguna, ringkasannya disamarkan, dan alasannya dicatat di risk register. | **Diputuskan** (mentor, 9 Nov): konfirmasi lewat percakapan. Diterapkan 10 Nov sebagai K25. |
| K3 | Kebijakan `HR-LEAVE-001` mewajibkan pengajuan minimal 3 hari kerja sebelumnya, tetapi aturan ini tidak ada di daftar validasi lab/brief. | Terapkan agar jawaban dan perilaku sistem konsisten. Risiko: bisa bertabrakan dengan hidden test. | **Diterapkan** (5 Nov 2026), khusus cuti tahunan. Beri tahu instruktur. |
| K4 | Waktu pengerjaan terbatas. | Ikuti tabel Jadwal. | **Diputuskan** (6 Nov 2026): Senin 3 jam, Selasa–Jumat sekitar 2 jam per hari. |
| K5 | `.env` sudah ada, tetapi `AGENT_MODEL` dan `EMBEDDING_MODEL` masih kosong. | Lengkapi di Step 3, sebelum indexing. | **Selesai** (6 Nov 2026): kredensial tersedia. |
| K7 | Urutan kerja: `lab.md` atau inti logika lebih dulu. | Inti logika lebih dulu, kecuali mentor mengecek checkpoint sesuai urutan lab. | **Ikuti `lab.md`** (6 Nov 2026). |
| K8 | Request pending tidak mengurangi saldo, jadi total request pending bisa melebihi saldo. | Hitung saldo efektif di dalam validasi, lalu cek ulang saat konfirmasi. | **Digantikan K26** (10 Nov): saldo kini benar-benar dipotong saat konfirmasi. |

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
- [x] **Seed idempotent.** Terbukti 9 Nov: seed 2x tetap 3 pegawai, 6 saldo, 2 request historis; token tersimpan sebagai hash 64 karakter; historis `status_set_by = 'seed'`; seed tanpa `--reset` mempertahankan request buatan aplikasi, sedangkan `--reset` menghapusnya. Done when: `python -m src.setup_lab` dua kali tidak menduplikasi data, dan `--reset` tersedia. Token tersimpan sebagai hash. `--reset` menghapus lalu membuat ulang semua tabel, karena `IF NOT EXISTS` tidak mengubah tabel lama (T6). Data historis memakai `status_set_by = 'seed'` (K9).
- [x] **`PostgresRepository` dasar.** Done when: pool, `health`, `authenticate`, dan `get_balances` bekerja tanpa interpolasi input ke SQL. Terbukti 9 Nov: token benar → `AuthContext`, token salah/kosong/`' OR '1'='1` → `None`; saldo Alya 3 baris, admin 0; `health()` → `False` dalam 2 detik saat PostgreSQL dimatikan.

Pertanyaan pemandu:

- Kenapa token disimpan sebagai hash? Kenapa SHA-256 polos cukup untuk token demo, tetapi tidak cocok untuk password?
- `data/historical_requests.json` memuat status `approved` dan `cancelled`. Apa dampaknya pada status constraint, dan bagaimana sistem tetap tidak bisa membuat `approved`?
- Apa yang membuat seed aman dijalankan dua kali?

## Step 3 — Policy indexing

- [x] **Lengkapi `.env`.** Done when: `AGENT_MODEL` dan `EMBEDDING_MODEL` terisi, dan `EMBEDDING_DIMENSIONS` sesuai model. Terbukti 9 Nov: panggilan embedding asli mengembalikan 1536 dimensi, sama dengan `EMBEDDING_DIMENSIONS`.
- [x] **`chunk_policy`.** Done when: `test_policy_chunk_ids_and_metadata_are_stable` hijau. Terbukti 9 Nov: test hijau; seed memasukkan 15 chunk dari 7 dokumen (tanpa embedding); chunk yang isinya berubah kehilangan embedding lama, dan section yang dihapus dari file ikut terhapus (K14).
- [x] **`embed` di `OpenAIProvider`.** Done when: embedding batch berjalan dan dimensi divalidasi sebelum insert. Terbukti 9 Nov: 15 chunk di-embed dalam satu batch; jumlah dan dimensi vector dicek sebelum disimpan.
- [x] **Indexing di seed.** Done when: semua chunk tersimpan dengan document ID, section, version, effective date, dan vector. Vector dikirim sebagai teks lalu di-cast ke `vector`, karena package `pgvector` tidak ada (T8). Terbukti 9 Nov: 15/15 chunk punya embedding; seed ulang meng-embed 0 chunk; tanpa API key seed tetap jalan dengan peringatan (K15).

Pertanyaan pemandu:

- Apa yang membuat chunk ID stabil, dan apa risikonya jika ID berubah setiap indexing?
- Bagaimana menjaga `version: 2.1` tetap string?

## Step 4 — Hybrid retrieval

- [x] **`ResilientCache` dan `NullCache`.** Done when: ada test tambahan bahwa Redis mati berperilaku seperti cache miss. Terbukti 9 Nov: 5 test di `tests/test_cache.py`, termasuk circuit breaker; Redis asli dimatikan → pencarian tetap jalan, request ke-2 dan seterusnya 0 ms.
- [x] **`lexical_search` dan `vector_search`.** Done when: keduanya mengembalikan `PolicyChunk` dengan metadata lengkap.
- [x] **`RetrievalService` (RRF + keyword rerank).** Done when: cache key memuat versi index. Terbukti: `test_cache_key_contains_index_version`; cache hit 1 ms vs miss 441 ms.
- [x] **Pendukung test retrieval.** Done when: pencarian `MemoryRepository` dan `embed` `DeterministicProvider` membuat `test_hybrid_retrieval_prefers_lexical_match` hijau.
- [x] **Checkpoint 2.** Done when: “jatah cuti tahunan” menemukan `HR-LEAVE-001` di top 3 dengan metadata lengkap. Terbukti 9 Nov: `HR-LEAVE-001#hak-dan-saldo` di peringkat 1 dengan section, version, dan effective date; recall@3 = 7/7 pada kasus evaluasi kebijakan.

Pertanyaan pemandu:

- Mengapa versi index harus masuk cache key?
- Kata `jatah`, `WFH`, `probation`, dan `surat dokter` muncul di evaluation case, tetapi tidak ada di dokumen kebijakan. Apa artinya bagi lexical search, dan apa artinya bagi hybrid search?
- PostgreSQL tidak punya konfigurasi text search Bahasa Indonesia bawaan. Konfigurasi apa yang dipakai, dan apa konsekuensinya?
- Query “jatah cuti tahunan” pada `websearch_to_tsquery` menggabungkan kata dengan AND. Apa hasilnya bila `jatah` tidak ada di dokumen?
- Brief menguji “versi kebijakan usang”. Bagaimana sistem memilih versi berlaku?

# Sesi Lab 2 — Agent, FastAPI, dan safety

## Step 5 — Tool wajib

- [x] **`src/domain.py`.** Done when: `pytest tests/test_domain.py` hijau, dan test baru membuktikan aturan minimal 3 hari kerja berlaku untuk cuti tahunan tetapi tidak untuk cuti sakit. Terbukti 9 Nov: `test_domain.py` dan `test_domain_rules.py` hijau (17 test); tafsiran K3 = hari pengajuan ikut dihitung.
- [x] **Sisa `src/security.py`.** Done when: `test_redaction_covers_sensitive_patterns` hijau. Terbukti 9 Nov: test mentor hijau, ditambah 22 test di `tests/test_security.py`, termasuk teks HR normal yang tidak boleh berubah (K17).
- [x] **Sisa operasi saldo, proposal, overlap, dan tiket di repository.** Done when: `MemoryRepository` dan `PostgresRepository` sama-sama mendukungnya. Terbukti 9 Nov: `tests/test_repository_contract.py` menjalankan 11 test yang sama untuk kedua repository; sisa baris uji di database 0 (K18).
- [x] **Saldo efektif di validasi (K8).** Done when: test membuktikan saldo annual 8 dengan request annual pending 5 hari menolak pengajuan annual 5 hari; request `approved`, `cancelled`, proposal belum dikonfirmasi, dan tipe cuti lain tidak dihitung; saldo di database tidak berubah. Terbukti di level repository + domain (`effective_balances`). Tool wajib memanggilnya; dicek lagi di task `ToolExecutor`.
- [x] **Rincian saldo di `get_my_leave_balance` (K8).** Done when: hasil tool memuat saldo di database, total hari pending, dan saldo efektif per tipe cuti. Terbukti: `balance_days` 8, `pending_manager_review_days` 5, `available_to_request_days` 3.
- [x] **`policy_version` dan `proposal_id` (T7, K11).** Done when: proposal tersimpan dengan `policy_version` dari satu sumber yang jelas, dan `proposal_id` dibuat backend dengan `uuid4` serta prefix yang konsisten. Terbukti: `policy_version` dari `RULE_POLICY_VERSIONS`; `proposal_id` = `AP-` + 32 hex `uuid4`.
- [x] **`TOOL_SCHEMAS` dan `ToolExecutor`.** Done when: empat tool tervalidasi Pydantic, identitas selalu dari `auth`, dan tidak ada argumen `employee_id`. Terbukti 9 Nov: 10 test di `tests/test_tools.py`; argumen `employee_id` dari model ditolak (`blocked`), bukan diabaikan diam-diam (K19).

Pertanyaan pemandu:

- Baca `tests/test_domain.py:39-42`. Argumen dan saldonya sama, tetapi error yang diharapkan berbeda. Apa yang tersirat tentang urutan validasi?
- Aturan 3 hari kerja dicek sebelum atau sesudah urutan tanggal? Uji jawabanmu dengan kasus `(date(2026, 9, 25), date(2026, 9, 24))` di `tests/test_domain.py:20`.
- Mengapa `domain.py` dilarang memanggil model?
- Pola `redact` apa yang mencegah false positive, misalnya menyamarkan semua angka panjang?

## Step 6 — Agent loop

- [x] **`respond` di `OpenAIProvider`.** Done when: `store=False`, strict schema, hashed `safety_identifier`, retry terbatas, usage tercatat. Terbukti 9 Nov dengan model asli: 6 pertanyaan evaluasi + 18 pertanyaan kebijakan (2 putaran) sesuai harapan.
- [x] **`respond` di `DeterministicProvider`.** Done when: respons deterministik, tanpa jaringan.
- [x] **`SYSTEM_INSTRUCTIONS` dan `AgentService.run`.** Done when: `pytest tests/test_agent_reliability.py` hijau, termasuk batas turn, tool call, dan citation validation. Terbukti: test mentor hijau + 12 test di `tests/test_agent.py` (batas turn, tool call, waktu, sitasi, output guard, privasi trace) (K20).

Pertanyaan pemandu:

- `store=False` dan `ModelTurn.output_items`: bagaimana percakapan tool dilanjutkan tanpa state di provider?
- `balance-other-007` melarang string `EMP-002` muncul. Bagaimana menolak permintaan tanpa mengulang ID itu?

## Step 7 — API contract

- [x] **`src/api.py` (8 endpoint dan problem detail).** Done when: `pytest tests/test_api.py` hijau. Terbukti 9 Nov: test mentor hijau + 10 test di `tests/test_api_contract.py`; server uvicorn diuji dengan curl (K21).
- [x] **`/readyz` saat PostgreSQL mati (T9).** Done when: dengan container `postgres` dihentikan, `/readyz` tidak mengembalikan `ready`, sesuai klaim di diagram. Terbukti: 503 `not_ready`; chat 503 dalam 5 detik; pulih 5 detik setelah PostgreSQL hidup (sebelum perbaikan: ~75 detik).
- [x] **Checkpoint 3.** Done when: Streamlit menjawab kebijakan dan saldo, dan Bima tidak bisa membaca trace Alya. Terbukti 9 Nov: lewat Streamlit, jatah cuti dijawab dengan `[HR-LEAVE-001]` dan saldo Alya tampil; trace Alya oleh Bima → 403.

Pertanyaan pemandu:

- `tests/test_api.py:11` mengharapkan 401 tanpa token. Apa perilaku default `HTTPBearer` di versi FastAPI yang terpasang?
- Field apa saja yang dibaca `app.py` dari `/monitoring/summary`? Kontraknya tidak tertulis di brief.

## Step 8 — Confirmation boundary

- [x] **`confirm_proposal` di kedua repository.** Done when: `pytest tests/test_actions.py` hijau, dan versi PostgreSQL memakai transaksi dengan row lock. Terbukti 9 Nov: test mentor hijau; PostgreSQL memakai advisory lock per pegawai + `FOR UPDATE` pada proposal (K22).
- [x] **Cek ulang saldo efektif saat konfirmasi (K8).** Done when: dua proposal 5 hari dengan saldo 8 tidak bisa sama-sama dikonfirmasi. Terbukti berurutan maupun paralel (2 thread bersamaan) di Memory dan PostgreSQL.
- [x] **Test constraint K9 di repo (T10).** Done when: sembilan kasus dari script sementara 9 Nov menjadi test, termasuk “asisten menulis `approved` ditolak” dan “proposal dikonfirmasi dua kali ditolak”. Terbukti: `tests/test_database_guards.py`.
- [x] **API login sebagai `hr_api` (K9 opsi C, brief poin 7).** Estimasi 2 jam. Terbukti 9 Nov: 16 test di `tests/test_database_guards.py`; API terhubung sebagai `hr_api`; `health()` False jika login gagal. Sisa: uji dari checkout bersih ikut task Step 11. Done when:
  - `setup_lab` (login sebagai `hr_app`) membuat role `hr_api` beserta `GRANT` per tabel dan RLS di `leave_requests`, dan tetap aman dijalankan ulang ketika role sudah ada.
  - API membentuk URL `hr_api` dari `DATABASE_URL` tanpa mengubah `docker-compose.yml`, dan tidak pernah memakai `SET ROLE`.
  - Test: login sebagai `hr_api` gagal menulis `approved` walaupun `status_set_by` diisi `'hr_system'`, serta gagal `UPDATE`, `DELETE`, dan `DROP TABLE`.
  - Alur `docker-delivery.md` dari checkout bersih tetap lulus, dan `/readyz` mendeteksi jika API gagal login.
- [x] **Semua test non-live.** Done when: `pytest -m "not live"` hijau seluruhnya. Terbukti 9 Nov: 144 passed, 0 failed.
- [x] **Checkpoint 4.** Done when: sebelum konfirmasi tidak ada request, dan konfirmasi ganda dengan key sama menghasilkan request ID yang sama. Terbukti lewat Streamlit: sebelum Konfirmasi hanya ada `LR-HIST-001`; dua klik → satu request `LR-48E7EBDEA378`, `pending_manager_review`, `status_set_by = assistant`; saldo tetap 8.

Pertanyaan pemandu:

- Pada konfirmasi berulang, mana yang harus dicek lebih dulu: idempotency atau expiry? Apa yang terjadi bila pengguna me-retry dengan key yang sama sesudah proposal kedaluwarsa?
- Dua proposal dengan tanggal sama, keduanya dikonfirmasi. Di mana overlap harus dicek ulang?
- `hr_app` adalah pemilik tabel. Apakah RLS berlaku untuk pemilik tabel? Kenapa itu tidak masalah selama API tidak pernah login sebagai `hr_app`?

# Sesi Lab 3 — Production readiness

## Step 9 — Telemetry dan privacy

- [x] **Telemetry dan redaction.** Done when: trace tanpa prompt mentah/chain-of-thought dan tes kebocoran `diabetes` lulus. Terbukti 9 Nov: 5 test di `tests/test_privacy.py` (setiap pintu masuk dan keluar); uji live dengan 3 pesan penuh PII lalu pindai database → 0 kebocoran (K23).

Pertanyaan pemandu:

- `medical-pii-012` melarang `diabetes`. Apakah cukup disamarkan di trace, atau perlu sebelum dikirim ke provider?
- Isi `reason` dan ringkasan tiket juga masuk database. Apakah keduanya melewati redaction?

## Step 10 — Evaluation dan monitoring

- [x] **`/monitoring/summary` dan `/monitoring/alerts`.** Done when: alert memakai `data/monitoring_rules.json` dan menghormati `minimum_samples`. Terbukti sejak Step 7 (K21): alert p95 menyala pada 34 run, tidak menyala pada 1 run.
- [x] **`src/run_evaluation.py`.** Done when: 15 kasus berjalan dan `outputs/evaluation_report.json` memuat metrik plus GO/NO-GO. Terbukti 9 Nov: 16 kasus live, **GO**; evaluator sendiri diuji bisa NO-GO (`tests/test_evaluation.py`) (K24).
- [x] **Regression case overlap (tugas assessment).** Done when: case, expected, actual, trace ID, dan keputusan lulus/gagal terkumpul. Terbukti: `leave-overlap-016` di `evaluation/regression_cases.json`, lulus, trace `tr-b42f577c…`, dicatat di `templates/evaluation-report.md`.
- [x] **Perbaiki kegagalan evaluasi.** Done when: semua target rilis tercapai; acceptance assertion tidak dilonggarkan. Terbukti: pass 100%, hard gates 100%, recall@3 100%, citation validity 100%.
- [x] **Uji kegagalan.** Done when: model, PostgreSQL, dan Redis mati masing-masing berakhir aman tanpa side effect tambahan. Terbukti 9 Nov: jumlah request/proposal/tiket sama sebelum dan sesudah untuk ketiganya.

## Step 11 — Deployment dan demo

- [x] **`Dockerfile`.** Done when: image non-root terbangun tanpa API key, dan `whoami` di container bukan `root`. Selain daftar di template, salin juga `ui_format.py` (K27), karena `app.py` mengimpornya. Terbukti 10 Nov: `whoami` = `appuser` di `api` dan `streamlit`, variabel API key tidak ada di image, kode read-only, `/app/outputs` bisa ditulis (K29).
- [x] **Urutan `docker-delivery.md` dari checkout bersih.** Done when: seed, API, UI, dan `pytest -m "not live"` di container lulus; `/readyz` mengembalikan `ready`. Terbukti 10 Nov dari salinan working tree tanpa `.env`/`.venv`: seed 15 chunk, `/readyz` `ready`, 255 passed di container, cek UI lulus, live test lulus, evaluator GO 3x. Uji ini menemukan dua bug: `OPENAI_BASE_URL` kosong dari Compose (K29) dan hard gate `leave-past-009` yang gagal 5/10 (K28). Sisa: ulangi dari `git clone` setelah commit.
- [ ] **Risk register dan demo script.** Done when: semua risiko punya owner, mitigation, dan evidence nyata.
- [ ] **Checkpoint 5.** Done when: demo Docker mencakup happy path, blocked cross-user request, pending confirmation, failure/abstention, monitoring evidence, dan residual risk.

Pertanyaan pemandu:

- TODO Dockerfile tidak menyebut `pyproject.toml`. Apakah pytest di container butuh file itu?
- User non-root harus bisa menulis ke mana? Lihat perintah `docker compose cp api:/app/outputs` dan kebutuhan `HOME` Streamlit.
- `docker-compose.yml` hanya meneruskan env tertentu. Variabel `.env` mana yang tidak sampai ke container API?

# Finalisasi

- [ ] **Diagram final dan ADR.** Done when: `architecture.md` memuat semua elemen wajib dan keputusan RAG vs fine-tuning vs multi-agent.
- [x] **`templates/evaluation-report.md`.** Done when: terisi dari hasil evaluasi nyata. Selesai 9 Nov dari run live GO; isi ulang setelah evaluasi terakhir sebelum pengumpulan.
- [ ] **8 soal `assessment.md`.** Done when: tiap jawaban merujuk kode atau test.
- [ ] **Screenshot dan backup output.** Done when: UI, monitoring, dan hasil test tersimpan tanpa secret.
- [ ] **Demo 5–7 menit.** Done when: latihan dua kali dengan timer, mencakup happy, blocked, dan failure path.
- [ ] **Uji akhir dari checkout bersih.** Done when: clone baru lulus `submission-checklist.md`.
- [x] **Cocokkan brief poin 7 dengan kode.** Done when: jika task `hr_api` di Step 8 selesai, brief tetap; jika tidak selesai, poin 7 dikembalikan ke versi “API masih login sebagai `hr_app`”. Selesai 9 Nov: task `hr_api` selesai, brief diperbarui dari “akan diterapkan” menjadi kondisi sekarang.
- [x] **Sembunyikan outcome dan trace ID dari UI pegawai (sesi terpisah).** Done when: `app.py` tidak lagi menampilkan baris `Outcome: … · Trace: …`; API tetap mengirim `outcome` dan `trace_id` (brief.md:37); endpoint trace tetap bisa dibaca pemilik dan admin (brief.md:40); test UI tetap hijau dan evaluasi tetap GO. **Diubah 18 Nov:** baris itu tidak dihapus, tetapi dilipat ke expander tertutup "Detail teknis", karena pemeriksaan penerimaan di `docker-delivery.md` meminta grader memastikan jawaban "memuat sitasi kebijakan serta trace". Nama tool tidak pernah ditampilkan di UI. Bagian dari perbaikan UI (riwayat chat, contoh pertanyaan per persona, tabel cuti dan alert yang terbaca, pesan error ramah).
- [x] **Rapikan duplikasi di `src/agent.py` (sesi terpisah).** (1) Dua cabang `elif run.searched and not citations` (sekitar baris 275–278) identik, jadi yang kedua tidak pernah jalan. (2) Kunci `"unsupported_numbers"` ditulis dua kali di dict trace (sekitar baris 354, satu baris dengan `number_context_mismatch`). Done when: tinggal satu cabang dan satu kunci, perilaku tidak berubah, dan `pytest -m "not live"` tetap hijau. Selesai 17 Nov di commit `5d4ce2c`.
- [ ] **Catat batas penyamaran medis di risk register (sesi terpisah).** Temuan 13 Nov: `redact()` menyamarkan "lupus" dan "diabetes", tetapi "Gula darah saya tinggi" dan "Saya kena diabetis" lolos. Teksnya terkirim ke provider dan tersimpan di Redis hingga 15 menit; model tetap menolak mencatat; trace tidak menyimpan teks. Done when: `templates/risk-register.csv` memuat risiko ini dengan bukti, dampak, mitigasi sekarang, dan perbaikan untuk produksi; laporan tidak mengklaim semua data medis pasti tersamarkan.

- [x] **Fitur tambahan: analisis cuti tim untuk manajer + RLS (K36).** Done when: tool tim, RLS di tiga tabel inti, persona manajer, kasus evaluasi manajer, dan dokumen selesai; evaluasi live tetap GO. Selesai 18 Nov di branch `feat/team-analytics`: 354 passed, evaluasi live GO 22/22. Catatan kerja: `add_fitur_analisis_notes.md`.
- [ ] **Uji ulang setelah fitur tim (sisa daftar 7.2 di `add_fitur_analisis_notes.md`).** Done when: tes manual dari `test-cases-eksplorasi.xlsx` ditambah kasus manajer, alur `docker-delivery.md` dari checkout bersih, dan persona lama serta manajer dicoba di UI.

## Progress log

| Tanggal | Selesai | Blocker | Berikutnya |
|---|---|---|---|
| 2026-11-05 | Analisis dokumentasi dan planning; setup Python dan git baseline; preflight test. | K1, K2, K4, dan K5 masih terbuka. | `business_days`. |
| 2026-11-06 | Jadwal diperbarui: deadline 20 Nov. K1 diputuskan, K5 selesai, K7 diputuskan: urutan mengikuti `lab.md`. Docker dan PostgreSQL/Redis siap; dokumen ter-commit. Belum ada kode baru. | K2 masih terbuka. `AGENT_MODEL` dan `EMBEDDING_MODEL` di `.env` masih kosong. | Project brief, ADR, dan diagram di Step 1. |
| 2026-11-09 | K8 dan K9 diputuskan. Project brief, ADR, dan draft diagram selesai: Checkpoint 1 terpenuhi. `token_hash`, schema 7 tabel, seed idempotent dan `--reset`, serta `PostgresRepository` dasar selesai: **Step 2 selesai**. **Step 3 selesai**: `chunk_policy`, `.env`, `embed`, dan indexing; 15 chunk ber-embedding. **Step 4 selesai**: cache dengan circuit breaker, hybrid retrieval (RRF + keyword rerank), Checkpoint 2, recall@3 = 7/7. **Step 5 selesai**: domain (K3 = hari pengajuan ikut dihitung), redaction, operasi repository dengan test kontrak Memory + PostgreSQL, saldo efektif K8, dan 4 tool. **Step 6 selesai**: agent loop terbatas, validasi sitasi, output guard, trace tanpa prompt; diuji live dengan model asli. **Step 7 selesai**: 8 endpoint, problem detail, Checkpoint 3 lewat Streamlit; bug pool lambat pulih setelah PostgreSQL mati ditemukan dan diperbaiki. **Step 8 selesai**: konfirmasi transaksional (advisory + row lock), K8 dicek ulang termasuk saat paralel, test constraint K9, opsi C (`hr_api` + RLS), Checkpoint 4. **Step 9 selesai**: pesan disamarkan sebelum dikirim ke provider, waktu model/tool di trace, test privasi end-to-end, test repository diisolasi dari data demo. **Step 10 selesai**: evaluator live 16 kasus → GO (pass, hard gate, recall@3, sitasi semuanya 100%); regression case overlap; uji kegagalan model/PostgreSQL/Redis tanpa side effect; T17 ditutup (93% waktu di model). Pytest 157 passed, 0 failed. | K2 masih menunggu instruktur. | Step 11: Docker. |
| 2026-11-18 | Fitur analisis cuti tim (K36): role `manager`, RLS di tiga tabel inti, query tim, tool `get_team_leave_analytics`, prompt manajer, persona Sari dan Dewi, 5 kasus evaluasi. Evaluasi live di stack terpisah: run 1 GO 21/22 (kasus 020 abstain karena cabang `no_citation`), diperbaiki, run 2 GO 22/22. Pytest 354 passed. | — | Uji ulang daftar 7.2, lalu todo yang tersisa. |
