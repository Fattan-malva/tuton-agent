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
│   ├── reader.py                  # HTML Moodle -> Markdown bersih  (BARU)
│   ├── reader_server.py           # Server Reader 127.0.0.1         (BARU)
│   ├── discovery.py               # Kumpulkan + verifikasi URL      (BARU)
│   ├── parser.py                  # Parser lama (mode --soal-mode file)
│   ├── downloader.py              # Unduh lampiran
│   ├── transcribe.py              # Lampiran -> teks (+ cache hash)  (DIperbaiki)
│   └── ocr.py                     # EasyOCR fallback
│
├── generator/
│   ├── state.py                   # State persistence (thread-safe)
│   ├── prompt.py                  # Prompt URL-only + mode file       (BARU)
│   ├── docx.py                    # Markdown -> Word (OMML math)
│   └── opencode_runner.py         # Wrapper subprocess OpenCode CLI
│
├── .opencode/agent/tuton.md        # System prompt agent (URL-first)
├── vendor/humanizer/              # Skill humanizer
├── template/                      # Template Word referensi
└── output/
    ├── state.json
    ├── .cache/                    # Cache halaman + transkripsi     (BARU)
    │   ├── pages/                 # HTML mentah per URL
    │   ├── md/                    # Markdown hasil render
    │   └── transkrip/             # Transkripsi keyed SHA-256 berkas
    └── <NamaMatkul>/sesi<N>/
        ├── soal.md                # hanya pada mode `file`
        ├── jawaban_<kind>_<n>.md
        ├── <kind><n>.docx
        └── lampiran/
```

---

## 3. Entry Points

| Command | Fungsi | Deskripsi |
|---------|--------|-----------|
| `python main.py run` | `cmd_run` | Pipeline penuh (default bila tanpa subcommand) |
| `python main.py run --jobs 3` | `cmd_run` | 3 item dikerjakan bersamaan |
| `python main.py run --soal-mode file` | `cmd_run` | Perilaku lama (A/B test) |
| `python main.py scrape [--course N]` | `cmd_scrape` | Lihat course/sesi/aktivitas |
| `python main.py probe --course N [--sesi S]` | `cmd_probe` | **Tampilkan persis yang dilihat AI** |
| `python main.py vision-probe` | `cmd_vision_probe` | Cek model bisa melihat gambar? |
| `python main.py solve ...` | `cmd_solve` | Soal dari form (teks/unggah) |
| `python main.py status` | `cmd_status` | Progres + URL sumber tiap item |

`probe` adalah alat paling berguna saat ada masalah: ia mencetak URL Reader,
hasil HTTP, dan isi yang akan dibaca AI — tanpa menjalankan agent.

---

## 4. Pipeline

```
┌──────────────────────────────────────────────────────────────────────┐
│ 1. CONFIG + AUTH                                                    │
│    Config.require() -> cek identitas & sesi                          │
│    MoodleSession.check_login()                                      │
│    retry 3x + backoff untuk timeout/5xx (auth.py)                   │
└───────────────────────────┬──────────────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 2. COURSE & SECTION DISCOVERY (scraper.py)                          │
│    get_courses() -> get_available_sections() -> split_assignable()   │
│    Lewati item yang statusnya sudah `done` (state.json)              │
└───────────────────────────┬──────────────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 3. PREFETCH — paralel (TUTON_PREFETCH_WORKERS, default 6)           │
│    SourceDiscovery.discover(activity, kind):                        │
│      a. kumpulkan URL kandidat:                                     │
│         halaman aktivitas | halaman seksi | thread diskusi | lampiran│
│      b. VERIFIKASI tiap URL (reader.verify_url):                    │
│         HTTP 200, bukan halaman login, isi >= 40 karakter           │
│         atau lampiran >= 200 byte                                   │
│      c. gagal semua -> putar ulang tanpa cache (2x)                 │
│      d. unduh lampiran ke output/<Course>/sesi<N>/lampiran/          │
│    Semua bisa paralel karena hanya menyentuh jaringan/disk.         │
└───────────────────────────┬──────────────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 4. KERJA — paralel (TUTON_JOBS, default 2)                          │
│    Satu item = satu proses `opencode run` (agent `tuton`)            │
│      - prompt berisi URL Reader (bukan teks soal)                   │
│      - AI: webfetch URL -> pahami rubrik/instruksi -> kerjakan      │
│      - retry sampai TUTON_RETRIES bila quality gate gagal            │
│      - quality gate: answer_quality_issues()                        │
│      - docx + state.json                                            │
│    Item gagal TIDAK lagi memblokir sisa item seksi yang sama.       │
│    Log tiap item dibUFFER per-thread lalu dicetak utuh ber-prefix,   │
│    jadi dua item paralel tidak saling mengacak barisnya.            │
└───────────────────────────┬──────────────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 5. DOKUMEN & STATE                                                  │
│    save_doc(soal_text=reader.markdown, jawaban_md, meta)             │
│    state.set_item({... "urls": [sumber yang terverifikasi]})         │
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

### Pembersihan HTML (3 tahap, urutannya penting)

1. `_clean_document` — buang yang tidak ambigu (`nav`, `header`, `footer`,
   `form`, `script`, tombol, `data-region=header/footer`, ...).
2. `_pick_content` — pilih container terluas dari kandidat yang saling lepas
   (`[role=main]`, `#region-main`, `#intro`, `[id^=post-content-]`, ...).
3. `_strip_chrome_tokens` — buang menu/dropdown **di dalam** container.

Tahap 2 dan 3 tidak boleh digabung. Percobaan menggabungkannya menghapus
seluruh halaman, karena `<body>` Moodle membawa class tata letak seperti
`sidebar-one` dan `header-light`.这种事情 hanya ketahuan karena menguji
terhadap HTML asli UT, bukan asumsi.

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

## 8. Mode `file` (A/B test)

`--soal-mode file` menghidupkan perilaku lama: Python menyusun `soal.md` lalu
menempelkannya ke prompt. Dipertahankan untuk membandingkan hasil
`--soal-mode url` vs `file` pada soal yang sama tanpa mengubah kode lain.

Perbedaan utama pada mode `file`: rubrik dan instruksi khusus tutor tetap bisa
terpotong oleh parser, karena info itu memang tidak pernah ikut dalam
`soal.md`.

---

## 9. Konfigurasi

| Variabel | Default | Fungsi |
|---|---|---|
| `TUTON_JOBS` | `2` | Item dikerjakan bersamaan |
| `TUTON_PREFETCH_WORKERS` | `6` | Worker pra-ambil (network-bound) |
| `TUTON_TIMEOUT` | `600` | Batas waktu satu item (detik) |
| `TUTON_RETRIES` | `2` | Percobaan menjawab per item |
| `TUTON_SOAL_MODE` | `url` | `url` (AI ambil sendiri) atau `file` (lama) |
| `TUTON_READER_PORT` | `8765` | Port Reader Lokal |
| `TUTON_TRANSCRIBE` | `auto` | `auto` / `always` / `never` |
| `TUTON_PDF_TEXT_FIRST` | `1` | Ekstrak teks layer PDF sebelum vision |
| `TUTON_CACHE_TTL` | `1800` | Umur cache halaman (detik) |
| `OPENCODE_VISION_TRIES` | `3` | Batas model vision per lampiran |
| `OPENCODE_VISION_PREFER` | (kosong) | Prioritaskan model vision tertentu |

---

## 10. Verifikasi

`python verify_reader.py` menjalankan 49 pemeriksaan tanpa menyentuh Moodle:
render Markdown (rubrik, gambar, tautan, forum), guard keamanan, server Reader
end-to-end, deteksi model vision, dan isi prompt.

Untuk memastikan apa yang sebenarnya dilihat AI, gunakan:

```
python main.py probe --course 329012 --sesi 3
```
