# TODO — HR Agent (Milestone P2M2)

Panduan kerja utama. Kerjakan satu task pada satu waktu, centang sesudah **Done when** terbukti.

- **Mulai:** Kamis, 5 November 2026
- **Asumsi waktu:** 2 jam per hari selama 7 hari (14 jam). Perlu dikonfirmasi, lihat K4.
- **Status saat ini:** analisis dan planning selesai, implementasi belum dimulai.

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
| K1 | `leave-valid-008` (hard gate) memakai 2–3 Nov 2026, yang sudah lewat. Test membekukan tanggal di 23 Sep 2026, sedangkan server live memakai tanggal sebenarnya. | Tanya instruktur. Jika tidak ada jawaban: `data/` tidak diubah, evaluator mengganti tanggal case ini secara dinamis ke hari kerja mendatang yang lolos aturan K3, dan penyimpangannya dicatat di report. | |
| K2 | `create_hr_ticket` menulis ke database tanpa konfirmasi, padahal rubric melarang side effect tanpa konfirmasi eksplisit. Endpoint confirm hanya mendukung `leave_request`. | Tanya instruktur. Jika tidak ada jawaban: tiket hanya dibuat bila diminta jelas oleh pengguna, ringkasannya disamarkan, dan alasannya dicatat di risk register. | |
| K3 | Kebijakan `HR-LEAVE-001` mewajibkan pengajuan minimal 3 hari kerja sebelumnya, tetapi aturan ini tidak ada di daftar validasi lab/brief. | Terapkan agar jawaban dan perilaku sistem konsisten. Risiko: bisa bertabrakan dengan hidden test. | **Diterapkan** (5 Nov 2026), khusus cuti tahunan. Beri tahu instruktur. |
| K4 | Waktu tersedia pada hari 2–7 belum diketahui. | Pakai 2 jam per hari. | |
| K5 | `.env` belum ada: `OPENAI_API_KEY`, `AGENT_MODEL`, `EMBEDDING_MODEL`, dan `EMBEDDING_DIMENSIONS` harus dari instruktur. | Minta paling lambat Hari 3. Sampai Hari 3 cukup memakai `DeterministicProvider`. | |

## Ringkasan output per hari

| Hari | Fokus | Output sesi ngoding | Output sesi non-ngoding |
|---|---|---|---|
| 1 (Kamis) | Menyiapkan lingkungan, lalu menulis aturan cuti dan penyamaran data. | `src/domain.py` dan `src/security.py` selesai, test-nya hijau. | Docker, `.venv`, dan git siap; peta failure test; project brief; draft diagram trust boundary. |
| 2 (Jumat) | Membuat sistem bisa mencari kebijakan, memakai data tiruan di memori tanpa internet. | `MemoryRepository`, cache, `DeterministicProvider`, `chunk_policy`, dan `RetrievalService` selesai; `test_actions` dan test retrieval hijau. | Tidak ada. |
| 3 (Sabtu) | Menyambungkan tool, agent, dan API, masih memakai model tiruan. | `TOOL_SCHEMAS`, `ToolExecutor`, `AgentService`, dan `src/api.py` selesai; semua `pytest -m "not live"` hijau. | Kredensial model dari instruktur sudah di tangan (K5). |
| 4 (Minggu) | Mengganti data tiruan dengan PostgreSQL dan mengindeks dokumen kebijakan. | `src/setup_lab.py` dan `PostgresRepository` selesai; seed bisa diulang tanpa data ganda. | Checkpoint 2 diperiksa manual lewat query “jatah cuti tahunan”. |
| 5 (Senin) | Memakai model OpenAI sungguhan dan mengemas aplikasi ke Docker. | `OpenAIProvider` dan `Dockerfile` selesai. | Urutan `docker-delivery.md` dijalankan; Checkpoint 3 dan 4 diuji lewat Streamlit. |
| 6 (Selasa) | Mengukur kualitas agent, membuat monitoring, dan memperbaiki yang gagal. | Telemetry, dua endpoint monitoring, `src/run_evaluation.py`, regression case overlap, dan perbaikan bug selesai. | Evaluasi 15 kasus dijalankan; uji model/PostgreSQL/Redis mati; hasilnya dicatat. |
| 7 (Rabu) | Melengkapi bukti dan berlatih demo. Tidak ada fitur baru. | Hanya perbaikan bug jika uji akhir gagal. | Diagram final dan ADR, evaluation report, risk register, 8 soal assessment, screenshot, 2× latihan demo, uji dari clone baru. |

## Hari 1 — Fondasi (Kamis, 2 jam)

Rincian waktu ada di [Execution plan 2 jam](#execution-plan-2-jam-pertama).

- [ ] **Setup lingkungan.** Done when: Docker Desktop hidup, `.venv` aktif, dependency terpasang, `docker compose up -d postgres redis` keduanya `healthy`.
- [ ] **`git init` dan commit awal.** Done when: `git status` bersih dan `.env` tidak ter-track.
- [ ] **Preflight test.** Done when: jumlah pass/fail dicatat dan tiap failure dipetakan ke TODO-nya.
- [ ] **`templates/project-brief.md`.** Done when: semua heading terisi dengan kata-katamu sendiri.
- [ ] **Draft diagram trust boundary.** Done when: Checkpoint 1 terpenuhi (identity flow, confirmation boundary, telemetry, cache degradation, failure path).
- [ ] **`src/domain.py`.** Done when: `pytest tests/test_domain.py` hijau, dan test baru membuktikan aturan minimal 3 hari kerja berlaku untuk cuti tahunan tetapi tidak untuk cuti sakit.
- [ ] **`src/security.py`.** Done when: `test_redaction_covers_sensitive_patterns` hijau.

Pertanyaan pemandu:

- Baca `tests/test_domain.py:39-42`. Argumen dan saldonya sama, tetapi error yang diharapkan berbeda. Apa yang tersirat tentang urutan validasi?
- Mengapa `domain.py` dilarang memanggil model?
- Aturan 3 hari kerja dicek sebelum atau sesudah urutan tanggal? Uji jawabanmu dengan kasus `(date(2026, 9, 25), date(2026, 9, 24))` di `tests/test_domain.py:20`.
- Pola `redact` apa yang mencegah false positive, misalnya menyamarkan semua angka panjang?

## Hari 2 — Data dan retrieval tanpa jaringan (Jumat)

- [ ] **`MemoryRepository`.** Done when: `pytest tests/test_actions.py` hijau.
- [ ] **`ResilientCache` dan `NullCache`.** Done when: ada test tambahan bahwa Redis mati berperilaku seperti cache miss.
- [ ] **`DeterministicProvider`.** Done when: embedding dan respons deterministik, tanpa jaringan.
- [ ] **`chunk_policy`.** Done when: `test_policy_chunk_ids_and_metadata_are_stable` hijau.
- [ ] **`RetrievalService` (RRF + keyword rerank).** Done when: `test_hybrid_retrieval_prefers_lexical_match` hijau.

Pertanyaan pemandu:

- Pada konfirmasi berulang, mana yang harus dicek lebih dulu: idempotency atau expiry? Apa yang terjadi bila pengguna me-retry dengan key yang sama sesudah proposal kedaluwarsa?
- Mengapa versi index harus masuk cache key?
- Kata `jatah`, `WFH`, `probation`, dan `surat dokter` muncul di evaluation case, tetapi tidak ada di dokumen kebijakan. Apa artinya bagi lexical search, dan apa artinya bagi hybrid search?

## Hari 3 — Agent dan API (Sabtu)

- [ ] **`TOOL_SCHEMAS` dan `ToolExecutor`.** Done when: empat tool tervalidasi Pydantic, identitas selalu dari `auth`, dan tidak ada argumen `employee_id`.
- [ ] **`SYSTEM_INSTRUCTIONS` dan `AgentService.run`.** Done when: `pytest tests/test_agent_reliability.py` hijau, termasuk batas turn, tool call, dan citation validation.
- [ ] **`src/api.py` (8 endpoint dan problem detail).** Done when: `pytest -m "not live"` hijau seluruhnya.

Pertanyaan pemandu:

- `tests/test_api.py:11` mengharapkan 401 tanpa token. Apa perilaku default `HTTPBearer` di versi FastAPI yang terpasang?
- `balance-other-007` melarang string `EMP-002` muncul. Bagaimana menolak permintaan tanpa mengulang ID itu?
- `store=False` dan `ModelTurn.output_items`: bagaimana percakapan tool dilanjutkan tanpa state di provider?
- Field apa saja yang dibaca `app.py` dari `/monitoring/summary`? Kontraknya tidak tertulis di brief.

## Hari 4 — PostgreSQL dan indexing nyata (Minggu)

Butuh K5 untuk embedding sungguhan.

- [ ] **Schema dan constraint di `src/setup_lab.py`.** Done when: tabel lengkap, `status` ber-constraint, token tersimpan sebagai hash.
- [ ] **Seed idempotent.** Done when: `python -m src.setup_lab` dua kali tidak menduplikasi data dan `--reset` tersedia.
- [ ] **`PostgresRepository`.** Done when: tidak ada interpolasi input ke SQL dan konfirmasi berjalan dalam transaksi dengan row lock.
- [ ] **Full-text + pgvector.** Done when: Checkpoint 2 terpenuhi (“jatah cuti tahunan” menemukan `HR-LEAVE-001` di top 3 dengan metadata lengkap).

Pertanyaan pemandu:

- PostgreSQL tidak punya konfigurasi text search Bahasa Indonesia bawaan. Konfigurasi apa yang dipakai, dan apa konsekuensinya?
- Query “jatah cuti tahunan” pada `websearch_to_tsquery` menggabungkan kata dengan AND. Apa hasilnya bila `jatah` tidak ada di dokumen?
- Dua proposal dengan tanggal sama, keduanya dikonfirmasi. Di mana overlap harus dicek ulang?
- Brief menguji “versi kebijakan usang”. Bagaimana sistem memilih versi berlaku?

## Hari 5 — Provider live dan Docker (Senin)

- [ ] **`OpenAIProvider`.** Done when: `store=False`, strict schema, hashed `safety_identifier`, retry terbatas, usage tercatat.
- [ ] **`Dockerfile`.** Done when: image non-root terbangun tanpa API key, dan `whoami` di container bukan `root`.
- [ ] **Urutan `docker-delivery.md` dari checkout bersih.** Done when: seed, API, UI, dan `pytest -m "not live"` di container lulus; `/readyz` mengembalikan `ready`.
- [ ] **Checkpoint 3.** Done when: Streamlit menjawab kebijakan dan saldo, dan Bima tidak bisa membaca trace Alya.
- [ ] **Checkpoint 4.** Done when: sebelum konfirmasi tidak ada request, dan konfirmasi ganda dengan key sama menghasilkan request ID yang sama.

Pertanyaan pemandu:

- TODO Dockerfile tidak menyebut `pyproject.toml`. Apakah pytest di container butuh file itu?
- User non-root harus bisa menulis ke mana? Lihat perintah `docker compose cp api:/app/outputs` dan kebutuhan `HOME` Streamlit.
- `docker-compose.yml` hanya meneruskan env tertentu. Variabel `.env` mana yang tidak sampai ke container API?

## Hari 6 — Evaluasi dan monitoring (Selasa)

- [ ] **Telemetry dan redaction.** Done when: trace tanpa prompt mentah/chain-of-thought dan tes kebocoran `diabetes` lulus.
- [ ] **`/monitoring/summary` dan `/monitoring/alerts`.** Done when: alert memakai `data/monitoring_rules.json` dan menghormati `minimum_samples`.
- [ ] **`src/run_evaluation.py`.** Done when: 15 kasus berjalan dan `outputs/evaluation_report.json` memuat metrik plus GO/NO-GO.
- [ ] **Regression case overlap (tugas assessment).** Done when: case, expected, actual, trace ID, dan keputusan lulus/gagal terkumpul.
- [ ] **Perbaiki kegagalan evaluasi.** Done when: semua target rilis tercapai; acceptance assertion tidak dilonggarkan.
- [ ] **Uji kegagalan.** Done when: model, PostgreSQL, dan Redis mati masing-masing berakhir aman tanpa side effect tambahan.

Pertanyaan pemandu:

- `medical-pii-012` melarang `diabetes`. Apakah cukup disamarkan di trace, atau perlu sebelum dikirim ke provider?
- Isi `reason` dan ringkasan tiket juga masuk database. Apakah keduanya melewati redaction?

## Hari 7 — Governance, dokumentasi, dan demo (Rabu)

- [ ] **Diagram final dan ADR.** Done when: `architecture.md` memuat semua elemen wajib dan keputusan RAG vs fine-tuning vs multi-agent.
- [ ] **`templates/evaluation-report.md` dan `risk-register.csv`.** Done when: semua risiko punya owner, mitigation, dan evidence nyata.
- [ ] **8 soal `assessment.md`.** Done when: tiap jawaban merujuk kode atau test.
- [ ] **Screenshot dan backup output.** Done when: UI, monitoring, dan hasil test tersimpan tanpa secret.
- [ ] **Demo 5–7 menit.** Done when: latihan dua kali dengan timer, mencakup happy, blocked, dan failure path.
- [ ] **Uji akhir dari checkout bersih.** Done when: clone baru lulus `submission-checklist.md`.

Buffer: Jika tertinggal, potong stretch goal dan polish lebih dulu. Jangan potong hard gate, evaluator, atau Docker.

## Execution plan 2 jam pertama

| Waktu | Aktivitas | Output |
|---|---|---|
| 0:00–0:20 | Hidupkan Docker Desktop, buat `.venv`, install dependency, `Copy-Item .env.example .env`, jalankan `postgres` dan `redis`, `git init`, commit awal. | Lingkungan siap, baseline ter-commit. |
| 0:20–0:35 | Jalankan `python -m pytest -m "not live"`. Kelompokkan failure berdasarkan TODO. | Peta failure di Progress log. |
| 0:35–1:05 | Isi project brief. Gambar trust boundary: user input, retrieved text, model output, tool, storage. | Brief dan draft diagram, direview mentor. |
| 1:05–1:35 | TDD `src/domain.py`: `business_days`, `validate_leave_request`, `estimate_cost`. | `tests/test_domain.py` hijau. |
| 1:35–1:55 | TDD `src/security.py`: `token_hash`, `stable_safety_id`, `redact`. | Test redaction hijau. |
| 1:55–2:00 | Commit, centang TODO, catat blocker dan pertanyaan untuk instruktur. | Hari 1 tertutup. |

Jika setup melebihi 0:35, potong sesi diagram jadi 15 menit dan lanjutkan sisanya besok. Prioritaskan `domain.py`, karena test-nya bisa jalan tanpa Docker dan API key.

## Progress log

| Tanggal | Selesai | Blocker | Berikutnya |
|---|---|---|---|
| 2026-11-05 | Analisis dokumentasi dan planning. | Docker daemon belum berjalan; `.env` dari instruktur belum ada; K1, K2, K4, dan K5 terbuka. | Mulai setup Hari 1. |
