"""Skill jawaban: bawaan repo (`skills/<nama>/SKILL.md`) + salinan milik akun.

Bawaan dibaca dari disk dan dipakai bersama semua akun. Mengedit skill bawaan
hanya membuat salinan milik akun itu di Supabase, jadi akun lain tetap memakai
versi bawaannya. Skill default menentukan instruksi yang dipakai pipeline.
"""

from __future__ import annotations

import re

from tuton import config
from tuton import supabase

DEFAULT_ID = "naskah-id"


def _nama(nilai: object) -> str:
    nama = str(nilai or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", nama):
        raise ValueError("Nama skill hanya huruf kecil, angka, garis, dan garis bawah.")
    return nama


def _bawaan(nama: str) -> str | None:
    path = config.SKILLS_DIR / nama / "SKILL.md"
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def daftar(user_id: str) -> list[dict]:
    """Semua skill yang terlihat akun ini, dengan penanda bawaan/diubah/default."""
    milik = {
        str(row.get("name") or ""): row
        for row in supabase.skill_list(user_id)
        if row.get("name")
    }
    default = supabase.skill_default(user_id) or DEFAULT_ID
    nama = sorted({*milik, *(x.parent.name for x in config.SKILLS_DIR.glob("*/SKILL.md"))})
    out = []
    for n in nama:
        isi = str((milik.get(n) or {}).get("content") or "") or _bawaan(n) or ""
        out.append({
            "name": n,
            "bawaan": n not in milik,
            "ukuran": len(isi.encode("utf-8")),
            "default": n == default,
        })
    return out


def default_id(user_id: str) -> str:
    """Skill default akun; jatuh ke bawaan kalau pilihannya sudah tidak ada."""
    pilih = supabase.skill_default(user_id) or DEFAULT_ID
    tersedia = {x["name"] for x in daftar(user_id)}
    return pilih if pilih in tersedia else (
        DEFAULT_ID if DEFAULT_ID in tersedia else ""
    )


def isi(user_id: str, nama: object) -> str:
    """Isi SKILL.md: salinan akun lebih dulu, lalu berkas bawaan."""
    nama = _nama(nama)
    milik = supabase.skill_get(user_id, nama)
    if milik is not None and str(milik.get("content") or "").strip():
        return str(milik["content"])
    bawaan = _bawaan(nama)
    if bawaan is None:
        raise ValueError(f"Skill `{nama}` tidak ditemukan.")
    return bawaan


def simpan(user_id: str, nama: object, content: object) -> dict:
    """Tulis salinan milik akun; versi bawaan di disk tidak pernah diubah."""
    nama = _nama(nama)
    teks = str(content or "")
    if not teks.strip():
        raise ValueError("Isi skill tidak boleh kosong.")
    if not user_id:
        raise ValueError("Skill per akun butuh login.")
    supabase.skill_save(user_id, nama, teks)
    return {"ok": True, "name": nama}


def hapus(user_id: str, nama: object) -> dict:
    """Hapus salinan akun. Skill bawaan kembali ke versi aslinya."""
    nama = _nama(nama)
    supabase.skill_delete(user_id, nama)
    if supabase.skill_default(user_id) == nama:
        supabase.skill_set_default(user_id, "")
    return {"ok": True, "name": nama}


def set_default(user_id: str, nama: object) -> dict:
    nama = _nama(nama)
    isi(user_id, nama)  # tolak nama asing sebelum menyimpan pilihan
    supabase.skill_set_default(user_id, nama)
    return {"ok": True, "default": nama}


def prompt(user_id: str) -> str:
    """Satu baris instruksi untuk prompt worker: muat skill default akun."""
    nama = default_id(user_id)
    if not nama:
        return ""
    return (
        f"Pakai skill `{nama}` dalam mode File pada berkas jawaban ini "
        "(muat dulu dengan tool `skill`, lalu terapkan pada berkasnya)."
    )