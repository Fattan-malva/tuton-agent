"""Konfigurasi runtime: provider OpenAI-compatible, model per agent, MCP.

Disimpan di `runtime/runtime.json` (mode 0600) dan dibaca setiap kali dipakai supaya
perubahan dari menu UI langsung berlaku tanpa restart. API key tidak pernah
dikembalikan ke klien; pemanggil yang menyensor.
"""

from __future__ import annotations

import json
import os
import re

from tuton import config

AGENTS = ("scrapper", "research", "vision", "worker")
RUNTIME_FILE = config.BASE_DIR / "runtime" / "runtime.json"
_RE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _kosong() -> dict:
    return {"providers": [], "agents": {}, "mcp": []}


def muat() -> dict:
    """Baca `runtime.json`; berkas rusak/hilang menghasilkan struktur kosong."""
    data = _kosong()
    path = RUNTIME_FILE
    if not path.is_file():
        return data
    try:
        isi = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return data
    if not isinstance(isi, dict):
        return data
    for kunci in data:
        if isinstance(isi.get(kunci), type(data[kunci])):
            data[kunci] = isi[kunci]
    return data


def simpan(data: dict) -> None:
    """Tulis atomik + mode 0600: berkas berisi API key."""
    path = RUNTIME_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


# ----------------------------------------------------------------- provider


def providers() -> list[dict]:
    return [p for p in muat()["providers"] if isinstance(p, dict) and p.get("id")]


def provider(pid: str) -> dict | None:
    for p in providers():
        if p.get("id") == pid:
            return p
    return None


def semua_model() -> list[str]:
    """Daftar `provider/model` untuk pemilih model di UI."""
    out: list[str] = []
    for p in providers():
        pid = p.get("id") or ""
        for m in p.get("models") or []:
            m = str(m).strip()
            if pid and m:
                out.append(f"{pid}/{m}")
    return list(dict.fromkeys(out))


def _cari_ref(ref: str) -> tuple[dict | None, str]:
    """Pecah `provider/model`: nama model boleh mengandung garis miring."""
    ref = (ref or "").strip()
    if not ref:
        return None, ""
    if "/" in ref:
        pid, model = ref.split("/", 1)
        p = provider(pid)
        return (p, model) if p and model else (None, "")
    calon = [p for p in providers() if ref in (p.get("models") or [])]
    if len(calon) == 1:
        return calon[0], ref
    return None, ""


def resolve(ref: str) -> tuple[dict, str]:
    """Provider dan model ID dari sebuah referensi; galatnya ramah dibaca."""
    p, model = _cari_ref(ref)
    if p is None:
        raise ValueError(
            f"Model `{ref}` tidak cocok dengan provider mana pun. "
            "Pakai bentuk `provider/model` atau tambahkan model itu di menu Provider."
        )
    return p, model


def model_agent(agent: str, bawaan: str = "") -> str:
    nilai = str(muat()["agents"].get(agent) or "").strip()
    return nilai or bawaan


# --------------------------------------------------------------------- MCP


def mcp_untuk(agent: str) -> list[dict]:
    """Server MCP aktif yang boleh dipakai satu agent."""
    out: list[dict] = []
    for s in muat()["mcp"]:
        if not isinstance(s, dict) or not s.get("id") or not s.get("url"):
            continue
        if s.get("enabled") is False:
            continue
        agents = s.get("agents") or []
        if agent not in agents:
            continue
        out.append(s)
    return out


def id_valid(nilai: str) -> bool:
    return bool(_RE_ID.fullmatch(nilai or ""))


def slug(nilai: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", (nilai or "").lower()).strip("-")
