"""Template job per pengguna. Fase 1: pilihan dan resolusi, bukan renderer."""
from __future__ import annotations

from tuton import supabase

DEFAULT_ID = "akademik-standar"
BUILTINS = (
    {"id": "akademik-standar", "name": "Akademik standar", "description": "Format jawaban akademik umum."},
    {"id": "ringkas", "name": "Ringkas", "description": "Jawaban padat dan langsung."},
    {"id": "analitis", "name": "Analitis", "description": "Penjelasan dengan analisis lebih dalam."},
    {"id": "diskusi", "name": "Diskusi", "description": "Format respons untuk forum diskusi."},
    {"id": "tugas-terstruktur", "name": "Tugas terstruktur", "description": "Susunan jawaban tugas berbagian."},
)


def daftar(user_id: str) -> list[dict]:
    return [*BUILTINS, *supabase.template_list(user_id)]


def resolve(user_id: str, template_id: object = "") -> dict:
    """Kembalikan template milik user atau bawaan; ID asing selalu ditolak."""
    identitas = str(template_id or supabase.template_default(user_id) or DEFAULT_ID).strip()
    for template in daftar(user_id):
        if template["id"] == identitas:
            return template
    raise ValueError("Template tidak ditemukan.")
