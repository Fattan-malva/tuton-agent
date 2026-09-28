import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

PROJECT_ROOT = BASE_DIR
OUTPUT_DIR = BASE_DIR / "output"
TEMPLATE_DIR = BASE_DIR / "template"
HUMANIZER_DIR = BASE_DIR / "vendor" / "humanizer"

# Zona waktu untuk stempel waktu hasil pekerjaan. UT operates on WIB (UTC+7).
WIB = timezone(timedelta(hours=7))


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
    OPENCODE_MODEL = _env("OPENCODE_MODEL")

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

    # --- Kecepatan & keandalan pipeline -----------------------------------
    # Batas waktu satu job menjawab (detik). Turun dari 900 ke 600 supaya satu
    # item macet tidak menahan batch selama 15 menit.
    TUTON_TIMEOUT = int(_env("TUTON_TIMEOUT", "600"))
    # Jumlah percobaan menjawab per item. Maks 3; default 2 sudah cukup karena
    # retry ketiga hanya mengulang kesalahan yang sama dengan biaya penuh.
    TUTON_RETRIES = int(_env("TUTON_RETRIES", "2"))
    # Berapa item yang dikerjakan bersamaan (masing-masing = 1 proses
    # `opencode run` independen). Naikkan kalau kuota model masih lega.
    TUTON_JOBS = int(_env("TUTON_JOBS", "2"))
    # Worker untuk tahap pra-ambil (verifikasi URL + unduh lampiran) yang
    # network-bound saja, jadi jauh boleh lebih banyak dari TUTON_JOBS.
    TUTON_PREFETCH_WORKERS = int(_env("TUTON_PREFETCH_WORKERS", "6"))
    # Worker khusus transkripsi lampiran. Tiap transkripsi = satu panggilan
    # model vision, jadi dijaga terpisah dari TUTON_JOBS supaya tidak ikut kena
    # rate limit. Transkripsi berjalan otomatis, tanpa perlu memilih model.
    TUTON_TRANSCRIBE_WORKERS = int(_env("TUTON_TRANSCRIBE_WORKERS", "2"))
    # Port Reader Lokal (server yang menyuntikkan cookie Moodle ke URL yang
    # dibaca agent). 0 = port otomatis.
    TUTON_READER_PORT = int(_env("TUTON_READER_PORT", "8765"))
    # "url" = prompt hanya berisi URL, AI yang ambil soalnya sendiri.
    # "file" = perilaku lama, soal.md statis ditempel ke prompt.
    TUTON_SOAL_MODE = _env("TUTON_SOAL_MODE", "url")
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