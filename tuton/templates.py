"""Template jawaban: daftar, resolusi, dan renderer dari skema (tanpa berkas DOCX)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from tuton import supabase
from tuton import template_schema as skema_mod

DEFAULT_ID = "akademik-standar"


def daftar(user_id: str) -> list[dict]:
    bawaan = [{**t, "bawaan": True} for t in skema_mod.preset_daftar()]
    milik = [{**t, "bawaan": False} for t in supabase.template_list(user_id)]
    return [*bawaan, *milik]


def resolve(user_id: str, template_id: object = "") -> dict:
    """Kembalikan template milik user atau bawaan; ID asing selalu ditolak."""
    identitas = str(template_id or supabase.template_default(user_id) or DEFAULT_ID).strip()
    for template in daftar(user_id):
        if template["id"] == identitas:
            return template
    raise ValueError("Template tidak ditemukan.")


def skema(user_id: str, template_id: object = "") -> dict:
    """Skema ter-normalisasi untuk template bawaan atau milik user."""
    identitas = resolve(user_id, template_id)["id"]
    bawaan = skema_mod.preset_skema(identitas)
    if bawaan is not None:
        return skema_mod.normalisasi(bawaan)
    baris = supabase.template_get(user_id, identitas)
    if baris is None:
        raise ValueError("Template tidak ditemukan.")
    return skema_mod.normalisasi(baris.get("schema") or {})


def detail(user_id: str, template_id: object) -> dict:
    """Info template beserta skemanya, untuk dibuka di editor."""
    info = resolve(user_id, template_id)
    return {**info, "schema": skema(user_id, info["id"])}


def render_base(user_id: str, template_id: object, out_dir: Path) -> Path:
    """Kerangka DOCX untuk pekerjaan: hanya judul, identitas, dan blok keep.

    Isi jawaban belum ada; pipeline yang mengisi judul, identitas, dan jawaban.
    """
    berkas = Path(out_dir) / "kerangka.docx"
    return skema_mod.render(skema(user_id, template_id), berkas, "pekerjaan")


def pratinjau_docx(user_id: str, template_id: object = "", schema: dict | None = None) -> bytes:
    """DOCX pratinjau penuh (sampel lorem, semua blok) untuk galeri dan editor.

    Kalau `schema` diisi (dari editor), itu yang dipakai; selain itu template
    bawaan atau milik user.
    """
    with tempfile.TemporaryDirectory(prefix="tuton-pratinjau-") as tmp:
        sumber = skema_mod.normalisasi(schema) if schema is not None else skema(user_id, template_id)
        berkas = skema_mod.render(sumber, Path(tmp) / "pratinjau.docx", "pratinjau")
        return berkas.read_bytes()
