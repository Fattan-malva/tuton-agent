import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

PROJECT_ROOT = BASE_DIR
OUTPUT_DIR = BASE_DIR / "output"
TEMPLATE_DIR = BASE_DIR / "template"

# Subfolder yang dibuat di dalam `output/`. `.jobs` dipakai server.py untuk
# unggahan sementara, `.cache` untuk cache halaman dan transkripsi, `_petak`
# untuk peta soal per sesi. Semuanya diabaikan git.
OUTPUT_JOBS_DIR = OUTPUT_DIR / ".jobs"
OUTPUT_CACHE_DIR = OUTPUT_DIR / ".cache"

# Zona waktu untuk stempel waktu hasil pekerjaan. UT operates on WIB (UTC+7).
WIB = timezone(timedelta(hours=7))


def ensure_dir(path: Path) -> Path:
    """Buat satu folder (bukan hanya leaf) beserta induknya, lalu kembalikan.

    Setiap penulisan ke disk harus lewat sini, karena dua alasan:

    1. `mkdir(parents=True)` hanya menyelesaikan kasus "folder belum pernah
       dibuat". Kalau foldernya HILANG setelah dibuat -- mount `output/` di
       container yang di-recreate, `rm -rf output` dari host saat container
       jalan, atau repo yang di-clone ulang -- pemanggil lama akan gagal
       dengan `FileNotFoundError` yang tidak menyebut penyebabnya. Di
       container, `output/` adalah bind-mount dari host, jadi kondisi nyata
       dan bukan tebakan: folder bisa hilang kapan saja tanpa container
       ikut berhenti.

    2. Pesan errornya harus bisa dibaca orang yang bukan pemilik server.
       `FileNotFoundError: '/app/output/.jobs'` tidak memberi tahu apakah
       masalahnya mount, izin tulis, atau container yang memang belum pernah
       menjalankan apa pun. Karena itu pesan kesalahannya ditulis di sini."""

    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except OSError as first:
        # Satu percobaan lagi: kalau yang hilang adalah leaf-nya, `parents=True`
        # sudah harus menanganinya. Retry menutup kasus mount yang baru saja
        # terpasang dan inode lamanya sudah tidak berlaku.
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path
        except OSError as exc:
            raise RuntimeError(
                f"Tidak bisa menyiapkan folder keluaran '{path}'. "
                "Penyebab paling sering: folder `output/` di host tidak ada "
                "atau tidak bisa ditulis (cek izin tulisnya, lalu jalankan "
                "`podman-compose down && mkdir -p output && podman-compose up -d`), "
                "atau mount `output/` tidak aktif. "
                f"Error asli: {first!r} / {exc!r}"
            ) from exc


# Setara True kalau ketiga folder keluaran sudah ada. Dipakai sebagai gerbang
# cepat supaya pemeriksa per-request tidak melakukan tiga kali `is_dir()` untuk
# request yang tidak menyentuh disk sama sekali.
_OUTPUT_DIRS_READY = False


def ensure_output_dirs(force: bool = False) -> Path:
    """Buat `output/` beserta subfoldernya kalau belum ada, lalu kembalikan.

    Dipanggil dari setiap titik masuk (`Config.require`, `server.py` termasuk
    `before_request`, `cmd_solve`, dan setiap penulis di dalam pipeline)
    supaya folder keluaran selalu ada sebelum ada yang menulis ke sana.

    `force=True` melewati cek cepat, dipakai saat server baru start: pada
    saat itu mount `output/` bisa saja belum terpasang, jadi asumsi "sudah ada"
    justru penyebab `FileNotFoundError` yang dilaporkan user.
    """
    global _OUTPUT_DIRS_READY
    if _OUTPUT_DIRS_READY and not force and all(
        d.is_dir() for d in (OUTPUT_DIR, OUTPUT_JOBS_DIR, OUTPUT_CACHE_DIR)
    ):
        return OUTPUT_DIR
    ensure_dir(OUTPUT_DIR)
    ensure_dir(OUTPUT_JOBS_DIR)
    ensure_dir(OUTPUT_CACHE_DIR)
    _OUTPUT_DIRS_READY = True
    return OUTPUT_DIR


def now_wib() -> datetime:
    """Waktu sekarang dalam zona WIB (UTC+7)."""
    return datetime.now(WIB)


def now_stamp() -> str:
    """Stempel waktu presisi detik, mis. '2026-09-28 15:04:37'."""
    return now_wib().strftime("%Y-%m-%d %H:%M:%S")


def stamp_display(value: str) -> str:
    """Normalisasi stempel waktu ISO/state ke 'YYYY-MM-DD HH:MM:SS'."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=WIB)
    return dt.astimezone(WIB).strftime("%Y-%m-%d %H:%M:%S")


# Kredensial Moodle (MOODLE_COOKIE/MoodleSession) disimpan di file JSON
# terpisah (bukan .env) supaya bisa di-update terus dari menu Settings.
MOODLE_CRED_FILE = BASE_DIR / "moodle_credentials.json"


DEFAULT_MOODLE_BASE_URL = "https://elearning.ut.ac.id"


def _load_moodle_session() -> str:
    try:
        data = json.loads(MOODLE_CRED_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    value = data.get("MoodleSession") or data.get("moodle_session") or ""
    return str(value).strip()


def _env(key: str, default: str = "") -> str:
    """Baca variabel env; variabel yang ADA tapi KOSONG dihitung belum diisi.

    Tanpa ini baris `MOODLE_BASE_URL=` (kosong) di .env menimpa default sehingga
    semua request menjadi URL relatif ('/my/courses.php') -> requests MissingSchema.
    """
    return (os.getenv(key) or "").strip() or default


def _env_any(*keys: str, default: str = "") -> str:
    """Baca beberapa nama variabel, ambil yang pertama terisi.

    Hanya dipakai untuk variabel yang ejaan lamanya keliru. Contoh nyata:
    `.env` pernah menulis `UT Daerah=Jakarta` -- nama variabel dengan spasi di
    tengah. python-dotenv tidak bisa menguraikannya sama sekali (memunculkan
    "could not parse statement" lalu MELOMPATI barisnya), jadi nilainya hilang
    tanpa error dan baris "UT Daerah" tidak pernah tercetak di dokumen.

    `.env.example` sekarang memakai nama yang benar. Fungsi ini tetap ada
    supaya `.env` yang sudah terlanjur salah edit tidak harus diperbaiki
    manual oleh pengguna.
    """
    for key in keys:
        nilai = (os.getenv(key) or "").strip()
        if nilai:
            return nilai
    return default


def normalize_base_url(raw: str) -> str:
    """Rapikan base URL Moodle: tambah skema bila kurang, buang slash akhir."""
    url = (raw or "").strip().rstrip("/")
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    return url


class Config:
    APP_USERNAME = _env("APP_USERNAME")
    APP_PASSWORD = _env("APP_PASSWORD")

    NAMA = _env("NAMA")
    NIM = _env("NIM")
    PRODI = _env("PRODI")
    # Isi tabel identitas di header dokumen. Boleh kosong: baris dengan nilai
    # kosong dilewati, bukan dicetak sebagai "None"/"" atau label menggantung.
    #
    # Nama ejaan lama ikut diterima supaya `.env` yang sudah terlanjur ditulis
    # dengan `Semester=` / `UT Daerah=` tetap bekerja. Lihat `_env_any`.
    SEMESTER = _env_any("SEMESTER", "Semester", "semester")
    UT_DAERAH = _env_any("UT_DAERAH", "UT Daerah", "ut_daerah", "UTDaerah")

    # Model untuk agen PENULIS jawaban (`tuton`). Ini satu-satunya langkah yang
    # butuh model kuat, karena seluruh halaman tidak lagi dibacanya sendiri.
    OPENCODE_MODEL = _env("OPENCODE_MODEL")
    # Model untuk agen pembantu: `pemetak-soal` dan `pencari-pustaka`. Tugasnya
    # sempit (baca halaman -> tulis brief; cari referensi -> tulis daftar) jadi
    # model kecil/grading gratis sudah cukup. Kosongkan untuk auto-pilih dari
    # `opencode models`; bila diisi tapi modelnya tidak ada, tetap auto-pilih
    # alih-alih gagal.
    OPENCODE_MODEL_HELPER = _env("OPENCODE_MODEL_HELPER")
    # Model transcriber (vision). Kosong = auto-pilih dari `opencode models`
    # (perilaku lama, tidak berubah). Kalau diisi, model itu DICOBA PALING
    # DULU -- bukan dikunci: bila gagal atau ternyata tidak bisa melihat
    # gambar, kandidat otomatis berikutnya tetap mengambil alih, supaya satu
    # model rusak tidak mematikan seluruh transkripsi. Prinsip yang sama seperti
    # `OPENCODE_MODEL_HELPER`: jangan pernah gagal hanya karena model pilihan.
    OPENCODE_MODEL_TRANSCRIBE = _env("OPENCODE_MODEL_TRANSCRIBE")

    # Model transcriber (vision) dipilih OTOMATIS dari `opencode models`
    # berdasarkan yang support image/pdf, jadi tidak di-hardcode. Variabel ini
    # opsional untuk memprioritaskan model tertentu bila masih tersedia.
    OPENCODE_VISION_PREFER = [
        p.strip() for p in _env("OPENCODE_VISION_PREFER").split(",") if p.strip()
    ]
    OPENCODE_VISION_VARIANT = _env("OPENCODE_VISION_VARIANT", "low")
    TUTON_TIMEOUT_TRANSCRIBE = int(_env("TUTON_TIMEOUT_TRANSCRIBE", "300"))
    # Berapa model vision yang boleh dicoba untuk satu lampiran sebelum menyerah.
    # Tiap percobaan = 1 proses opencode, jadi ini batas biaya.
    OPENCODE_VISION_TRIES = int(_env("OPENCODE_VISION_TRIES", "3"))
    # PDF ber-teks-layer diekstrak langsung (instan) sebelum panggil model vision.
    TUTON_PDF_TEXT_FIRST = _env("TUTON_PDF_TEXT_FIRST", "1") not in ("0", "false", "no")
    # Minimal karakter teks layer PDF agar dianggap sah. Nilai kecil disengaja:
    # PDF soal UT biasanya hanya beberapa baris, dan teks layer selalu lebih
    # otoritatif daripada OCR (yang sering salah baca 1NF jadi INF).
    TUTON_PDF_TEXT_MIN_CHARS = int(_env("TUTON_PDF_TEXT_MIN_CHARS", "40"))

    # --- Kecepatan & keandalan pipeline -----------------------------------
    # Batas waktu satu job menjawab (detik). Turun dari 900 ke 600 supaya satu
    # item macet tidak menahan batch selama 15 menit.
    TUTON_TIMEOUT = int(_env("TUTON_TIMEOUT", "600"))
    # Jumlah percobaan menjawab per item. Maks 3; default 2 sudah cukup karena
    # retry ketiga hanya mengulang kesalahan yang sama dengan biaya penuh.
    TUTON_RETRIES = int(_env("TUTON_RETRIES", "2"))
    # Batas waktu untuk agen pembantu (`pemetak-soal`, `pencari-pustaka`).
    # Lebih pendek dari TUTON_TIMEOUT karena tugasnya sempit: satu peta soal
    # atau satu daftar referensi. Tanpa batas lebih pendek, satu pemetaan yang
    # macet menahan seluruh batch selama 10 menit.
    TUTON_TIMEOUT_HELPER = int(_env("TUTON_TIMEOUT_HELPER", "420"))
    # Jumlah percobaan untuk agen pembantu. Default 1: kalau pemetaan gagal,
    # jalur cadangan agen penulis (baca URL sendiri) masih rescuing pekerjaan,
    # jadi mengulang pemetaan dengan model yang sama hanya menguras kuota.
    TUTON_HELPER_RETRIES = int(_env("TUTON_HELPER_RETRIES", "1"))
    # Berapa item yang dikerjakan bersamaan (masing-masing = 1 proses
    # `opencode run` independen). Naikkan kalau kuota model masih lega.
    TUTON_JOBS = int(_env("TUTON_JOBS", "4"))
    # Lebar worker untuk TAHAP PEMETAAN SOAL per sesi (`pemetak-soal`). Sesi-sesi
    # saling bebas: tiap satu menulis `sesi<N>.md` yang berbeda, jadi tidak ada
    # yang berebut berkas sama.
    TUTON_MAP_WORKERS = int(_env("TUTON_MAP_WORKERS", "4"))
    # Lebar worker untuk TAHAP PENCARIAN PUSTAKA per item. Sama seperti pemetaan:
    # tiap item menulis `referensi_<kind>_<index>.md` yang berbeda dan hanya
    # membaca peta sesi yang sudah selesai ditulis sebelumnya.
    TUTON_HELPER_WORKERS = int(_env("TUTON_HELPER_WORKERS", "4"))
    # Batas keras jumlah referensi di Daftar Pustaka. Ini batas BIAYA, bukan
    # selera: riset adalah langkah termahal per item, dan tiap referensi
    # menambah satu putaran webfetch. Prompt agen `pencari-pustaka` memakai
    # angka yang sama, dan `answer_quality_issues` menolak hasil yang melebihi.
    TUTON_MAX_PUSTAKA = int(_env("TUTON_MAX_PUSTAKA", "5"))
    # Umur maksimum referensi yang dicari di LUAR materi sesi, dalam tahun.
    # Rujukan yang memang diminta tutor (bahan ajar wajib sesi) tetap dipakai
    # berapa pun umurnya, karena yang menentukan soal itu yang menunjuk buku
    # itu. Referensi tambahan dari luar wajib masuk rentang ini, supaya dokumen
    # tidak terlihat seperti hasil riset lama.
    TUTON_PUSTAKA_TAHUN_MAX = int(_env("TUTON_PUSTAKA_TAHUN_MAX", "10"))
    # Worker untuk tahap pra-ambil (verifikasi URL + unduh lampiran) yang
    # network-bound saja, jadi jauh boleh lebih banyak dari TUTON_JOBS.
    TUTON_PREFETCH_WORKERS = int(_env("TUTON_PREFETCH_WORKERS", "6"))
    # Worker khusus transkripsi lampiran. Tiap transkripsi = satu panggilan
    # model vision, jadi dijaga terpisah dari TUTON_JOBS supaya tidak ikut kena
    # rate limit. Transkripsi berjalan otomatis, tanpa perlu memilih model.
    TUTON_TRANSCRIBE_WORKERS = int(_env("TUTON_TRANSCRIBE_WORKERS", "3"))
    # Port Reader Lokal (server yang menyuntikkan cookie Moodle ke URL yang
    # dibaca agent). 0 = port otomatis.
    TUTON_READER_PORT = int(_env("TUTON_READER_PORT", "8765"))
    # "auto" = pakai transkripsi hanya bila model agent tak bisa melihat
    # gambar/PDF; "always" = selalu transkripsi; "never" = serahkan file
    # ke agent (ia membacanya sendiri lewat tool read).
    TUTON_TRANSCRIBE = _env("TUTON_TRANSCRIBE", "auto")
    # Cache halaman & transkripsi. Simpan hasil fetch supaya `--force` tidak
    # memukul Moodle lagi dan transkripsi vision tidak diulang.
    TUTON_CACHE_DIR = BASE_DIR / "output" / ".cache"
    TUTON_CACHE_TTL = int(_env("TUTON_CACHE_TTL", "1800"))

    MOODLE_BASE_URL = normalize_base_url(
        _env("MOODLE_BASE_URL", DEFAULT_MOODLE_BASE_URL)
    )
    _EXTRA_COOKIES = None

    @classmethod
    def base_url(cls) -> str:
        """Base URL Moodle yang siap pakai; error jelas bila kosong/tak valid."""
        url = normalize_base_url(cls.MOODLE_BASE_URL)
        if not url or "://" not in url:
            raise RuntimeError(
                "MOODLE_BASE_URL kosong/tidak valid. Isi di .env atau menu "
                f"Settings (contoh: {DEFAULT_MOODLE_BASE_URL})."
            )
        return url

    @classmethod
    def moodle_session(cls) -> str:
        """Prioritaskan kredensial dari JSON; fallback ke MOODLE_SESSION di .env."""
        stored = _load_moodle_session()
        return stored or _env("MOODLE_SESSION")

    @classmethod
    def save_moodle_session(cls, value: str) -> None:
        value = str(value or "").strip()
        if value.lower().startswith("moodlesession="):
            value = value.split("=", 1)[1].strip()
        MOODLE_CRED_FILE.write_text(
            json.dumps({"MoodleSession": value}, indent=2) + "\n",
            encoding="utf-8",
        )
        cls._EXTRA_COOKIES = None

    @classmethod
    def cookies(cls) -> dict:
        if cls._EXTRA_COOKIES is None:
            cls._EXTRA_COOKIES = {
                k: v
                for k, v in os.environ.items()
                if k.startswith("COOKIE_") and v.strip()
            }
        cookies = {"MoodleSession": cls.moodle_session()}
        for raw in cls._EXTRA_COOKIES.values():
            parts = raw.split("=", 1)
            if len(parts) == 2:
                cookies[parts[0].strip()] = parts[1].strip()
        return cookies

    @classmethod
    def as_dict(cls) -> dict:
        return {
            "nama": cls.NAMA,
            "nim": cls.NIM,
            "prodi": cls.PRODI,
            "model": cls.OPENCODE_MODEL or "(default)",
            "base_url": cls.MOODLE_BASE_URL,
            "has_session": bool(cls.moodle_session()),
        }

    @classmethod
    def require(cls) -> None:
        # Folder keluaran disiapkan lebih dulu, bahkan sebelum identitas dicek.
        # Kalau identitas kurang lengkap, run memang berhenti -- tapi `output/`
        # tetap harus ada supaya `status` dan `results` (yang tidak lewat
        # `require`) bisa membaca cache lama tanpa error.
        ensure_output_dirs()
        missing = [k for k, v in {
            "NAMA": cls.NAMA,
            "NIM": cls.NIM,
            "PRODI": cls.PRODI,
        }.items() if not v]
        if missing:
            raise RuntimeError(
                "Identitas belum lengkap di .env: " + ", ".join(missing)
            )
        if not cls.moodle_session():
            raise RuntimeError(
                "MOODLE_COOKIE (MoodleSession) belum diisi. "
                "Atur di menu Settings."
            )
        cls.base_url()