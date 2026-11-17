# Catatan Fitur Analisis Tim (Manajer)

Catatan kerja untuk satu fitur tambahan: analisis cuti tim untuk role manajer, plus pengaman di database (RLS). Semua keputusan, perubahan, dampak, dan hal yang harus diuji ulang dicatat di sini.

- **Dibuat:** 17 November 2026
- **Status:** rancangan, belum ada kode
- **Deadline pengumpulan:** 20 November 2026
- **Aturan mentor:** boleh menambah data dan fitur, asalkan semua yang sudah ada tetap berjalan dan tidak ada yang berkurang.

Tanda status di bawah: **[SEPAKAT]** sudah diputuskan, **[USULAN]** belum disepakati, **[TERBUKA]** perlu diputuskan.

---

## 1. Kemampuan fitur

### 1.1 Yang bisa dilakukan manajer [SEPAKAT]

Satu tool: `get_team_leave_analytics(metric, start_date, end_date)`.

| Metrik | Pertanyaan manajer | Isi hasil tool |
|---|---|---|
| `team_absence` | "Siapa di tim saya yang cuti minggu depan?" | Ukuran tim, dan cuti yang beririsan dengan periode: nama, jenis cuti, tanggal mulai dan selesai, jumlah hari kerja, status |
| `pending_queue` | "Pengajuan tim saya yang masih menunggu, mana yang paling lama?" | Pengajuan pending: nama, jenis cuti, tanggal, tanggal diajukan, sudah berapa hari menunggu. Urut dari yang paling lama. |
| `coverage_risk` | "Hari apa yang lebih dari 30% tim saya cuti?" | Ukuran tim, ambang 30%, dan hari kerja yang jumlah orang cutinya ≥ 30%: tanggal, jumlah orang, persentase (bilangan bulat), nama |

### 1.2 Aturan [SEPAKAT kecuali ditandai]

- Tim diambil dari token: pegawai yang `manager_id`-nya sama dengan `auth.employee_id`. Tool **tidak menerima** argumen "tim siapa".
- Role diperiksa di handler tool. Bukan manajer → `blocked`.
- Manajer **boleh** melihat jenis cuti.
- Manajer **tidak boleh** melihat: alasan cuti, saldo anggota, ID pegawai (hanya nama, supaya `guard_output` tidak perlu diubah).
- Agent **tidak bisa** menyetujui atau menolak cuti.
- Status yang dihitung "cuti": `pending_manager_review` dan `approved`. `cancelled` tidak dihitung.
- Hari kerja: Senin sampai Jumat, sama dengan `business_days`.
- Semua angka (jumlah, persentase, hari menunggu) dihitung tool, supaya lolos pemeriksaan angka.
- Manajer sendiri tidak dihitung sebagai anggota timnya. Contoh: 2 dari 4 bawahan cuti = 50%. **[SEPAKAT]**
- Rentang tanggal maksimal 31 hari, supaya daftar hasil, token, dan waktu jawaban tidak membengkak. **[SEPAKAT]**
- Untuk `pending_queue`, `start_date` dan `end_date` diisi `null`. **[USULAN]**

### 1.3 Yang tidak termasuk

- Persetujuan atau penolakan cuti.
- Analisis lintas tim, per departemen, atau untuk HR.
- Endpoint API baru. Fitur ini masuk lewat `/api/v1/chat`.

---

## 2. Data [SEPAKAT]

| ID | Nama | Role | Tim | Atasan (`manager_id`) |
|---|---|---|---|---|
| EMP-001 | Alya (sudah ada) | employee | Engineering | EMP-010 |
| EMP-002 | Bima (sudah ada) | employee | Engineering | EMP-010 |
| EMP-010 | Sari | manager | Engineering | — |
| EMP-011, EMP-012 | pegawai baru | employee | Engineering | EMP-010 |
| EMP-020 | Dewi | manager | Finance | — |
| EMP-021 s.d. EMP-023 | pegawai baru | employee | Finance | EMP-020 |

- Saldo dan riwayat Alya dan Bima **tidak diubah**. Yang ditambahkan untuk mereka hanya `department` dan `manager_id`.
- Riwayat cuti baru hanya untuk pegawai baru, disusun supaya ada hari dengan ≥ 30% tim cuti.
- Nama, token, dan tanggal riwayat: **[TERBUKA]**, ditentukan saat menulis data.

### Persona UI [SEPAKAT: file persona terpisah]

Test mentor `tests/test_supplied_ui.py` mengunci `demo_personas.json` persis berisi EMP-001, EMP-002, ADM-001, jadi file itu **tidak disentuh**.

- Persona manajer ditaruh di file baru, misalnya `demo_personas_team.json`, dengan format yang sama (`employee_id`, `label`, `scenario`, `demo_token`), sehingga divalidasi oleh `load_personas` milik mentor.
- `app.py:31` diubah sekitar 2-3 baris: isi file baru ditambahkan ke daftar persona **kalau file itu ada**. Kalau file dihapus, UI kembali persis seperti aslinya.
- Yang berubah di UI hanya isi dropdown "Persona demo". Tab, tombol, dan kontrak API tidak berubah.
- Manajer di tab Permintaan Cuti melihat pengajuannya sendiri; di tab Monitoring mendapat 403.

---

## 3. Pengaman di database (RLS) [SEPAKAT: opsi B, rancangan USULAN]

### 3.1 Kondisi sekarang

`src/setup_lab.py:228-233`:
- `api_read ... FOR SELECT ... USING (true)`: akun `hr_api` boleh **membaca semua baris** `leave_requests`.
- `api_insert_pending_only ... FOR INSERT ... WITH CHECK (status = 'pending_manager_review' AND status_set_by = 'assistant')`: akun `hr_api` hanya bisa **menulis** status pending. Ini tetap dipertahankan.

Batas "hanya data milik sendiri" saat ini sepenuhnya dijaga `WHERE employee_id = ...` di setiap query.

### 3.2 Pengertian yang disepakati [SEPAKAT]

- RLS adalah **lapis tambahan** di bawah pengaman kode. Pengaman kode (`WHERE employee_id = ...`, identitas dari token, role dicek di handler) **tetap ada**, tidak ada yang dihapus.
- Tujuannya: kalau suatu saat ada query baru yang lupa memfilter, **database tetap menolak** menampilkan baris orang lain.
- Yang menjalankan aturan RLS: **PostgreSQL**, di setiap query. Yang menulis aturannya: kita, di `setup_lab.py`.
- Database tahu siapa penggunanya dari `app.employee_id`, yang **diisi oleh kode kita di satu tempat** (helper di 3.3), dari `AuthContext` hasil token. Tidak pernah dari model atau isi pesan.
- **Gagal tertutup** adalah pilihan kita di aturan RLS: `current_setting('app.employee_id', true)` bernilai kosong kalau belum diisi, sehingga tidak ada baris yang terlihat.

### 3.3 Rancangan [USULAN]

1. **Satu helper** di `PostgresRepository`, berbentuk method dengan `@contextmanager` (dari `contextlib`):
   - pinjam koneksi dari pool, mulai transaksi;
   - isi identitas dengan `SELECT set_config('app.employee_id', %s, true)` (`true` = hanya untuk transaksi ini, tidak terbawa ke pengguna berikutnya di koneksi yang sama). `SET LOCAL` tidak bisa memakai parameter, jadi pakai `set_config`;
   - `yield` koneksi;
   - setelah blok `with` selesai, transaksi ditutup dan identitas hilang.
2. **Semua** query ke tiga tabel inti (3.4) wajib lewat helper ini. Query yang lupa akan mengembalikan kosong, sehingga test kontrak di PostgreSQL langsung gagal. Kelalaian terlihat saat test, bukan diam-diam.
3. Helper menerima `employee_id: str`, dan method repository tetap menerima `employee_id: str` (lihat 3.6). **[SEPAKAT]**

### 3.4 Tabel yang diberi RLS [SEPAKAT: tiga tabel inti]

| Tabel | Pegawai melihat | Manajer melihat | Ditulis oleh API |
|---|---|---|---|
| `leave_balances` | Miliknya sendiri | Miliknya sendiri (tidak boleh melihat saldo anggota) | Ya: potong saldo saat konfirmasi |
| `action_proposals` | Miliknya sendiri | Miliknya sendiri | Ya: simpan proposal, isi `confirmed_at` |
| `leave_requests` | Miliknya sendiri | Miliknya sendiri **+ bawahan langsung** | Ya: buat pengajuan pending |

Aturan per tabel **[USULAN]**:
- `leave_balances`: baca dan ubah hanya `employee_id = current_setting('app.employee_id', true)`. Trigger yang mencegah API menaikkan saldo tetap berlaku.
- `action_proposals`: baca, tulis, dan ubah hanya baris sendiri. Efek samping: proposal orang lain tidak terlihat, jadi konfirmasi proposal orang lain tetap dijawab 404 seperti sekarang.
- `leave_requests`:
  ```sql
  -- baca
  USING (
    employee_id = current_setting('app.employee_id', true)
    OR employee_id IN (SELECT employee_id FROM employees
                       WHERE manager_id = current_setting('app.employee_id', true))
  )
  -- tulis: aturan lama tetap (status pending, dibuat assistant) + baris milik sendiri
  WITH CHECK (status = 'pending_manager_review' AND status_set_by = 'assistant'
              AND employee_id = current_setting('app.employee_id', true))
  ```
  Pegawai biasa tidak punya bawahan, jadi bagian kedua aturan baca selalu kosong untuk mereka.

Yang sengaja **tidak** diberi RLS di versi ini:

| Tabel | Alasan |
|---|---|
| `employees` | Dibaca saat login, sebelum identitas diketahui |
| `policy_chunks` | Kebijakan boleh dibaca semua pegawai |
| `traces` | Monitoring admin membaca semua trace; butuh pengecualian role. Bisa menyusul. |
| `hr_tickets` | API hanya menulis, tidak pernah membaca |

### 3.5 Yang wajib dibuktikan setelah RLS aktif

`confirm_proposal` memakai ketiga tabel dalam satu transaksi, dan beberapa pengecekannya bertanya "apakah sudah ada?" (bentrok di repository.py:509, replay di :491, key di :500). Kalau barisnya tidak terlihat, jawabannya menjadi "belum ada". Dengan helper di 3.3 hal ini tertutup, tapi wajib dibuktikan dengan test: konfirmasi ganda, bentrok, replay, dan key yang dipakai ulang **tetap ditolak** di PostgreSQL sungguhan dengan RLS aktif.

Constraint `EXCLUDE` untuk bentrok di level database: **tidak dipakai** di versi ini, supaya tetap sederhana. [SEPAKAT]

### 3.6 Bentuk parameter: AuthContext utuh vs employee_id [SEPAKAT: A, tetap `employee_id`]

Keputusan: tanda tangan method repository **tidak berubah** (`employee_id: str`). Helper hanya mengisi `app.employee_id`. Test mentor tetap hijau. Riwayat pertimbangannya di bawah.

Keputusan awal: method repository menerima `AuthContext` utuh. **Ternyata bertentangan dengan aturan mentor**: test milik mentor memanggil repository dengan string, misalnya

- `tests/test_actions.py:24-46`: `repository.save_proposal("EMP-001", ...)`, `repository.confirm_proposal("EMP-001", "AP-TEST", ...)`, `repository.list_leave_requests("EMP-001")`
- `tests/test_agent_reliability.py:57`: `repository.list_leave_requests("EMP-001")`

Kalau tanda tangan method diubah menjadi `AuthContext`, kedua file test mentor ini gagal.

Temuan yang mengubah alasan awal: aturan RLS di 3.4 **tidak butuh role**. Manajer dikenali dari hubungan `manager_id` di tabel `employees`: pegawai biasa tidak punya bawahan, jadi tidak melihat baris tambahan. Role tetap dicek di handler tool (lapis kode).

Pilihan:
- **A.** Tanda tangan tetap `employee_id: str`. Helper hanya mengisi `app.employee_id`. Test mentor tetap hijau.
- **B.** Tambah method baru yang menerima `AuthContext`, method lama tetap ada. Dua jalur untuk hal yang sama.
- **C.** Ganti ke `AuthContext` dan ubah test mentor. Melanggar aturan mentor.

### 3.7 Yang tidak terdampak RLS

- Seed di `setup_lab.py`: login sebagai `hr_app` (pemilik tabel), yang melewati RLS.
- Trigger pengembalian saldo saat status dibatalkan: dijalankan oleh sistem HR, bukan `hr_api`.
- `MemoryRepository`: tidak punya RLS. Aturannya harus ditiru di kode supaya test kontrak tetap setara.

---

## 4. Daftar perubahan per file

| File | Perubahan | Milik mentor? |
|---|---|---|
| `src/setup_lab.py` | Kolom `department`, `manager_id`; role `manager` di constraint; RLS baru; seed pegawai baru dan riwayatnya (lewat `ALTER`, tanpa `--reset`) | Tidak |
| `data/employees.json` | Tambah pegawai baru; tambah `department` dan `manager_id` | **Ya** (menambah saja) |
| `data/historical_requests.json` | Tambah riwayat pegawai baru | **Ya** (menambah saja) |
| `src/contracts.py` | Role `manager` di `AuthContext`; argumen tool baru | Sebagian (model Pydantic disediakan mentor) |
| `src/repository.py` | Helper identitas; semua query ke tiga tabel inti lewat helper; query tim; versi `MemoryRepository` meniru aturan yang sama | Tidak |
| `src/tools.py` | Schema, argumen, handler `_get_team_leave_analytics` | Tidak |
| `src/agent.py` | Blok prompt khusus manajer; penanganan cabang `action_not_performed` (lihat 6.1) | Tidak |
| `demo_personas_team.json` (baru) | Persona Sari dan Dewi | Tidak |
| `app.py` | Sekitar 2-3 baris di baris 31: baca file persona tim kalau ada | **Ya** (menambah saja) |
| `tests/` | Test baru (bagian 7) | Tidak |
| `evaluation/regression_cases.json` | Kasus manajer | Tidak |
| `DECISIONS.md`, `TODO.md`, `templates/risk-register.csv`, `templates/architecture.md`, laporan evaluasi | Catat keputusan, risiko, diagram | Tidak |

Yang **tidak** diubah: `lc_agent.py`, `lc_model.py`, `providers.py`, `retrieval.py`, `api.py`, `demo_personas.json`, `data/evaluation_cases.json`, test milik mentor.

---

## 5. Bagian lama yang terdampak

| Bagian | Kenapa terdampak | Risiko |
|---|---|---|
| Query `leave_requests` di `PostgresRepository` (repository.py:376, 389, 448, 491, 500, 509, 531) | Harus lewat helper identitas | Bagian 3.5 |
| Query `leave_balances` (`get_balances` :317, potong saldo di `confirm_proposal` :511-524) | Harus lewat helper identitas | Saldo tampak kosong kalau lupa |
| Query `action_proposals` (`save_proposal` :412, `get_proposal` :437, `confirm_proposal` :479, :541) | Harus lewat helper identitas | Proposal tampak tidak ada kalau lupa |
| `confirm_proposal` | Memakai ketiga tabel dalam satu transaksi dengan kunci | Paling berisiko, paling wajib diuji ulang |
| Pemanggil method repository: `tools.py` (5 panggilan), `api.py` (2), `test_actions.py` dan `test_agent_reliability.py` milik mentor, `test_repository_contract.py`, `test_tools.py`, `test_agent.py` | **Tidak berubah**, karena tanda tangan method tetap (3.6) | Tetap harus hijau setelah RLS aktif |
| `MemoryRepository` membaca `employees.json` lewat `AuthContext.model_validate` | Baris role `manager` ditolak sampai `contracts.py` diubah | Semua test error sementara. Urutan kerja: ubah `contracts.py` dulu. |
| Prompt aturan 4 | Bertentangan dengan tool tim | Blok manajer hanya untuk role manajer. Prompt pegawai biasa tidak boleh berubah. |
| `is_leave_action_request` + cabang `action_not_performed` | Pertanyaan manajer bertanggal ("siapa yang ambil cuti 2026-12-01 ...") dikenali sebagai permintaan cuti | Jawaban benar dilabeli `abstained` |
| `test_repository_contract.py`, `test_database_guards.py` | Login sebagai `hr_api`, jadi terkena RLS | Harus disesuaikan tanpa melonggarkan apa yang diuji |
| Evaluasi 17 kasus | Alur saldo, proposal, dan konfirmasi berubah di level database | Wajib diulang |

---

## 6. Jebakan yang sudah diketahui

1. **`action_not_performed` salah memicu.** Usulan: cabang itu dilewati kalau tool tim dipanggil dengan status `ok`. Dibuktikan dengan test dulu. **[USULAN]**
2. **Test persona mentor.** Diselesaikan dengan file persona terpisah (bagian 2). `demo_personas.json` tidak boleh disentuh.
3. **`AuthContext.role`** hanya menerima `employee` dan `monitoring_admin`.
4. **"Minggu depan" harus diubah model menjadi tanggal.** Prompt sudah memuat tanggal hari ini.
5. **Pemeriksaan angka.** Persentase dan jumlah hari harus ada di hasil tool. Model tidak boleh menghitung.
6. **`guard_output`** menyamarkan semua ID pegawai lain. Hasil tool memakai nama.
7. **`set_config` vs `SET LOCAL`.** Lihat 3.2. Perlu dicek bahwa nilai bertahan sepanjang blok `pool.connection()`.

---

## 7. Yang harus diuji

### 7.1 Test baru

| Test | Harapan |
|---|---|
| Manajer melihat timnya (`team_absence`, `pending_queue`, `coverage_risk`) | Isi sesuai data seed, angka sama dengan hitungan manual |
| Manajer A meminta tim B | Kosong atau ditolak |
| Pegawai biasa memanggil tool tim | `blocked` |
| Pegawai mengaku manajer di pesan | Ditolak, role dari token |
| Argumen `employee_id` / `manager_id` sisipan | Ditolak (`blocked`) |
| Hasil tool tidak memuat alasan cuti, saldo, atau ID | Lulus |
| Pertanyaan manajer bertanggal | Bukan `abstained` |
| RLS: `hr_api` tanpa identitas membaca `leave_requests` | 0 baris |
| RLS: pegawai membaca baris pegawai lain | 0 baris |
| RLS: manajer membaca baris bawahan | Terlihat |
| RLS: manajer membaca baris tim lain | 0 baris |
| RLS: konfirmasi ganda, bentrok, replay, key dipakai ulang | **Tetap ditolak** setelah RLS aktif |
| RLS: `hr_api` menulis `approved` | Tetap ditolak |

### 7.2 Uji ulang setelah fitur selesai

- [ ] `pytest -m "not live"`: semua hijau, termasuk 8 file test mentor
- [ ] `setup_lab` dijalankan dua kali di database yang sudah ada (tanpa `--reset`): tidak error, tidak ada duplikat
- [ ] `setup_lab` di database kosong (stack terpisah `-p`)
- [ ] Evaluasi 17 kasus lama di stack terpisah: tetap GO
- [ ] Kasus evaluasi manajer baru: lulus
- [ ] Tes manual dari `test-cases-eksplorasi.xlsx`, ditambah kasus manajer
- [ ] Alur Docker dari `docker-delivery.md` dari checkout bersih
- [ ] UI: persona lama tetap berfungsi; persona manajer (kalau ada) berfungsi

---

## 8. Keputusan terbuka

| # | Keputusan | Pilihan |
|---|---|---|
| 1 | Nama, token, dan riwayat pegawai baru | Ditentukan saat menulis data |

---

## 10. Urutan pengerjaan [SEPAKAT]

Prinsip: setiap langkah bisa diuji sendiri, dan aplikasi tetap berjalan di akhir setiap langkah. `pytest -m "not live"` harus hijau sebelum lanjut ke langkah berikutnya.

| Langkah | Isi | Bukti selesai |
|---|---|---|
| 0 | Commit perubahan yang masih menggantung, lalu buat branch baru untuk fitur ini | `git status` bersih di branch baru |
| 1 | `contracts.py`: tambah role `manager` di `AuthContext`. Harus **sebelum** data pegawai baru, karena `MemoryRepository` membaca `employees.json` lewat `AuthContext`. | Semua test hijau |
| 2 | Schema: kolom `department` dan `manager_id`, role `manager` di constraint (lewat `ALTER`). Data: pegawai baru dan riwayatnya di `employees.json` dan `historical_requests.json`. | `setup_lab` dua kali tanpa error dan tanpa duplikat; data Alya dan Bima tidak berubah; semua test hijau |
| 3 | Helper `_as_user` di `PostgresRepository`, lalu semua query ke tiga tabel inti dipindah lewat helper. **RLS belum diaktifkan** (`USING (true)` masih berlaku), jadi perilaku tidak berubah. | Semua test hijau |
| 4 | Aktifkan aturan RLS di tiga tabel inti. Dipisah dari langkah 3, supaya kalau ada yang rusak, penyebabnya jelas: aturan RLS, bukan pemindahan query. | Test RLS baru (bagian 7.1) hijau, dan semua test lama tetap hijau, termasuk konfirmasi ganda, bentrok, dan replay |
| 5 | Query tim di `PostgresRepository` dan `MemoryRepository`, beserta test kontrak | Kontrak memori = PostgreSQL |
| 6 | Tool `get_team_leave_analytics` di `tools.py`: schema, argumen, handler dengan cek role | `test_tools.py`: hasil benar, non-manajer `blocked`, argumen sisipan ditolak, tanpa alasan/saldo/ID |
| 7 | `agent.py`: blok prompt khusus manajer, dan penanganan cabang `action_not_performed` | `test_agent.py`: pertanyaan manajer bertanggal tidak `abstained`; prompt pegawai biasa tidak berubah |
| 8 | UI: `demo_personas_team.json` + 2-3 baris di `app.py` | `test_supplied_ui.py` mentor tetap hijau; persona manajer muncul di dropdown |
| 9 | Kasus evaluasi manajer di `evaluation/regression_cases.json`, lalu evaluasi di stack terpisah | 17 kasus lama tetap GO, kasus baru lulus |
| 10 | Dokumen: `DECISIONS.md`, risk register, diagram arsitektur, laporan evaluasi, `TODO.md` | Semua keputusan dan risiko di catatan ini tercermin di dokumen resmi |

Setelah langkah 10: jalankan seluruh daftar di bagian 7.2.

---

## 9. Log pengerjaan

| Tanggal | Yang dikerjakan | Catatan |
|---|---|---|
| 2026-11-17 | Rancangan awal dan daftar risiko | Belum ada kode |
| 2026-11-17 | RLS: tiga tabel inti disepakati, pengertian RLS disamakan, `EXCLUDE` tidak dipakai. Ditemukan konflik: `AuthContext` utuh merusak test mentor (3.6). Diputuskan: tetap `employee_id`; RLS tidak butuh role karena manajer dikenali dari `manager_id`. Persona manajer: file terpisah. Manajer tidak dihitung dalam ukuran tim; rentang maksimal 31 hari. Usulan urutan pengerjaan ditambahkan (bagian 10) dan disetujui. Perencanaan selesai. | Belum ada kode |
| 2026-11-17 | Langkah 0-2: commit perbaikan, branch `feat/team-analytics`, role `manager`, kolom `department`/`manager_id` (kolom baru di akhir, karena ada test yang INSERT tanpa nama kolom), 7 pegawai baru, 8 riwayat cuti baru. Seed dua kali tanpa error. | Seed awal gagal karena `UPDATE manager_id` masuk ke loop pertama; dipindah ke loop kedua |
| 2026-11-17 | Langkah 3: helper `_as_user` (`@contextmanager`, `set_config(..., true)`), 6 method + `get_proposal` dipindah ke helper. `get_proposal` kini menerima `employee_id` (hanya dipakai 2 test buatan kita). RLS belum aktif. | `pytest -m "not live"`: 325 passed |
| 2026-11-17 | Langkah 4: RLS aktif di `leave_requests` (milik sendiri + bawahan langsung; insert hanya milik sendiri), `leave_balances` dan `action_proposals` (milik sendiri, `FOR ALL`). Fixture `api` di `test_database_guards.py` kini bertindak sebagai Alya (seperti repository); fixture `api_no_identity` untuk kondisi tanpa identitas. 5 test RLS + 1 test kontrak baru. | Seed 2x OK, 4 policy aktif. `pytest`: 332 passed, 0 skipped. **Container API lama (tanpa `_as_user`) harus di-build ulang**, karena dengan RLS aktif kode lama melihat 0 baris. |
| 2026-11-17 | Langkah 4 di-commit, container API dan UI di-build ulang (readyz ok). Langkah 5: model `TeamLeaveRequest` (turunan `LeaveRequestView` + `employee_id`, `employee_name`); `count_team_members` (tabel `employees`, tanpa RLS) dan `list_team_requests` (lewat `_as_user`, hanya status aktif, filter periode beririsan, `None` = sisi terbuka) di kedua repository. `employee_id` dibawa untuk menghitung orang, tool tidak menampilkannya. Test kontrak dengan manajer khusus test `EMP-900`. | `pytest`: 334 passed, 0 skipped; test tim lulus di memori dan PostgreSQL |
| 2026-11-17 | Langkah 5 di-commit. Langkah 6: `TeamAnalyticsArgs`; schema kelima `get_team_leave_analytics` (tanpa `employee_id`/`manager_id`); handler cek role → `blocked`; `pending_queue` dengan tanggal ditolak (bukan diabaikan); periode wajib untuk dua metrik lain, maks 31 hari. Tiga fungsi hitung murni: `team_absence`, `pending_queue` (hari kalender, tanggal WIB), `coverage_risk` (Senin-Jumat lewat `_is_business_day`, ambang dibandingkan bilangan bulat, persen dibulatkan ke atas mulai 0,5). Hasil hanya nama. | `pytest`: 345 passed (11 test baru di `test_tools.py`). **Dampak:** pegawai biasa kini juga melihat 5 tool (graph dibangun sekali), jadi evaluasi 17 kasus lama wajib diulang di langkah 9. |
