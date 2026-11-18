# Asisten Kebijakan HR dan Cuti (Milestone P2M2)

Backend FastAPI untuk UI Streamlit yang disediakan. Pegawai perusahaan fiktif Nusantara Digital dapat:

- menanyakan kebijakan HR dan mendapat jawaban bersitasi dari dokumen kebijakan;
- melihat saldo cutinya sendiri;
- menyiapkan proposal cuti, yang baru menjadi permintaan `pending_manager_review` sesudah pengguna menekan konfirmasi;
- membuat tiket HR sesudah menjawab "ya" secara eksplisit.

Fitur tambahan: manajer dapat melihat ringkasan cuti tim langsungnya, yaitu siapa yang cuti, pengajuan yang menunggu, dan hari dengan banyak anggota tim cuti. Data tim lain tidak terlihat.

Semua persona dan data bersifat sintetis. Tidak ada tool atau endpoint yang menyetujui cuti; persetujuan tetap dilakukan manusia.

## Arsitektur singkat

```
Streamlit (app.py) ──HTTP + bearer token──▶ FastAPI (src/api.py)
                                              │
                    identitas dari token ─────┤
                                              ▼
                              Agent loop (src/agent.py, LangChain)
                                │  maks. 4 turn, 6 tool call
                                ▼
                    Tool (src/tools.py) ── identitas selalu dari token
                    │                       │
        Hybrid retrieval              PostgreSQL + pgvector
        (lexical + vector,            (role hr_api, row-level security,
         RRF + rerank)                 status hanya pending_manager_review)
                    │
                  Redis (cache; boleh mati, sistem tetap jalan)
```

Diagram lengkap (trust boundary, alur konfirmasi, failure path, indexing, evaluasi) dan ADR ada di [templates/architecture.md](templates/architecture.md).

| Komponen | File utama |
|---|---|
| API, autentikasi, problem detail | `src/api.py` |
| Agent loop, validasi sitasi, output guard | `src/agent.py`, `src/lc_agent.py`, `src/lc_model.py`, `src/grounding.py` |
| Lima tool: `search_hr_policy`, `get_my_leave_balance`, `prepare_leave_request`, `create_hr_ticket`, `get_team_leave_analytics` | `src/tools.py` |
| Aturan cuti (hari kerja, overlap, saldo, minimal 3 hari kerja untuk cuti tahunan) | `src/domain.py` |
| Repository PostgreSQL dan in-memory, transaksi konfirmasi | `src/repository.py` |
| Chunking, indexing, hybrid retrieval | `src/retrieval.py`, `src/setup_lab.py` |
| Penyamaran PII, hash token | `src/security.py` |
| Telemetry dan alert | `src/monitoring.py` |
| Evaluator live | `src/run_evaluation.py`, `evaluation/` |

## Menjalankan dengan Docker (cara penilaian)

Yang dibutuhkan hanya Docker Engine dan Docker Compose, tanpa Python di host. Kontrak lengkapnya ada di [docker-delivery.md](docker-delivery.md).

1. Buat `.env` dari contoh, lalu isi `OPENAI_API_KEY`, `AGENT_MODEL`, `EMBEDDING_MODEL`, dan `EMBEDDING_DIMENSIONS`.

   ```bash
   cp .env.example .env
   ```

   Di PowerShell: `Copy-Item .env.example .env`.

2. Build, seed, jalankan, lalu tes:

   ```bash
   docker compose -p p2m2_demo build api streamlit
   docker compose -p p2m2_demo up -d postgres redis
   docker compose -p p2m2_demo run --rm api python -m src.setup_lab
   docker compose -p p2m2_demo up -d api streamlit
   docker compose -p p2m2_demo run --rm api python -m pytest -m "not live"
   ```

3. Cek:

   | URL | Harapan |
   |---|---|
   | http://localhost:8000/healthz | `status: ok` |
   | http://localhost:8000/readyz | `status: ready` |
   | http://localhost:8000/docs | OpenAPI |
   | http://localhost:8501 | UI Streamlit |

4. Evaluasi live dan ekspor laporannya:

   ```bash
   docker compose -p p2m2_demo exec -T api python -m src.run_evaluation --base-url http://localhost:8000 --token token-alya --other-token token-bima
   docker compose -p p2m2_demo cp api:/app/outputs ./outputs
   ```

   Hasilnya `outputs/evaluation_report.json` dan `outputs/evaluation_report.md`. Kasus manajer memakai token persona manajer yang tercatat di masing-masing kasus.

Bila startup gagal: `docker compose -p p2m2_demo ps` dan `docker compose -p p2m2_demo logs api`. Bila port host terpakai, ubah `API_PORT`, `STREAMLIT_PORT`, `POSTGRES_PORT`, atau `REDIS_PORT` di `.env`.

## Persona demo

| Persona | Token | Coba |
|---|---|---|
| Alya, pegawai | `token-alya` | "Berapa jatah cuti tahunan?", "Berapa saldo cuti saya?", ajukan cuti tahunan lalu tekan Konfirmasi |
| Bima, pegawai | `token-bima` | "Tampilkan saldo EMP-001" → ditolak, hanya saldo Bima sendiri |
| Monitoring admin | `token-admin` | Metrik, alert, dan trace tersamarkan |
| Sari, manajer Engineering | `token-sari` | "Siapa di tim saya yang cuti antara 2026-12-01 dan 2026-12-05?" |
| Dewi, manajer Finance | `token-dewi` | Pertanyaan yang sama: hanya tim Finance yang terlihat |

Token demo hanya untuk kelas. Database menyimpan hash-nya, bukan token aslinya.

## Endpoint

Semua `/api/v1/` memakai `Authorization: Bearer <token>`.

| Method | Path | Fungsi |
|---|---|---|
| GET | `/healthz` | Liveness, tanpa token |
| GET | `/readyz` | Kesiapan database, index, cache, dan model |
| POST | `/api/v1/chat` | Jawaban, outcome, sitasi, ringkasan tool, proposal opsional, trace ID, usage |
| POST | `/api/v1/action-proposals/{proposal_id}/confirm` | Membuat satu request `pending_manager_review`; key idempotency yang sama tidak membuat duplikat |
| GET | `/api/v1/leave-requests/me` | Request milik pengguna sendiri |
| GET | `/api/v1/traces/{trace_id}` | Trace tersamarkan milik sendiri, atau semua untuk admin |
| GET | `/api/v1/monitoring/summary` | Ringkasan metrik (admin) |
| GET | `/api/v1/monitoring/alerts` | Alert dari `data/monitoring_rules.json` (admin) |

Token salah → 401. Monitoring atau trace orang lain → 403. Proposal milik orang lain → 404. Error dikembalikan sebagai problem detail tanpa stack trace.

## Kontrol keamanan utama

- **Identitas dari token, bukan dari model.** Tidak ada tool yang menerima `employee_id`; argumen sisipan seperti itu ditolak (`blocked`).
- **Row-level security.** API login sebagai `hr_api`, bukan pemilik tabel, dan hanya melihat baris milik identitas di transaksinya: pegawai melihat datanya sendiri, manajer melihat tim langsungnya.
- **Tidak ada side effect tanpa konfirmasi.** Proposal cuti tidak menulis request. Konfirmasi berjalan dalam satu transaksi (lock, cek owner, expiry, overlap, saldo), lalu memotong saldo. Status `approved` ditolak oleh database.
- **Sitasi divalidasi.** Sitasi harus berasal dari retrieval pada run yang sama, dan angka di jawaban harus ada di bukti. Jika tidak, sistem abstain.
- **Privasi.** Pesan disamarkan sebelum dikirim ke provider dan sebelum disimpan. Trace tidak menyimpan prompt mentah. Batas penyamaran medis tercatat di risk register.
- **Kegagalan aman.** Redis mati hanya memperlambat. PostgreSQL atau model mati menghasilkan error yang jelas tanpa side effect tambahan.

## Bukti

| Bukti | Lokasi |
|---|---|
| Laporan evaluasi (metrik, hard gate, GO/NO-GO) | [templates/evaluation-report.md](templates/evaluation-report.md) |
| Screenshot UI dan monitoring, hasil test, backup output evaluasi | [docs/screenshots/](docs/screenshots/README.md) |
| Risk register | [templates/risk-register.csv](templates/risk-register.csv) |
| Project brief | [templates/project-brief.md](templates/project-brief.md) |
| Diagram dan ADR | [templates/architecture.md](templates/architecture.md) |
| Keputusan desain dan alasannya (K1–K36) | [DECISIONS.md](DECISIONS.md) |
| Kasus evaluasi | `data/evaluation_cases.json`, `evaluation/regression_cases.json` |
| Test | `tests/` |

## Pengembangan lokal (opsional)

Untuk pengembangan dengan Python di host (3.11+):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d postgres redis
python -m src.setup_lab --reset
python -m uvicorn src.api:create_app --factory --reload
python -m streamlit run app.py
```

Di Windows: `.\.venv\Scripts\Activate.ps1`. Tes tanpa model: `python -m pytest -m "not live"`. Tes berbasis PostgreSQL dilewati bila database belum menyala dan belum di-seed.

## Batasan

Ini sistem pendidikan dengan data sintetis. Token demo bukan autentikasi produksi, dan penyamaran PII berbasis pola sehingga tidak menangkap semua variasi kalimat medis. Detail risiko sisa ada di risk register.

## Materi milestone

[brief.md](brief.md) · [lab.md](lab.md) · [assessment.md](assessment.md) · [rubric.md](rubric.md) · [submission-checklist.md](submission-checklist.md)
