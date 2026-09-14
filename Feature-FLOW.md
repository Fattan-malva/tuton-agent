# Feature-FLOW.md

> Aplikasi: **Tuton-Agent**  
> Path: `C:\FATTAN\AI\tuton-agent`  
> Bahasa: Python 3.13+ (Windows)  
> Tujuan: Otomatisasi pengerjaan tutorial/diskusi/tugas Universitas Terbuka (UT) via scraping Moodle LMS, transkripsi lampiran dengan AI, dan menghasilkan dokumen Word `.docx`.

---

## 1. Tech Stack

| Layer | Teknologi |
|-------|-----------|
| Bahasa | Python 3.13+ |
| CLI | `argparse` (stdlib) |
| Web Scraping | `requests`, `beautifulsoup4` |
| AI Agent | OpenCode CLI (`opencode run`) |
| Vision AI | `opencode/mimo-v2.5-free`, `opencode/muse-spark-1.3-contributor-free` |
| OCR Fallback | `easyocr`, `pymupdf` |
| Dokumen Word | `python-docx` (OMML math), `pywin32` (COM, legacy .doc) |
| Excel | `openpyxl` |
| Konfigurasi | `python-dotenv` |
| State | JSON file (`output/state.json`) |

---

## 2. Struktur Direktori

```
tuton-agent/
├── main.py                        # CLI entry point
├── config.py                      # Konfigurasi & loader .env
├── requirements.txt
├── .env.example
│
├── moodle/
│   ├── __init__.py
│   ├── auth.py                    # Session Moodle (MoodleSession)
│   ├── scraper.py                 # Scraping course/section/activity
│   ├── parser.py                  # Parsing soal dari forum/assignment/generic
│   ├── downloader.py              # Download attachment ke lampiran/
│   ├── transcribe.py              # Transkripsi attachment → teks
│   └── ocr.py                     # EasyOCR fallback
│
├── generator/
│   ├── __init__.py
│   ├── state.py                   # State persistence (output/state.json)
│   ├── prompt.py                  # Builder prompt untuk OpenCode
│   ├── docx.py                    # Markdown → Word .docx (OMML math)
│   └── opencode_runner.py         # Wrapper subprocess OpenCode CLI
│
├── vendor/
│   └── humanizer/                 # Skill humanizer (25 pola AI)
│       ├── SKILL.md
│       └── agents/openai.yaml
│
├── .opencode/
│   ├── agent/
│   │   ├── tuton.md               # Agent system prompt (jawaban)
│   │   └── transcriber.md         # Agent system prompt (transkripsi)
│   └── package.json
│
├── template/
│   └── ContohFormatJawaban.doc    # Template referensi Word
│
└── output/                        # Hasil (gitignored)
    ├── state.json
    └── <NamaMatkul>/
        └── sesi<N>/
            ├── soal.md
            ├── jawaban_<kind>_<index>.md
            ├── <kind><index>.docx
            └── lampiran/
```

---

## 3. Entry Points

| Command | Fungsi | Deskripsi |
|---------|--------|-----------|
| `python main.py run [--course ID] [--sesi N] [--force]` | `cmd_run` | Full pipeline: scrape → parse → transcribe → jawab → docx |
| `python main.py scrape [--course ID]` | `cmd_scrape` | Inspect course/sesi/aktivitas tanpa proses |
| `python main.py status` | `cmd_status` | Tampilkan progres dari `state.json` |
| *(tanpa subcommand)* | `cmd_run` (default) | Jalankan full flow (item selesai dilewati) |

---

## 4. Full Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  USER                                                              │
│  python main.py run [--course ID] [--sesi N] [--force]            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  1. CONFIG LOAD (config.py)                                        │
│     • Load .env → NAMA, NIM, PRODI, MOODLE_SESSION, OPENCODE_*   │
│     • Validasi field wajib via Config.require()                    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  2. MOODLE AUTH (moodle/auth.py)                                   │
│     • MoodleSession = requests.Session + cookie                    │
│     • check_login() → GET /my/courses.php, cek tidak redirect       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  3. COURSE DISCOVERY (moodle/scraper.py)                           │
│     • get_courses() → parse /my/courses.php                        │
│     • Per course: get_available_sections(course_id)                │
│     • split_assignable() → klasifikasi: diskusi / tugas / lain     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  4. PER-ITEM PROCESSING (_process_item per activity)               │
│     • Cek state.is_done() → skip jika sudah selesai (kec --force)  │
│     • Tentukan display_index dari title/section                    │
│     • Buat output dirs: output/<Course>/sesi<N>/lampiran/          │
└──────┬────────────────────────┬──────────────────────┬──────────────┘
       │                         │                      │
       ▼                         ▼                      ▼
┌──────────────┐     ┌──────────────────────┐  ┌──────────────────┐
│ 5a. PARSE   │     │ 5b. DOWNLOAD         │  │ 5c. BUILD PROMPT │
│  QUESTION   │     │  ATTACHMENTS         │  │                  │
│ (parser.py) │     │ (downloader.py)      │  │ (prompt.py)      │
│             │     │                      │  │                  │
│ • forum     │     │ • download_all()     │  │ • Context + soal │
│   → forum   │     │ • Simpan ke lampiran/│  │   path + rules   │
│ • assign    │     │                      │  │                  │
│   → assign  │     └──────────────────────┘  └──────────────────┘
│ • generic   │
│   → fallback│
│             │
│ Returns     │
│ ParsedQuestion│
│ (title,     │
│ question,   │
│ attach_urls)│
└──────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  6. TRANSCRIBE ATTACHMENTS (moodle/transcribe.py)                  │
│     Per file di lampiran/:                                         │
│     • Image/PDF → Vision AI (mimo-v2.5 → muse-spark → easyocr)    │
│     • Excel → openpyxl                                             │
│     • Word → python-docx                                           │
│     • Output: transkrip_<stem>.md                                  │
│     • Append transkrip ke soal.md                                  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  7. WRITE soal.md                                                  │
│     • Title + question + transkripsi lampiran                      │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  8. RUN OPENCODE (generator/opencode_runner.py)                    │
│     • Resolve binary: OPENCODE_BIN > npm > PATH                   │
│     • Command:                                                     │
│       opencode run - --agent tuton --title tuton-job              │
│       --file <soal.md> [--model ...] [--variant ...]              │
│     • Agent "tuton" baca soal.md, terapkan humanizer skill,       │
│       tulis jawaban_<kind>_<index>.md                              │
│     • Timeout default 900s, retry maks 2x                         │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  9. GENERATE .docx (generator/docx.py)                             │
│     • Header: Nama, NIM, Prodi, Matkul                             │
│     • Title: "<Kind> <Index> <Matkul>"                             │
│     • Section Soal + Jawab                                        │
│     • Daftar Pustaka (hanging indent)                              │
│     • OMML math (matriks, superscript, sqrt)                       │
│     • Bold/Italic/Markdown tables                                  │
│     • Catatan: konversi .doc via Word COM di-skip (OMML butuh .docx)│
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 10. UPDATE STATE (generator/state.py)                              │
│     • set_item(key, {status: "done", outputs: [paths]})           │
│     • Flush ke output/state.json                                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Feature Flow: Transcription Sub-Flow

```
Attachment (image / PDF / xlsx / docx)
         │
         ▼
┌────────────────────────────────────────┐
│  process_attachment(path, work_dir)    │
└────────────────────────────────────────┘
         │
    ┌────┴───────────────────────────────┐
    │                                    │
    ▼                                    ▼
┌──────────────┐               ┌────────────────────┐
│ Image / PDF  │               │ Excel / Word docx  │
│ → Vision AI  │               │ → Python libs      │
│   Primary:   │               │ • openpyxl         │
│   mimo-v2.5  │               │ • python-docx      │
│   Backup:    │               └────────────────────┘
│   muse-spark │
│   Fallback:  │
│   easyocr    │
│   (pymupdf   │
│    for PDF)  │
└──────────────┘
         │
         ▼
  transkrip_<stem>.md (disimpan di lampiran/)
```

---

## 6. Data Models

### 6.1 Moodle Domain (`moodle/scraper.py`, `moodle/parser.py`)

```python
@dataclass
class Course:
    id: int
    name: str
    # Computed: folder_name = safe filename dari name

@dataclass
class Activity:
    mod_type: str   # "forum" | "assign" | "lesson" | "resource" | "page" | "url" | "folder"
    id: int
    title: str
    section: int = 0
    # Computed: url = f"https://elearning.ut.ac.id/mod/{mod_type}/view.php?id={id}"

@dataclass
class SectionInfo:
    number: int
    title: str
    activities: list[Activity]

@dataclass
class ParsedQuestion:
    activity: Activity
    title: str
    question: str = ""
    attachment_urls: list[str] = field(default_factory=list)
    source_url: str = ""
```

### 6.2 State Schema (`generator/state.py`)

```json
{
  "items": {
    "<course_id>:<kind>:<index>": {
      "status": "done" | "failed",
      "matkul": "<course name>",
      "sesi": <section number>,
      "kind": "diskusi" | "tugas",
      "index": <display index>,
      "desc": "<activity title>",
      "outputs": ["<docx_path>", "<md_path>"]
    }
  }
}
```

### 6.3 Document Metadata (`generator/docx.py`)

```python
meta = {
    "nama": str,        # Config.NAMA
    "nim": str,         # Config.NIM
    "prodi": str,       # Config.PRODI
    "matkul": str,      # Course name
    "kind_label": str,  # "Diskusi" atau "Tugas"
    "display_index": int,
    "file_base": str    # e.g. "diskusi1"
}
```

---

## 7. Konfigurasi & Environment

### 7.1 Environment Variables (`.env`)

| Variable | Required | Default | Deskripsi |
|----------|----------|---------|-----------|
| `NAMA` | Ya | `""` | Nama mahasiswa untuk header dokumen |
| `NIM` | Ya | `""` | NIM mahasiswa |
| `PRODI` | Ya | `""` | Program studi |
| `MOODLE_BASE_URL` | Tidak | `https://elearning.ut.ac.id` | URL instance Moodle |
| `MOODLE_SESSION` | Ya | `""` | Session cookie Moodle |
| `COOKIE_*` | Tidak | — | Tambahan cookie (format `name=value`) |
| `OPENCODE_MODEL` | Tidak | `""` (default opencode) | Model untuk jawaban |
| `OPENCODE_VISION_MODEL_IMAGE` | Tidak | `opencode/mimo-v2.5-free` | Vision model gambar |
| `OPENCODE_VISION_MODEL_IMAGE_BACKUP` | Tidak | `opencode/muse-spark-1.3-contributor-free` | Backup vision model gambar |
| `OPENCODE_VISION_MODEL_PDF` | Tidak | `opencode/muse-spark-1.3-contributor-free` | Vision model PDF |
| `OPENCODE_VISION_VARIANT` | Tidak | `low` | Reasoning variant vision |
| `TUTON_TIMEOUT_TRANSCRIBE` | Tidak | `300` | Timeout transkripsi (detik) |
| `TUTON_TIMEOUT` | Tidak | `900` | Timeout opencode default (detik) |
| `OPENCODE_BIN` | Tidak | auto-resolve | Path executable opencode |

### 7.2 Secrets Handling

- `.env` di-`gitignore`
- `MOODLE_SESSION` dianggap secret (cookie browser-extracted)
- Tidak ada API key lain; model AI dipilih via CLI args opencode

---

## 8. Integrasi Eksternal

| Integrasi | Tipe | Detail |
|-----------|------|--------|
| **Moodle LMS** | HTTP/Scraping | `https://elearning.ut.ac.id` — session cookie auth, HTML via BeautifulSoup |
| **OpenCode CLI** | Subprocess | `opencode run -` — dijalankan dengan agent, model, variant, attachments |
| **Vision Models** | AI API (via opencode) | `mimo-v2.5-free` (primary), `muse-spark-1.3-contributor-free` (backup) |
| **EasyOCR** | Library | Fallback OCR untuk gambar |
| **PyMuPDF** | Library | Fallback ekstraksi teks PDF |
| **OpenPyXL** | Library | Ekstraksi teks Excel (.xlsx) |
| **python-docx** | Library | Generate Word .docx |
| **pywin32** | COM | Legacy `.doc` conversion (saat ini di-skip) |
| **Google Scholar / Crossref** | Web (via agent) | Verifikasi referensi oleh agent opencode |

---

## 9. State Management & Idempotency

- **File state:** `output/state.json`
- **Key format:** `f"{course_id}:{kind}:{index}"` (e.g. `328559:forum:39917565`)
- **Load:** Sekali di module-level `_STATE`, di-mutate in-memory, flush ke disk via `save()` setelah setiap item
- **Idempotency:**
  - `state.is_done()` cek status `"done"` + keberadaan file output
  - Flag `--force` bypass state untuk reprocess
  - Output file di-overwrite saat re-run

---

## 10. Output Directory Layout

```
output/
├── state.json
└── <NamaMatkul_Folder>/
    └── sesi<N>/
        ├── soal.md                    # Soal + transkripsi lampiran
        ├── jawaban_<kind>_<index>.md  # Jawaban mentah dari AI
        ├── <kind><index>.docx         # Dokumen Word final
        └── lampiran/
            ├── <file_asli>            # Attachment asli dari Moodle
            ├── transkrip_<stem>.md    # Hasil transkripsi
            └── ...
```

---

## 11. Error Handling

| Kondisi | Penanganan |
|---------|-----------|
| HTTP error | `raise_for_status()` |
| Login invalid | Redirect check di `check_login()` |
| OpenCode timeout | Kill process, retry hingga 2x |
| Item gagal | Tandai `status: "failed"` di `state.json` |
| OCR/transcription gagal | Cascade fallback: vision model → easyocr/pymupdf |
| Encoding Windows | Force UTF-8 stdout/stderr |

---

## 12. Daftar Fitur Utama

| # | Fitur | File Kunci |
|---|-------|-----------|
| 1 | CLI argparse (run / scrape / status) | `main.py` |
| 2 | Autentikasi Moodle via session cookie | `moodle/auth.py` |
| 3 | Scraping course, section, activity | `moodle/scraper.py` |
| 4 | Parsing soal forum, assignment, generic | `moodle/parser.py` |
| 5 | Download attachment (pluginfile.php) | `moodle/downloader.py` |
| 6 | Transkripsi attachment dengan AI + fallback | `moodle/transcribe.py`, `moodle/ocr.py` |
| 7 | Pembuatan prompt untuk OpenCode | `generator/prompt.py` |
| 8 | Eksekusi OpenCode CLI (subprocess) | `generator/opencode_runner.py` |
| 9 | Humanizer skill (25 pola AI) | `vendor/humanizer/SKILL.md` |
| 10 | Generate Word .docx dengan OMML math | `generator/docx.py` |
| 11 | State management (idempotent) | `generator/state.py` |
| 12 | Agent system prompt (tuton.md) | `.opencode/agent/tuton.md` |
| 13 | Agent system prompt (transcriber.md) | `.opencode/agent/transcriber.md` |
| 14 | Verifikasi referensi (agent) | `.opencode/agent/tuton.md` |

---

## 13. Catatan Khusus

- **OMML Equation:** Konversi `.doc` via Word COM di-skip karena OMML math butuh format `.docx` native.
- **Windows Compatibility:** Path dan encoding di-handle khusus untuk win32.
- **OpenCode Binary:** Di-resolve dari `OPENCODE_BIN` env, lalu `%APPDATA%\npm`, lalu PATH.
- **Display Index:** Diekstrak dari judul activity (pola `diskusi N` / `tugas N`), fallback ke section number.
