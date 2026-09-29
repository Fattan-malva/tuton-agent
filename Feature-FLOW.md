# Feature-FLOW.md

> Aplikasi: **Tuton-Agent**  
> Path: `C:\FATTAN\AI\tuton-agent`  
> Bahasa: Python 3.13+ (Windows)  
> Tujuan: Otomatisasi pengerjaan tutorial/diskusi/tugas Universitas Terbuka (UT) via scraping Moodle LMS, dan menghasilkan dokumen Word `.docx`.

---

## 0. Prinsip utama: URL-First

AI **tidak** lagi menerima teks soal hasil scrape kita. AI menerima **URL**,
lalu membacanya sendiri lewat tool `webfetch`. Agar itu mungkin, ada **Reader
Lokal**: server HTTP kecil di `127.0.0.1` yang menyuntikkan `MoodleSession` lalu
mengembalikan halaman sebagai Markdown.

```
URL di prompt  ──webfetch──►  Reader Lokal (127.0.0.1:8765)
                                 │  suntik cookie Moodle
                                 ▼
                          Markdown bersih (instruksi tutor, rubrik, lampiran)
```

Alasannya praktis, bukan selera. Scrape kita pasti memotong bagian yang paling
menentukan nilai:

| Yang hilang saat teks ditempel statis | Akibatnya |
|---|---|
| Instruksi khusus tutor ("minimal 500 kata", "format PDF spasi 1.5") | Jawaban salah bentuk |
| Pedoman penilaian / rubrik | Nilai turun karena butir rubrik terlewat |
| Komposisi nilai & syarat kelulusan | Missed requirement |
| Konteksi diskusi (post pembuka) | Menjawab pertanyaan yang salah |
| Tampilan instruksi di halaman seksi | Nomor butir tidak sinkron dengan yang diminta dosen |

Dengan AI membaca halaman aslinya, semua itu ikut terbaca dan
`generator/prompt.py` tinggalятся di URL + aturan kejujuran.

---

## 1. Tech Stack

| Layer | Teknologi |
|-------|-----------|
| Bahasa | Python 3.13+ |
| CLI | `argparse` (stdlib) |
| Web Scraping | `requests`, `beautifulsoup4` |
| Reader Lokal | `http.server.ThreadingHTTPServer` (stdlib) |
| AI Agent | OpenCode CLI (`opencode run`) |
| Vision AI | auto-deteksi dari `opencode models` |
| OCR Fallback | `easyocr`, `pymupdf` |
| Dokumen Word | `python-docx` (OMML math) |
| Excel | `openpyxl` |
| Web UI | Flask (`server.py`) + Next.js static export |
| Konfigurasi | `python-dotenv` |
| State | JSON file (`output/state.json`) + lock thread |

---

## 2. Struktur Direktori

```
tuton-agent/
├── main.py                        # CLI + orkestrasi pipeline
├── config.py                      # Konfigurasi & loader .env
├── server.py                      # Web UI (Flask) + endpoint Reader
│
├── moodle/
│   ├── auth.py                    # Session + retry/backoff
│   ├── scraper.py                 # Course/section/activity
│   ├── reader.py                  # HTML Moodle -> Markdown bersih
│   ├── reader_server.py           # Server Reader 127.0.0.1
│   ├── discovery.py               # Kumpulkan + verifikasi URL
│   ├── downloader.py              # Unduh lampiran
│   ├── transcribe.py              # Lampiran -> teks (+ cache hash)
│   └── ocr.py                     # EasyOCR fallback
│
├── generator/
│   ├── state.py                   # State persistence (thread-safe)
│   ├── models.py                  # Resolver model per peran (writer/helper)
│   ├── prompt.py                  # Prompt peta, referensi, penulis, form
│   ├── docx.py                    # Markdown -> Word (OMML, template-driven)
│   └── opencode_runner.py         # Wrapper subprocess OpenCode CLI
│
├── .opencode/agent/
│   ├── tuton.md                   # Agen PENULIS jawaban (tanpa riset)
│   ├── pemetak-soal.md            # Cari + pahami soal, sekali per sesi
│   ├── mencari-pustaka.md         # Daftar referensi, sekali per item
│   └── transcriber.md             # Lampiran gambar/PDF -> teks
├── .opencode/skills/humanizer/    # Skill humanizer
├── template/                      # Template Word (dokumen dasar semua .docx)
├── web/                           # Sumber Next.js (build -> web/out)
├── frontend/                      # Hasil static export, disajikan server.py
└── output/
    ├── state.json
    ├── .cache/                    # Cache halaman + transkripsi
    │   ├── pages/                 # HTML mentah per URL
    │   ├── md/                    # Markdown hasil render
    │   └── transkrip/             # Transkripsi keyed SHA-256 berkas
    └── <NamaMatkul>/
        ├── _petak/sesi<N>.md      # Tahap 0: peta soal per sesi
        └── sesi<N>/
            ├── jawaban_<kind>_<n>.md
            ├── referensi_<kind>_<n>.md   # Tahap 1: daftar pustaka
            ├── <MataKuliah>_<Kind><n>.docx
            └── lampiran/
```

Folder `vendor/`, `nextjs-pages/`, berkas `moodle/parser.py`, dan
`package.json` di root sudah dihapus: semuanya sisa versi lama yang sudah
digantikan oleh `web/`. `package.json` root pernah menunjuk Next 14 /
React 18 / Tailwind 3, sedangkan yang benar `web/package.json`
(Next 15 / React 19 / Tailwind 4).

---

## 3. Entry Points

| Command | Fungsi | Deskripsi |
|---------|--------|-----------|
| `python main.py run` | `cmd_run` | Pipeline penuh (default bila tanpa subcommand) |
| `python main.py run --jobs 3` | `cmd_run` | 3 item dikerjakan bersamaan |
| `python main.py run --force` | `cmd_run` | Tulis ulang jawaban; peta + referensi dari cache |
| `python main.py run --remap` | `cmd_run` | Buang cache peta + referensi, buat ulang |
| `python main.py run --soal-mode file` | `cmd_run` | Jalur uji A/B (bukan jalur resmi) |
| `python main.py scrape [--course N]` | `cmd_scrape` | Lihat course/sesi/aktivitas |
| `python main.py probe --course N [--sesi S]` | `cmd_probe` | **Tampilkan persis yang dilihat AI** |
| `python main.py vision-probe` | `cmd_vision_probe` | Cek model bisa melihat gambar? |
| `python main.py solve ...` | `cmd_solve` | Soal dari form (teks/unggah/format) |
| `python main.py status` | `cmd_status` | Progres + URL sumber tiap item |

`probe` adalah alat paling berguna saat ada masalah: ia mencetak URL Reader,
hasil HTTP, dan isi yang akan dibaca AI — tanpa menjalankan agent.

### Dua sakelar cache, bedanya disengaja

| Flag | Efek | Pakai saat |
|------|------|-----------|
| (tanpa flag) | Cache dipakai, item `done` dilewati | Run biasa. Termurah. |
| `--force` | Jawaban ditulis ulang; peta + referensi dari cache | Jawaban lama salah, datanya sudah benar. |
| `--force --remap` | Peta + referensi + jawaban semuanya dibuat ulang | Soalnya sendiri berubah, jadi peta lama jadi salah. |

`--force` tanpa `--remap` saat peta keliru hanya menghasilkan jawaban keliru
yang sama, dua kali bayar.

---

## 4. Pipeline

```
┌──────────────────────────────────────────────────────────────────────┐
 │ 1. CONFIG + AUTH                                                    │
 │    Config.require() → cek identitas & sesi                          │
 │    MoodleSession.check_login()                                      │
 │    retry 3x + backoff untuk timeout/5xx (auth.py)                   │
└──────────────────────────────────────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
 │ 2. COURSE & SECTION DISCOVERY (scraper.py)                          │
 │    get_courses() → get_available_sections() → split_assignable()    │
 │    Lewati item yang statusnya sudah `done` (state.json)             │
└──────────────────────────────────────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
 │ TAHAP 0 — PETA SOAL, satu kali per (mata kuliah, sesi)              │
 │   Agent pemetak-soal (model kecil) → output/_petak/sesi<N>.md       │
 │     a. buka halaman seksi, cari soal di MENU APA SAJA               │
 │     b. tulis butir, rubrik, format jawaban, lampiran                │
 │     c. batas keras 12 halaman; tidak menjawab, tidak riset          │
 │   Cache dipakai ulang di run berikutnya.                            │
 │   --remap memaksa buat ulang dari nol.                              │
 │   GAGAL tidak menghentikan pipeline (lihat catatan bawah).          │
└──────────────────────────────────────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
 │ PREFETCH + TRANSKRIPSI — paralel (TUTON_PREFETCH_WORKERS, 6)        │
 │   SourceDiscovery.discover(activity, kind):                         │
 │     a. kumpulkan URL kandidat:                                      │
 │        halaman aktivitas | seksi | thread diskusi | lampiran        │
 │     b. VERIFIKASI tiap URL (reader.verify_url):                     │
 │        HTTP 200, bukan halaman login, isi ≥ 40 karakter             │
 │        atau lampiran ≥ 200 byte                                     │
 │     c. gagal semua → putar ulang tanpa cache (2x)                   │
 │     d. unduh lampiran → output/<Course>/sesi<N>/lampiran/           │
 │   Lalu transkripsi lampiran sesuai TUTON_TRANSCRIBE.                │
 │   Bisa paralel karena hanya menyentuh jaringan/disk.                │
└──────────────────────────────────────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
 │ TAHAP 1 — DAFTAR PUSTAKA, satu kali per item                        │
 │   Agent mencari-pustaka (model kecil)                               │
 │     → output/<Course>/sesi<N>/referensi_<kind>_<n>.md               │
 │   Batas keras: maksimal TUTON_MAX_PUSTAKA (bawaan 5) entri,         │
 │   maksimal 1 websearch dan 1 webfetch per entri.                    │
 │   Cache per item. GAGAL tidak menghentikan pipeline.                │
└──────────────────────────────────────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
 │ TAHAP 2 — MENULIS, satu kali per item (TUTON_JOBS, 2)               │
 │   Satu item = satu proses opencode run (agent tuton)                │
 │     – baca peta + referensi + transkrip lampiran                    │
 │     – webfetch hanya cadangan kalau peta tidak ada                  │
 │     – salin daftar pustaka VERBATIM dari berkas referensi           │
 │     – retry sampai TUTON_RETRIES bila quality gate gagal            │
 │     – quality gate: answer_quality_issues()                         │
 │   Item gagal tidak memblokir item lain.                             │
 │   Log per-thread di-buffer lalu dicetak utuh ber-prefix,            │
 │   jadi dua item tidak saling mengacak barisnya.                     │
└──────────────────────────────────────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
 │ DOKUMEN & STATE                                                     │
 │   save_doc(soal_text, jawaban_md, meta, template)                   │
 │   state.set_item({... urls: [sumber yang terverifikasi]})           │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 5. Reader Lokal

### Endpoint

| Endpoint | Fungsi |
|---|---|
| `GET /healthz` | status + jumlah permintaan |
| `GET /soal?u=<url>&k=<role>&t=<token>` | Markdown halaman / teks PDF |
| `GET /file?u=<url>&t=<token>` | bytes asli (gambar/PDF/dokumen) |

### Keamanan

| Ancaman | PenANGAN |
|---|---|
| Akses dari proses lain di mesin | token acak per-proses, tanpa token -> 403 |
| SSRF ke host internal | hanya host `MOODLE_BASE_URL` yang boleh diambil |
| Server terekspos jaringan | bind `127.0.0.1` saja |
| Lampiran besar melahap memori | batas 25 MB, timeout 60s |
| `docx` gagal karena karakter kontrol | kontrol & biner dibuang saat render |
| Dokumen hasil menyimpang dari format resmi | template dipakai sebagai dokumen dasar, bukan ditiru |

### Pembersihan HTML (3 tahap, urutannya penting)

1. `_clean_document` — buang yang tidak ambigu (`nav`, `header`, `footer`,
   `form`, `script`, tombol, `data-region=header/footer`, ...).
2. `_pick_content` — pilih container terluas dari kandidat yang saling lepas
   (`[role=main]`, `#region-main`, `#intro`, `[id^=post-content-]`, ...).
3. `_strip_chrome_tokens` — buang menu/dropdown **di dalam** container.

Tahap 2 dan 3 tidak boleh digabung. Percobaan menggabungkannya menghapus
seluruh halaman, karena `<body>` Moodle membawa class tata letak seperti
`sidebar-one` dan `header-light`. Hal seperti ini hanya ketahuan karena
menguji terhadap HTML asli UT, bukan asumsi.

Selector yang sengaja TIDAK dipakai:

| Selector | Alasan |
|---|---|
| `[data-region]` | Moodle memakainya pada `data-region="content"` untuk card body post diskusi — menghapus itu berarti menghapus soal |
| `.inline` | dipakai Moodle untuk membungkus isi post, bukan hanya tombol inline-edit |
| token class `d-flex`, `block`, `toolbar` | utility class Bootstrap yang juga dipakai container konten |

### Yang dibuang sebagai aset, bukan lampiran

Logo, avatar, ikon tipe berkas: `/theme/`, `/theme_`, `/pix/`, `/user/icon/`,
`logout.png`, `theme/image.php`. Tanpa filter ini, "lampiran" berisi logo UT.

---

## 6. Kecepatan

| Teknik | Dampak |
|---|---|
| **Deteksi model vision diperbaiki** | `opencode models --verbose` sudah dihapus di opencode terbaru. Versi lama selalu gagal -> daftar model kosong -> semua transkripsi jatuh ke easyocr di CPU. Sekarang: coba `--verbose`, lalu output polos, lalu daftar statis. 430 model terdeteksi, 3 kandidat vision. |
| **Cache transkripsi (SHA-256)** | Berkas yang tidak berubah tidak pernah ditranskripsi dua kali. `--force` tidak mengulang vision. |
| **Teks layer PDF lebih dulu** | PDF non-scan diekstrak dengan pymupdf (instan) sebelum memanggil model vision. |
| **Cache halaman (TTL)** | 1800 detik. Prefetch kedua dan `probe` berulang tidak memukul Moodle. |
| **Prefetch paralel** | Verifikasi URL + unduh lampiran jaringan murni, 6 worker. |
| **`--jobs` untuk item** | 2 item = 2 proses `opencode run` bersamaan. Ini pengatur utama. |
| **Retry 2x, bukan 3x** | Percobaan ketiga mengulang kesalahan yang sama dengan biaya penuh. |
| **Prompt ramping** | Tidak ada lagi teks soal + transkripsi yang ditempel di prompt. |

### Batas biaya vision

`OPENCODE_VISION_TRIES` (default 3) membatasi jumlah model yang dicoba per
lampiran. Tanpa batas ini, daftar model yang tersedia (ratusan) akan dicoba satu
per satu dan satu lampiran bisa menahan belasan menit.

---

## 7. Keandalan

| Masalah nyata | Penangan |
|---|---|
| Satu selector gagal -> soal kosong | 4 sumber URL per item, tiap satu diverifikasi |
| Sesi Moodle kedaluwarsa | Deteksi halaman login; pesan jelas "perbarui MoodleSession di Settings"; item lain tetap jalan |
| 1 soal tidak ketemu | Item itu ditandai `failed`, **sisa item di seksi tetap dikerjakan** (perilaku lama: satu gagalan memblokir satu seksi penuh) |
| URL thread diskusi 404 | `normalize_url()` Merrygabungkan segmen kembar: `/mod/forum/mod/forum/discuss.php` -> `/mod/forum/discuss.php` |
| Jawaban korup / tanpa Daftar Pustaka | `answer_quality_issues()` + retry dengan instruksi perbaikan |
| `state.json` korup saat paralel | Tulis ke `.tmp` lalu rename atomik; `RLock` protects read-modify-write |
| Log antar item tercampur | stdout diroute per-thread, tiap item di-buffer lalu dicetak utuh ber-prefix |
| Timeout jaringan sesaat | retry 3x + backoff di `MoodleSession._request` |

---

## 8. Jalur `file` (Form Soal + uji A/B)

Ada dua tempat yang memakai jalur file, dan sengaja dipisah:

| Pemakai | Tujuan |
|---|---|
| `cmd_solve` (Form Soal) | Jalur resmi. Sumber soal dari ketikan/unggah pengguna, bukan dari scrape. |
| `main.py run --soal-mode file` | Uji A/B di CLI. Bukan jalur resmi dan tidak bisa diaktifkan lewat `.env`. |

Dulu `--soal-mode` ada di Settings dan `.env`. Itu dibuang: sakelar yang
tersembunyi membuat hasil run tidak bisa dijelaskan hanya dari log, dan dropdown
itu membuat orang memilih antara dua perilaku yang kesannya sama padahal
hanya satu yang benar.

### Form Soal

Form Soal bekerja seperti biasa, dengan satu field opsional tambahan:

| Field | Kosong | Terisi |
|---|---|---|
| Contoh format (`.docx`) | Template standar jadi dokumen dasar | Berkas pengguna jadi dokumen dasar |
| Keterangan format | — | Ditambahkan ke prompt sebagai petunjuk isi |

Berkas format disalin ke `output/<Course>/sesi<N>/_format/`, bukan ke
`template/`. Kalau diletakkan di `template/`, satu unggahan akan diam-diam
menggantikan template standar untuk semua run berikutnya.

Python menyalin berkas format apa adanya sebagai dokumen dasar, sehingga
margin, ukuran halaman, font, dan style dokumen hasil benar-benar milik
pengguna. Yang tidak ditangani Python adalah **isi**: model penulislah yang
mengisi tiap sub-bagian memakai style asli berkas contoh itu.

Berkas `.docx` hasil Agent Run mengikuti `template/ContohFormatJawaban.docx`
dengan cara yang sama: dipakai sebagai dokumen dasar, bukan ditiru. Style
`Normal`, `Heading 2`, `Heading 3`, dan tabel identitas diambil dari dokumen itu
supaya perubahan template ikut terbawa.

---

## 9. Konfigurasi

| Variabel | Default | Fungsi |
|---|---|---|
| `TUTON_JOBS` | `2` | Item dikerjakan bersamaan |
| `TUTON_PREFETCH_WORKERS` | `6` | Worker pra-ambil (network-bound) |
| `TUTON_TIMEOUT` | `600` | Batas waktu satu item (detik) |
| `TUTON_RETRIES` | `2` | Percobaan menjawab per item |
| `TUTON_MAX_PUSTAKA` | `5` | Batas keras referensi per jawaban |
| `TUTON_TIMEOUT_HELPER` | `420` | Batas waktu satu pemanggilan agen pembantu |
| `TUTON_HELPER_RETRIES` | `1` | Percobaan agen pembantu |
| `OPENCODE_MODEL_HELPER` | (kosong) | Model pemetaan soal + cari referensi. Kosong = pilih otomatis |
| `TUTON_READER_PORT` | `8765` | Port Reader Lokal |
| `TUTON_TRANSCRIBE` | `auto` | `auto` / `always` / `never` |
| `TUTON_PDF_TEXT_FIRST` | `1` | Ekstrak teks layer PDF sebelum vision |
| `TUTON_CACHE_TTL` | `1800` | Umur cache halaman (detik) |
| `SEMESTER` | (kosong) | Isi baris Semester di tabel identitas |
| `UT_DAERAH` | (kosong) | Isi baris UT Daerah di tabel identitas |
| `OPENCODE_VISION_TRIES` | `3` | Batas model vision per lampiran |
| `OPENCODE_VISION_PREFER` | (kosong) | Prioritaskan model vision tertentu |

### Nama variabel `.env` harus bisa diurai

Nama variabel ber-spasi — misalnya `UT Daerah=Jakarta` — **tidak bisa diurai
python-dotenv**. Barisnya dilewati dengan pesan "could not parse statement",
`Config.UT_DAERAH` tetap kosong, dan baris "UT Daerah" tidak pernah tercetak di
dokumen. Tidak ada error yang terlihat dari sisi pengguna, hanya baris yang
bikin-bilang hilang.

Aturannya sederhana: huruf besar + garis bawah, tanpa spasi.
`SEMESTER=Semester 2`, `UT_DAERAH=Jakarta`.

`config._env_any()` masih menerima ejaan lama (`Semester`, `UT Daerah`)
supaya `.env` yang terlanjur salah edit tidak harus dibetulkan manual, dan
`server.py` membuang kunci ejaan lama setiap kali Settings menyimpan ulang —
jadi filenya lama-lama mendekati benar sendiri.

`test_format.py` bagian 6 mengunci aturan ini, termasuk membuktikan bahwa
nama ber-spasi memang tidak terbaca.

`TUTON_MAX_PUSTAKA` adalah batas **biaya**, bukan selera. Satu entri berarti
satu kali verifikasi sumber. Referensi tanpa batas membuat satu run bisa jauh
lebih mahal tanpa menambah ketepatan.

---

## 10. Verifikasi

Tiga pagar regresi, semuanya jalan lokal tanpa menyentuh Moodle dan tanpa
biaya model (karena `run_opencode` di-stub):

| Perintah | Cek | Cakupan |
|---|---|---|
| `python verify_reader.py` | 49 | Render Markdown (rubrik, gambar, tautan, forum), guard keamanan, server Reader end-to-end, deteksi model vision, isi prompt |
| `python test_pipeline.py` | 70 | Rantai penuh URL → docx: discovery, transkripsi, tiga tahap agent, quality gate, template-driven docx, state, CLI |
| `python test_format.py` | 61 | Field "Format Jawaban" (opsional), berkas format sebagai dokumen dasar, Semester + UT Daerah sampai ke dokumen, nama variabel `.env`, `output/` dibuat otomatis, aturan git, pagar class `pixel-*` |

Stub di `test_pipeline.py` sadar-per-agen: agen peta menulis peta, agen
pencari-pustaka menulis referensi, dan agen penulis menulis jawaban. Stub juga
mencatat prompt per agen, sehingga pemeriksaan bisa menunjuk prompt yang tepat
— bukan `PROMPTS[0]`, yang sejak pipeline tiga tahap adalah prompt pemetaan.

Untuk memastikan apa yang sebenarnya dilihat AI, gunakan:

```
python main.py probe --course 329012 --sesi 3
```

---

## 11. Aturan CSS kustom

Class tema (`pixel-input`, `pixel-button`, `pixel-label`, ...) ditulis **di luar
`@layer`** di `globals.css`. Konsekuensinya yang harus diingat:

> Di kaskade CSS, aturan tanpa layer selalu menang atas utility Tailwind yang
> berada di `@layer utilities`.

Jadi `className="pixel-input pl-8"` **tidak** memberi padding kiri 2rem.
`padding: 0 12px` dari `.pixel-input` tetap yang berlaku, teks mulai di 12px,
dan ikon di 10px langsung tertimpa. Bug ini pernah terjadi di input pencarian
model.

Aturan yang berlaku: kalau butuh mengubah properti yang sudah diatur class
`pixel-*`, tambahkan class baru di `globals.css` (contoh: `pixel-input-icon`,
`pixel-textarea`), jangan pakai utility Tailwind.

`test_format.py` bagian 9 memindai seluruh `.tsx` dan gagal kalau ada
`pixel-input` yang digabung utility `p*`/`min-h*` — menangkap niatnya, bukan
hasil visualnya.

---

## 12. Folder keluaran

`output/` dibuat otomatis oleh `config.ensure_output_dirs()`, yang dipanggil
dari `Config.require()` (seluruh perintah `main.py`) dan dari blok `__main__`
`server.py`. Tidak ada `.gitkeep`, jadi tidak perlu ada apa pun yang
di-commit hanya untuk menjaga foldernya tetap ada.

Isinya diabaikan git sepenuhnya lewat satu baris `output/` di `.gitignore`.
Satu baris sudah cukup karena git mengabaikan seluruh isi direktori, termasuk
subfolder `.jobs/`, `.cache/`, `_petak/`, dan `_format/`. `test_format.py`
memeriksa ini berkas per berkas, karena satu pola yang terlewat berarti
Nama/NIM bisa ikut ter-push tanpa terlihat.
