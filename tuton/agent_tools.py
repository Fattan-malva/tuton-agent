"""Tool lokal untuk agent runner: baca/tulis berkas dan ambil halaman web.

Tool `bash` dan `subagent` tidak diimplementasikan karena spec agent sudah
menolaknya. Semua path dibatasi ke folder kerja (`cwd`), jadi model tidak bisa
menyentuh berkas di luar proyek walau prompt-nya keliru.
"""

from __future__ import annotations

import re
from pathlib import Path

import requests

from tuton import config
from tuton import html2md
from tuton import skills

MAKS_HASIL = 16_000
MAKS_BACA = 200_000
_USER_AGENT = "Mozilla/5.0 (compatible; tuton-agent/1.0)"

_DEFINISI: dict[str, dict] = {
    "read": {
        "description": "Baca isi satu berkas teks. Path relatif ke folder kerja.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "limit": {"type": "integer", "description": "Maksimum karakter"},
            },
            "required": ["path"],
        },
    },
    "write": {
        "description": "Tulis (buat/timpa) satu berkas teks, membuat folder induk bila perlu.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    "edit": {
        "description": "Ganti satu potongan teks di dalam berkas yang sudah ada.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    "glob": {
        "description": "Cari berkas berdasarkan pola, mis. `_kerja/**/*.md`.",
        "parameters": {
            "type": "object",
            "properties": {"pattern": {"type": "string"}},
            "required": ["pattern"],
        },
    },
    "grep": {
        "description": "Cari teks/regex di dalam berkas dan kembalikan path:baris.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "include": {"type": "string", "description": "Pola nama berkas"},
            },
            "required": ["pattern"],
        },
    },
    "webfetch": {
        "description": "Buka URL http/https dan kembalikan isinya sebagai teks/Markdown.",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    "skill": {
        "description": "Muat instruksi skill berdasarkan namanya.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
}

# Aksi di frontmatter agent -> tool lokal yang diberikan.
_PETA_IZIN = {
    "read": {"read"},
    "edit": {"write", "edit"},
    "glob": {"glob"},
    "grep": {"grep"},
    "webfetch": {"webfetch"},
    "skill": {"skill"},
}


def tools_untuk(izin: set[str]) -> list[dict]:
    nama = set()
    for aksi in izin:
        nama |= _PETA_IZIN.get(aksi, set())
    out = [
        {"type": "function", "function": {"name": n, **_DEFINISI[n]}}
        for n in _DEFINISI
        if n in nama
    ]
    return out


def _potong(teks: str, maks: int = MAKS_HASIL) -> str:
    teks = teks or ""
    if len(teks) <= maks:
        return teks
    return teks[:maks] + f"\n\n[... dipotong, {len(teks) - maks} karakter lagi ...]"


def _rahasia(p: Path) -> bool:
    """Berkas kredensial tidak boleh dibaca agent, walau path-nya sah."""
    try:
        rel = p.resolve().relative_to(config.BASE_DIR.resolve())
    except ValueError:
        return False
    return rel.parts[0] == "runtime" or rel.name.startswith(".env")


def _path(nilai: str, cwd: Path) -> Path:
    p = Path(nilai or "")
    if not p.is_absolute():
        p = cwd / p
    p = p.resolve()
    if not p.is_relative_to(cwd.resolve()):
        raise ValueError(f"Path di luar folder kerja tidak diizinkan: {nilai}")
    if _rahasia(p):
        raise ValueError("Berkas kredensial tidak boleh dibaca agent.")
    return p


def _arg(args: dict, *nama: str, bawaan: str = "") -> str:
    for n in nama:
        v = args.get(n)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return bawaan


def _skill(nama: str) -> str:
    # Salinan skill milik akun menimpa bawaan; jalur CLI tanpa login membaca
    # berkas `skills/` apa adanya.
    try:
        return _potong(skills.isi(config.current_user(), nama), MAKS_BACA)
    except ValueError:
        tersedia = [x["name"] for x in skills.daftar(config.current_user())]
        raise ValueError(
            f"Skill `{nama}` tidak ada. Yang tersedia: {', '.join(tersedia) or '-'}."
        )


def _webfetch(url: str) -> str:
    if not re.match(r"^https?://", url or "", re.I):
        raise ValueError("Hanya URL http/https yang bisa dibuka.")
    r = requests.get(
        url,
        headers={"User-Agent": _USER_AGENT},
        timeout=(10, 45),
        allow_redirects=True,
    )
    if r.status_code >= 400:
        raise ValueError(f"HTTP {r.status_code} dari {url}")
    ctype = (r.headers.get("Content-Type") or "").lower()
    if "html" in ctype:
        teks = html2md.ke_markdown(
            r.text,
            base_url=str(r.url),
            buang_mahasiswa=False,
            ambil_isi_saja=False,
        )
    else:
        teks = r.text
    if not (teks or "").strip():
        raise ValueError("Halaman tidak menghasilkan teks.")
    return _potong(teks)


def _grep(pattern: str, include: str) -> str:
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Regex tidak sah: {exc}") from exc
    pola = include or "*"
    if Path(pola).is_absolute():
        # Sama seperti `glob`: pola absolut tidak sah untuk rglob.
        try:
            pola = str(Path(pola).relative_to(config.BASE_DIR.resolve()))
        except ValueError:
            raise ValueError("Pola grep harus berada di folder proyek.")
    hasil: list[str] = []
    for path in config.BASE_DIR.rglob(pola):
        if not path.is_file() or ".git" in path.parts or "node_modules" in path.parts:
            continue
        if _rahasia(path):
            continue
        if path.stat().st_size > 1_000_000:
            continue
        try:
            isi = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for no, baris in enumerate(isi.splitlines(), 1):
            if rx.search(baris):
                rel = path.relative_to(config.BASE_DIR)
                hasil.append(f"{rel}:{no}: {baris.strip()[:200]}")
                if len(hasil) >= 100:
                    return "\n".join(hasil) + "\n[... hasil dipotong ...]"
    return "\n".join(hasil) or "(tidak ada hasil)"


def jalankan(nama: str, args: dict, cwd: Path) -> str:
    """Jalankan satu tool lokal; galat dikembalikan sebagai teks ke model."""
    try:
        args = args if isinstance(args, dict) else {}
        if nama == "read":
            path = _path(_arg(args, "path", "filePath", "file_path"), cwd)
            if not path.is_file():
                raise ValueError(f"Berkas tidak ada: {path.relative_to(cwd.resolve())}")
            data = path.read_bytes()[:MAKS_BACA]
            if b"\x00" in data:
                raise ValueError("Berkas biner; gunakan lampiran, bukan read.")
            limit = int(args.get("limit") or MAKS_BACA)
            return _potong(data.decode("utf-8", errors="replace"), limit)
        if nama == "write":
            path = _path(_arg(args, "path", "filePath", "file_path"), cwd)
            isi = args.get("content")
            if not isinstance(isi, str):
                raise ValueError("Argumen `content` wajib berupa teks.")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(isi, encoding="utf-8")
            return f"Tersimpan: {path.relative_to(cwd.resolve())} ({len(isi)} karakter)"
        if nama == "edit":
            path = _path(_arg(args, "path", "filePath", "file_path"), cwd)
            lama = _arg(args, "old_string", "oldString")
            baru = args.get("new_string", args.get("newString"))
            if not path.is_file():
                raise ValueError(f"Berkas tidak ada: {path.relative_to(cwd.resolve())}")
            isi = path.read_text(encoding="utf-8", errors="replace")
            if not lama or lama not in isi:
                raise ValueError("Teks lama tidak ditemukan; baca ulang berkasnya.")
            path.write_text(isi.replace(lama, str(baru or ""), 1), encoding="utf-8")
            return f"Tersunting: {path.relative_to(cwd.resolve())}"
        if nama == "glob":
            pola = _arg(args, "pattern") or "**/*"
            # Model kadang mengirim cwd absolut; pathlib.Path.glob hanya
            # menerima pola relatif. Normalisasi ke cwd sebelum globbing.
            if Path(pola).is_absolute():
                try:
                    pola = str(Path(pola).relative_to(cwd.resolve()))
                except ValueError:
                    raise ValueError("Pola glob harus berada di folder kerja agent.")
            hasil = []
            for p in cwd.glob(pola):
                if not p.is_file() or ".git" in p.parts or "node_modules" in p.parts:
                    continue
                if _rahasia(p):
                    continue
                hasil.append(str(p.relative_to(cwd.resolve())))
                if len(hasil) >= 200:
                    break
            return "\n".join(sorted(hasil)) or "(tidak ada berkas)"
        if nama == "grep":
            return _grep(_arg(args, "pattern"), _arg(args, "include"))
        if nama == "webfetch":
            return _webfetch(_arg(args, "url"))
        if nama == "skill":
            return _skill(_arg(args, "name"))
        raise ValueError(f"Tool tidak dikenal: {nama}")
    except (OSError, ValueError, requests.RequestException) as exc:
        return f"GALAT: {exc}"
