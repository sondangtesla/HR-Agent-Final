# TODO — HR Agent (Milestone P2M2)

Panduan kerja utama. Kerjakan satu task pada satu waktu, centang sesudah **Done when** terbukti.

- **Mulai:** Kamis, 5 November 2026
- **Target internal:** seluruh sistem selesai pada 13 November 2026.
- **Deadline pengumpulan:** 20 November 2026.
- **Status saat ini:** setup selesai, implementasi belum dimulai.

Tahap adalah blok kerja, bukan hari kalender. Lihat [Jadwal](#jadwal) untuk tanggalnya.

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
| K4 | Waktu pengerjaan sampai target 13 Nov terbatas. | Ikuti tabel Jadwal. | **Diputuskan** (6 Nov 2026): Senin 3 jam, Selasa–Jumat sekitar 2 jam per hari. |
| K5 | `.env` belum ada, tetapi API key dan nama model sudah dimiliki. | Isi `.env` di Tahap 4. Sampai saat itu cukup memakai `DeterministicProvider`. | **Selesai** (6 Nov 2026): kredensial tersedia. |

## Ringkasan output per tahap

| Tahap | Fokus | Output sesi ngoding | Output sesi non-ngoding |
|---|---|---|---|
| 1 | Menyiapkan lingkungan, lalu menulis aturan cuti dan penyamaran data. | `src/domain.py` dan `src/security.py` selesai, test-nya hijau. | `.venv` dan git siap; peta failure test; project brief; draft diagram trust boundary. |
| 2 | Membuat sistem bisa mencari kebijakan, memakai data tiruan di memori tanpa internet. | `MemoryRepository`, cache, `DeterministicProvider`, `chunk_policy`, dan `RetrievalService` selesai; `test_actions` dan test retrieval hijau. | Tidak ada. |
| 3 | Menyambungkan tool, agent, dan API, masih memakai model tiruan. | `TOOL_SCHEMAS`, `ToolExecutor`, `AgentService`, dan `src/api.py` selesai; semua `pytest -m "not live"` hijau. | Kredensial model dari instruktur sudah di tangan (K5). |
| 4 | Mengganti data tiruan dengan PostgreSQL dan mengindeks dokumen kebijakan. | `src/setup_lab.py` dan `PostgresRepository` selesai; seed bisa diulang tanpa data ganda. | Docker Desktop, `.env`, PostgreSQL, dan Redis siap; Checkpoint 2 diperiksa manual lewat query “jatah cuti tahunan”. |
| 5 | Memakai model OpenAI sungguhan dan mengemas aplikasi ke Docker. | `OpenAIProvider` dan `Dockerfile` selesai. | Urutan `docker-delivery.md` dijalankan; Checkpoint 3 dan 4 diuji lewat Streamlit. |
| 6 | Mengukur kualitas agent, membuat monitoring, dan memperbaiki yang gagal. | Telemetry, dua endpoint monitoring, `src/run_evaluation.py`, regression case overlap, dan perbaikan bug selesai. | Evaluasi 15 kasus dijalankan; uji model/PostgreSQL/Redis mati; hasilnya dicatat. |
| 7 | Melengkapi bukti dan berlatih demo. Tidak ada fitur baru. | Hanya perbaikan bug jika uji akhir gagal. | Diagram final dan ADR, evaluation report, risk register, 8 soal assessment, screenshot, 2× latihan demo, uji dari clone baru. |

## Tahap 1 — Fondasi

- [x] **Setup Python.** Done when: `.venv` aktif dan dependency terpasang. Terbukti: pytest 8.4.2 berjalan.
- [x] **`git init` dan commit awal.** Done when: `git status` bersih dan `.env` tidak ter-track. Terbukti: commit `754e288`.
- [x] **Preflight test.** Done when: hasil awal dicatat. Terbukti: 4 passed, 12 failed, 5 errors, 1 deselected.
- [ ] **Peta failure per TODO (ditunda).** Done when: tiap failure dipetakan ke modul penyebabnya.
- [ ] **`templates/project-brief.md`.** Done when: semua heading terisi dengan kata-katamu sendiri.
- [ ] **Draft diagram trust boundary.** Done when: Checkpoint 1 terpenuhi (identity flow, confirmation boundary, telemetry, cache degradation, failure path).
- [ ] **`src/domain.py`.** Done when: `pytest tests/test_domain.py` hijau, dan test baru membuktikan aturan minimal 3 hari kerja berlaku untuk cuti tahunan tetapi tidak untuk cuti sakit.
- [ ] **`src/security.py`.** Done when: `test_redaction_covers_sensitive_patterns` hijau.

Pertanyaan pemandu:

- Baca `tests/test_domain.py:39-42`. Argumen dan saldonya sama, tetapi error yang diharapkan berbeda. Apa yang tersirat tentang urutan validasi?
- Mengapa `domain.py` dilarang memanggil model?
- Aturan 3 hari kerja dicek sebelum atau sesudah urutan tanggal? Uji jawabanmu dengan kasus `(date(2026, 9, 25), date(2026, 9, 24))` di `tests/test_domain.py:20`.
- Pola `redact` apa yang mencegah false positive, misalnya menyamarkan semua angka panjang?

## Tahap 2 — Data dan retrieval tanpa jaringan

- [ ] **`MemoryRepository`.** Done when: `pytest tests/test_actions.py` hijau.
- [ ] **`ResilientCache` dan `NullCache`.** Done when: ada test tambahan bahwa Redis mati berperilaku seperti cache miss.
- [ ] **`DeterministicProvider`.** Done when: embedding dan respons deterministik, tanpa jaringan.
- [ ] **`chunk_policy`.** Done when: `test_policy_chunk_ids_and_metadata_are_stable` hijau.
- [ ] **`RetrievalService` (RRF + keyword rerank).** Done when: `test_hybrid_retrieval_prefers_lexical_match` hijau.

Pertanyaan pemandu:

- Pada konfirmasi berulang, mana yang harus dicek lebih dulu: idempotency atau expiry? Apa yang terjadi bila pengguna me-retry dengan key yang sama sesudah proposal kedaluwarsa?
- Mengapa versi index harus masuk cache key?
- Kata `jatah`, `WFH`, `probation`, dan `surat dokter` muncul di evaluation case, tetapi tidak ada di dokumen kebijakan. Apa artinya bagi lexical search, dan apa artinya bagi hybrid search?

## Tahap 3 — Agent dan API

- [ ] **`TOOL_SCHEMAS` dan `ToolExecutor`.** Done when: empat tool tervalidasi Pydantic, identitas selalu dari `auth`, dan tidak ada argumen `employee_id`.
- [ ] **`SYSTEM_INSTRUCTIONS` dan `AgentService.run`.** Done when: `pytest tests/test_agent_reliability.py` hijau, termasuk batas turn, tool call, dan citation validation.
- [ ] **`src/api.py` (8 endpoint dan problem detail).** Done when: `pytest -m "not live"` hijau seluruhnya.

Pertanyaan pemandu:

- `tests/test_api.py:11` mengharapkan 401 tanpa token. Apa perilaku default `HTTPBearer` di versi FastAPI yang terpasang?
- `balance-other-007` melarang string `EMP-002` muncul. Bagaimana menolak permintaan tanpa mengulang ID itu?
- `store=False` dan `ModelTurn.output_items`: bagaimana percakapan tool dilanjutkan tanpa state di provider?
- Field apa saja yang dibaca `app.py` dari `/monitoring/summary`? Kontraknya tidak tertulis di brief.

## Tahap 4 — PostgreSQL dan indexing nyata

Butuh K5 untuk embedding sungguhan.

- [ ] **Setup Docker dan `.env`.** Done when: Docker Desktop hidup, `.env` terisi, dan `docker compose up -d postgres redis` keduanya `healthy`.
- [ ] **Schema dan constraint di `src/setup_lab.py`.** Done when: tabel lengkap, `status` ber-constraint, token tersimpan sebagai hash.
- [ ] **Seed idempotent.** Done when: `python -m src.setup_lab` dua kali tidak menduplikasi data dan `--reset` tersedia.
- [ ] **`PostgresRepository`.** Done when: tidak ada interpolasi input ke SQL dan konfirmasi berjalan dalam transaksi dengan row lock.
- [ ] **Full-text + pgvector.** Done when: Checkpoint 2 terpenuhi (“jatah cuti tahunan” menemukan `HR-LEAVE-001` di top 3 dengan metadata lengkap).

Pertanyaan pemandu:

- PostgreSQL tidak punya konfigurasi text search Bahasa Indonesia bawaan. Konfigurasi apa yang dipakai, dan apa konsekuensinya?
- Query “jatah cuti tahunan” pada `websearch_to_tsquery` menggabungkan kata dengan AND. Apa hasilnya bila `jatah` tidak ada di dokumen?
- Dua proposal dengan tanggal sama, keduanya dikonfirmasi. Di mana overlap harus dicek ulang?
- Brief menguji “versi kebijakan usang”. Bagaimana sistem memilih versi berlaku?

## Tahap 5 — Provider live dan Docker

- [ ] **`OpenAIProvider`.** Done when: `store=False`, strict schema, hashed `safety_identifier`, retry terbatas, usage tercatat.
- [ ] **`Dockerfile`.** Done when: image non-root terbangun tanpa API key, dan `whoami` di container bukan `root`.
- [ ] **Urutan `docker-delivery.md` dari checkout bersih.** Done when: seed, API, UI, dan `pytest -m "not live"` di container lulus; `/readyz` mengembalikan `ready`.
- [ ] **Checkpoint 3.** Done when: Streamlit menjawab kebijakan dan saldo, dan Bima tidak bisa membaca trace Alya.
- [ ] **Checkpoint 4.** Done when: sebelum konfirmasi tidak ada request, dan konfirmasi ganda dengan key sama menghasilkan request ID yang sama.

Pertanyaan pemandu:

- TODO Dockerfile tidak menyebut `pyproject.toml`. Apakah pytest di container butuh file itu?
- User non-root harus bisa menulis ke mana? Lihat perintah `docker compose cp api:/app/outputs` dan kebutuhan `HOME` Streamlit.
- `docker-compose.yml` hanya meneruskan env tertentu. Variabel `.env` mana yang tidak sampai ke container API?

## Tahap 6 — Evaluasi dan monitoring

- [ ] **Telemetry dan redaction.** Done when: trace tanpa prompt mentah/chain-of-thought dan tes kebocoran `diabetes` lulus.
- [ ] **`/monitoring/summary` dan `/monitoring/alerts`.** Done when: alert memakai `data/monitoring_rules.json` dan menghormati `minimum_samples`.
- [ ] **`src/run_evaluation.py`.** Done when: 15 kasus berjalan dan `outputs/evaluation_report.json` memuat metrik plus GO/NO-GO.
- [ ] **Regression case overlap (tugas assessment).** Done when: case, expected, actual, trace ID, dan keputusan lulus/gagal terkumpul.
- [ ] **Perbaiki kegagalan evaluasi.** Done when: semua target rilis tercapai; acceptance assertion tidak dilonggarkan.
- [ ] **Uji kegagalan.** Done when: model, PostgreSQL, dan Redis mati masing-masing berakhir aman tanpa side effect tambahan.

Pertanyaan pemandu:

- `medical-pii-012` melarang `diabetes`. Apakah cukup disamarkan di trace, atau perlu sebelum dikirim ke provider?
- Isi `reason` dan ringkasan tiket juga masuk database. Apakah keduanya melewati redaction?

## Tahap 7 — Governance, dokumentasi, dan demo

- [ ] **Diagram final dan ADR.** Done when: `architecture.md` memuat semua elemen wajib dan keputusan RAG vs fine-tuning vs multi-agent.
- [ ] **`templates/evaluation-report.md` dan `risk-register.csv`.** Done when: semua risiko punya owner, mitigation, dan evidence nyata.
- [ ] **8 soal `assessment.md`.** Done when: tiap jawaban merujuk kode atau test.
- [ ] **Screenshot dan backup output.** Done when: UI, monitoring, dan hasil test tersimpan tanpa secret.
- [ ] **Demo 5–7 menit.** Done when: latihan dua kali dengan timer, mencakup happy, blocked, dan failure path.
- [ ] **Uji akhir dari checkout bersih.** Done when: clone baru lulus `submission-checklist.md`.

Buffer: Jika tertinggal, potong stretch goal dan polish lebih dulu. Jangan potong hard gate, evaluator, atau Docker.

## Jadwal

Sisa kerja sampai Tahap 6 diperkirakan sekitar 11 jam, dan waktu Senin–Jumat juga 11 jam. Jadwal ini tidak punya cadangan, jadi waktu Sabtu dan Minggu adalah bonus.

**Target 13 November:** sistem utuh berjalan di Docker dengan model asli, dan evaluator versi awal sudah bisa dijalankan. Perbaikan hasil evaluasi berlanjut pada 14–15 November.

| Tanggal | Waktu | Target |
|---|---|---|
| Sabtu, 7 Nov | 0–30 menit | Commit dokumen dan `business_days`. Boleh dilewati. |
| Minggu, 8 Nov | Bonus jika ada waktu | Lanjutan `src/domain.py`. |
| Senin, 9 Nov | 3 jam, 04:00–07:00 | Kode Tahap 1 selesai, `MemoryRepository` selesai. |
| Selasa, 10 Nov | 2 jam | Cache, `DeterministicProvider`, `chunk_policy`, `RetrievalService`, dan awal `tools.py`. Test retrieval hijau. |
| Rabu, 11 Nov | 2 jam | Sisa `tools.py`, `agent.py`, dan `api.py`. `pytest -m "not live"` hijau. |
| Kamis, 12 Nov | 2 jam | Docker dan `.env`, `setup_lab.py`, `PostgresRepository`. Checkpoint 2 lulus. |
| Jumat, 13 Nov | 2 jam | `OpenAIProvider`, `Dockerfile`, evaluator versi awal. Chat dengan model asli berjalan di Docker. |
| Sabtu–Minggu, 14–15 Nov | Fleksibel | Sisa Tahap 6: perbaikan evaluasi, telemetry, monitoring, uji kegagalan. Plus project brief dan diagram. |
| Senin–Kamis, 16–19 Nov | Fleksibel | Sisa Tahap 7, review, latihan presentasi Bahasa Inggris. |
| Jumat, 20 Nov | | Pengumpulan. |

Jika tertinggal, urutan yang dipertahankan: alur Python utuh, PostgreSQL dan model asli, Docker, lalu evaluasi. Tanggal 14–15 November menjadi cadangan pertama.

## Rencana Senin, 9 November (04:00–07:00)

| Waktu | Aktivitas | Output |
|---|---|---|
| 04:00–04:10 | Baca `TODO.md`, pastikan dokumen sudah ter-commit. | Siap mulai. |
| 04:10–04:55 | TDD `src/domain.py`, termasuk aturan K3. | `tests/test_domain.py` hijau. |
| 04:55–05:20 | TDD `src/security.py`. | Test redaction hijau. |
| 05:20–05:30 | Istirahat. | |
| 05:30–06:45 | Implementasi `MemoryRepository`, mulai dari yang dibutuhkan `tests/test_actions.py`. | `tests/test_actions.py` hijau. |
| 06:45–07:00 | Commit, centang TODO, catat blocker. | Sesi tertutup. |

Jika tertinggal, pertahankan `domain.py` dan `security.py`. `MemoryRepository` boleh berlanjut ke sesi berikutnya.

## Progress log

| Tanggal | Selesai | Blocker | Berikutnya |
|---|---|---|---|
| 2026-11-05 | Analisis dokumentasi dan planning; setup Python dan git baseline; preflight test. | K1, K2, K4, dan K5 masih terbuka. Tahap 1 belum selesai, sisanya dibawa ke sesi berikutnya. | Selesaikan `business_days`, lalu sisa task Tahap 1. |
| 2026-11-06 | Jadwal diperbarui: target 13 Nov, deadline 20 Nov. K1 diputuskan, K5 selesai. Belum ada kode baru. | K2 masih terbuka. | `business_days` jika ada waktu Sabtu, atau mulai Senin 04:00. |
