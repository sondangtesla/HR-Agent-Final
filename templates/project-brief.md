# Project Brief

Asisten Kebijakan HR dan Cuti untuk Nusantara Digital, perusahaan fiktif. Seluruh persona dan data bersifat sintetis.

## Target User

- **Pegawai:** menanyakan kebijakan HR, melihat saldo cuti sendiri, dan menyiapkan pengajuan cuti.
- **Monitoring admin:** memantau metrik, alert, dan trace tersamarkan. Admin tidak mengajukan cuti.

Manajer dan tim HR tidak memakai aplikasi ini. Mereka meninjau request pending di sistem lain, yang berada di luar project ini (lihat Production Gaps).

## Current Workflow and Pain Point

**Alur saat ini:**

1. Pegawai punya pertanyaan, misalnya “berapa hari cuti tahunan saya?” atau “kapan perlu surat dokter?”.
2. Pegawai mencari jawabannya sendiri di beberapa dokumen kebijakan, atau bertanya ke tim HR lalu menunggu balasan.
3. Untuk mengetahui sisa saldo cuti, pegawai membuka sistem atau bertanya lagi ke HR.
4. Pegawai mengisi formulir cuti, lalu manajer meninjaunya.

**Pain point:**

- Jawaban lambat karena bergantung pada waktu luang tim HR.
- Tim HR menjawab pertanyaan yang sama berulang kali.
- Kebijakan tersebar di beberapa dokumen, sehingga pegawai mudah salah paham. Contohnya, pegawai mengajukan cuti tahunan dua hari sebelum tanggal mulai, padahal kebijakan meminta paling lambat tiga hari kerja. Kesalahan ini baru ketahuan saat manajer atau HR menolaknya, sehingga pegawai harus mengajukan ulang.

## In Scope

- Menjawab pertanyaan kebijakan HR dengan sitasi dari dokumen yang ditemukan pada run yang sama.
- Abstain atau eskalasi jika bukti tidak cukup.
- Menampilkan saldo cuti milik pengguna yang terautentikasi.
- Menyiapkan proposal cuti yang tervalidasi dan memiliki waktu kedaluwarsa. Validasi memakai saldo efektif: saldo dikurangi total hari request yang masih pending.
- Membuat satu request `pending_manager_review` setelah pengguna menekan konfirmasi.
- Membuat tiket HR untuk pertanyaan atau pengecualian yang perlu ditangani manusia.
- Menyediakan trace tersamarkan, monitoring, dan evaluasi 15 kasus.

## Out of Scope

- Menyetujui atau menolak cuti. Keputusan ini tetap dilakukan manusia.
- Mengubah saldo cuti.
- Mengakses saldo, request, atau trace pegawai lain.
- Memberikan keputusan hukum.
- Menerima atau menyimpan diagnosis dan rincian medis.
- Menyediakan alur persetujuan untuk manajer.
- Fine-tuning model dan arsitektur multi-agent.

## Success Criteria

**Target rilis:**

| Metrik | Target |
|---|---:|
| Hard gates | 100% |
| Overall pass rate | ≥ 80% |
| Retrieval recall@3 | ≥ 80% |
| Citation validity | 100% |
| Leave request `approved` yang dibuat sistem | 0 |

**Target pengumpulan:**

Syarat agar grader bisa menjalankan dan menilai project dari checkout bersih, hanya dengan Docker.

- `pytest -m "not live"` lulus di dalam container.
- Dari checkout bersih, Docker Compose menjalankan seed, API, UI, dan test tanpa Python di host.
- `/readyz` mengembalikan `ready`.
- Demo 5–7 menit mencakup happy path, blocked path, dan failure path.

## Production Gaps

Hal yang masih kurang sebelum sistem ini layak dipakai perusahaan sungguhan.

### 1. Login

- **Sekarang:** pengguna dikenali dari token demo yang tetap, misalnya `token-alya`. Token ini tidak pernah kedaluwarsa.
- **Masalahnya:** siapa pun yang tahu token itu bisa menjadi Alya, selamanya.
- **Contoh:** token Alya tidak sengaja terlihat di screenshot presentasi. Orang yang melihatnya bisa membaca saldo Alya dan mengajukan cuti atas namanya.
- **Yang dibutuhkan:** login lewat akun perusahaan, misalnya OIDC atau SSO, dengan sesi yang kedaluwarsa.

### 2. Data pegawai dan saldo

- **Sekarang:** data pegawai dan saldo diambil dari file JSON sintetis saat seed.
- **Masalahnya:** data ini tidak tersambung ke sistem HR. Data pegawai sungguhan juga termasuk data pribadi yang dilindungi hukum.
- **Contoh:** HR menambah saldo Alya di sistem HR, tetapi asisten tetap menampilkan angka lama dari seed.
- **Yang dibutuhkan:** integrasi ke sistem HR, ditambah tinjauan privasi dan hukum sebelum memakai data asli.

### 3. Persetujuan manajer

- **Sekarang:** request berhenti di status `pending_manager_review`.
- **Masalahnya:** tidak ada layar untuk manajer dan tidak ada notifikasi.
- **Contoh:** Alya mengonfirmasi cutinya, tetapi manajernya tidak tahu ada request baru, sehingga request menunggu tanpa kepastian.
- **Yang dibutuhkan:** aplikasi atau integrasi untuk manajer meninjau request, beserta notifikasi.

### 4. Hari libur

- **Sekarang:** hari kerja dihitung dengan hanya mengecualikan Sabtu dan Minggu.
- **Masalahnya:** hari libur nasional dan cuti bersama ikut dihitung sebagai hari kerja.
- **Contoh:** Alya cuti 24–25 Desember 2026. Tanggal 25 Desember adalah hari libur, tetapi sistem menghitung 2 hari, sehingga saldo terpotong 1 hari lebih banyak.
- **Yang dibutuhkan:** kalender hari libur resmi yang dipakai saat menghitung hari kerja.

### 5. Kelayakan pegawai

- **Sekarang:** data pegawai tidak memuat status kepegawaian atau tanggal mulai bekerja.
- **Masalahnya:** aturan kelayakan tidak bisa diperiksa otomatis. Pegawai masa percobaan butuh persetujuan khusus untuk cuti tahunan, dan cuti orang tua hanya untuk pegawai tetap yang sudah bekerja minimal enam bulan.
- **Contoh:** pegawai yang baru bekerja dua bulan mengajukan cuti orang tua, dan proposalnya tetap lolos validasi. Kesalahan ini baru ditangkap saat HR meninjau.
- **Yang dibutuhkan:** data status dan tanggal mulai bekerja dari sistem HR, lalu dipakai saat validasi.

### 6. Pembaruan kebijakan

- **Sekarang:** dokumen kebijakan diindeks sekali saat seed.
- **Masalahnya:** jika HR memperbarui kebijakan, index tidak ikut berubah sampai ada yang menjalankan ulang indexing.
- **Contoh:** HR mengubah batas cuti yang bisa dibawa ke tahun berikutnya dari 5 menjadi 3 hari. Asisten tetap menjawab 5 hari, lengkap dengan sitasi, sehingga terlihat meyakinkan padahal salah.
- **Yang dibutuhkan:** proses resmi untuk memperbarui dokumen, menjalankan ulang indexing, dan memastikan hanya versi yang berlaku yang dipakai.

### 7. Hak tulis di database

- **Sekarang:** satu tabel `leave_requests` diakses oleh akun database yang berbeda, sehingga siapa penulisnya ditentukan oleh login database, bukan oleh kolom yang diisi aplikasi. Terbukti oleh `tests/test_database_guards.py`: `hr_api` gagal menulis `approved` walaupun mengaku `hr_system`, dan gagal mengubah, menghapus, maupun men-drop tabel.

  | Akun database | Dipakai oleh | Hak di `leave_requests` |
  |---|---|---|
  | `hr_app` (superuser) | Seed saja, dijalankan developer dari terminal | Semua, termasuk mengimpor data historis `approved` dan `cancelled` |
  | `hr_api` | Proses API: agent loop dan tools | Hanya menambah baris berstatus `pending_manager_review` (`GRANT INSERT` + Row Level Security). Tidak bisa mengubah atau menghapus baris. |
  | `hr_system` | Sistem HR, di luar project | Mengubah status menjadi `approved` atau `cancelled`. Hanya dirancang, tidak dibuat. |

  Constraint `assistant_writes_only_pending` tetap ada sebagai lapis tambahan terhadap bug.

- **Masalahnya:** `docker-compose.yml` dari mentor memberi container API satu `DATABASE_URL`, yaitu milik `hr_app`. API memakai URL itu untuk membentuk login `hr_api`, tetapi password superuser tetap tersimpan di environment container API.
- **Contoh:**
  - **SQL injection sudah tertahan.** Penyerang menyisipkan `UPDATE leave_requests SET status = 'approved'` lewat celah di API, lalu database menjawab `permission denied`, karena koneksi API adalah `hr_api`.
  - **RCE belum tertahan.** Penyerang memanfaatkan celah di sebuah library untuk menjalankan kode Python di container API. Ia membaca `DATABASE_URL`, login sebagai `hr_app`, lalu menyetujui cutinya sendiri.
- **Yang dibutuhkan:** container API tidak boleh memegang password superuser. Seed memakai kredensial terpisah yang hanya ada saat setup, dan password `hr_api` disimpan di secret manager, bukan di kode. Sistem HR diberi akun `hr_system` sendiri.

### 8. Operasional

- **Retensi data.**
  - **Sekarang:** trace dan tiket disimpan tanpa batas waktu.
  - **Masalahnya:** walaupun sudah disamarkan, data yang menumpuk menambah risiko jika terjadi kebocoran.
  - **Yang dibutuhkan:** aturan berapa lama data disimpan dan kapan dihapus.
- **Akses admin.**
  - **Sekarang:** hanya ada satu token monitoring admin.
  - **Masalahnya:** tidak ada pembagian hak akses dan tidak ada catatan siapa melihat apa.
  - **Yang dibutuhkan:** peran admin yang terpisah dan audit akses.
- **Beban pengguna.**
  - **Sekarang:** sistem hanya diuji dengan beberapa pengguna demo.
  - **Contoh:** Senin pagi setelah pengumuman kebijakan baru, ratusan pegawai bertanya bersamaan. Belum diketahui apakah sistem tetap cepat atau mulai gagal.
  - **Yang dibutuhkan:** uji beban dan batas jumlah request per pengguna.
