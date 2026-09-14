import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

PROJECT_ROOT = BASE_DIR
OUTPUT_DIR = BASE_DIR / "output"
TEMPLATE_DIR = BASE_DIR / "template"
HUMANIZER_DIR = BASE_DIR / "vendor" / "humanizer"


class Config:
    NAMA = os.getenv("NAMA", "")
    NIM = os.getenv("NIM", "")
    PRODI = os.getenv("PRODI", "")
    OPENCODE_MODEL = (os.getenv("OPENCODE_MODEL") or "").strip()

    OPENCODE_VISION_MODEL_IMAGE = (
        os.getenv("OPENCODE_VISION_MODEL_IMAGE", "opencode/mimo-v2.5-free").strip()
    )
    OPENCODE_VISION_MODEL_IMAGE_BACKUP = os.getenv(
        "OPENCODE_VISION_MODEL_IMAGE_BACKUP", "opencode/muse-spark-1.3-contributor-free"
    ).strip()
    OPENCODE_VISION_MODEL_PDF = os.getenv(
        "OPENCODE_VISION_MODEL_PDF", "opencode/muse-spark-1.3-contributor-free"
    ).strip()
    OPENCODE_VISION_VARIANT = os.getenv("OPENCODE_VISION_VARIANT", "low").strip()
    TUTON_TIMEOUT_TRANSCRIBE = int(os.getenv("TUTON_TIMEOUT_TRANSCRIBE", "300"))

    MOODLE_BASE_URL = os.getenv("MOODLE_BASE_URL", "https://elearning.ut.ac.id")
    MOODLE_SESSION = os.getenv("MOODLE_SESSION", "").strip()
    _EXTRA_COOKIES = None

    @classmethod
    def cookies(cls) -> dict:
        if cls._EXTRA_COOKIES is None:
            cls._EXTRA_COOKIES = {
                k: v
                for k, v in os.environ.items()
                if k.startswith("COOKIE_") and v.strip()
            }
        cookies = {"MoodleSession": cls.MOODLE_SESSION}
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
            "has_session": bool(cls.MOODLE_SESSION),
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
        if not cls.MOODLE_SESSION:
            raise RuntimeError("MOODLE_SESSION belum diisi di .env")