"""Konfigurasi runtime: provider OpenAI-compatible dan model per agent.

Sumber data ditentukan oleh konteks:

- **Web (akun login)**: tabel Supabase `user_providers`, satu baris per akun
  (`config.current_provider_data()`). API key satu akun tidak pernah dilihat
  akun lain, dan berkas `runtime/runtime.json` tidak lagi dipakai bersama.
- **CLI (`python main.py`)**: `runtime/runtime.json` seperti sebelumnya, supaya
  pemakaian lokal tanpa login tetap jalan.

Semua fungsi di bawah memilih sumber itu sendiri, jadi pemanggil (pipeline,
agent runner, endpoint UI) tidak perlu tahu bedanya. Data dibaca setiap kali
dipakai supaya perubahan dari menu UI langsung berlaku tanpa restart. API key
tidak pernah dikembalikan ke klien; penyaringan ada di `server/app.py`.

Provider lama di berkas dimigrasikan ke akun yang sedang login saat pertama
kali mengakses provider (`migrasi_ke_user`), jadi API key yang sudah ada tidak
hilang setelah perubahan ini.
"""

from __future__ import annotations

import json
import os
import re
import threading

from tuton import config
from tuton import supabase

AGENTS = ("scrapper", "research", "vision", "worker")
RUNTIME_FILE = config.BASE_DIR / "runtime" / "runtime.json"
# Penanda bahwa migrasi berkas -> akun sudah dikerjakan. Di dalam berkas, bukan
# di memori: server bisa di-restart kapan saja, dan migrasi yang berjalan dua
# kali akan menimpa provider akun dengan isi berkas lama.
_MIGRASI_KUNCI = "migrated_to_user"
# Akun yang sudah dicek pada proses ini. Tanpa ini, setiap request dari akun
# yang memang belum punya provider akan membaca `runtime.json` lagi.
_MIGRASI_DICOBA: set[str] = set()
_MIGRASI_LOCK = threading.Lock()
_RE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _kosong() -> dict:
    return {"providers": [], "agents": {}}


# ------------------------------------------------------------------ penyimpanan


def _muat_berkas() -> dict:
    """Baca `runtime.json` apa adanya; berkas rusak/hilang menghasilkan kosong."""
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
    # Kunci penanda migrasi ikut dipertahankan supaya `simpan_berkas` tidak
    # menghapusnya saat berkas dibaca lalu ditulis ulang.
    for kunci in isi:
        if kunci not in data:
            data[kunci] = isi[kunci]
    return data


def simpan_berkas(data: dict) -> None:
    """Tulis atomik + mode 0600: berkas berisi API key (khusus jalur CLI)."""
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


def _bersih(data: dict) -> dict:
    out = _kosong()
    providers = data.get("providers")
    if isinstance(providers, list):
        out["providers"] = [p for p in providers if isinstance(p, dict) and p.get("id")]
    agents = data.get("agents")
    if isinstance(agents, dict):
        out["agents"] = {str(k): str(v) for k, v in agents.items() if v}
    return out


def muat() -> dict:
    """Data provider+agent yang berlaku di konteks sekarang.

    Akun web memakai baris Supabase-nya (bisa kosong); CLI memakai berkas.
    """
    data = config.current_provider_data()
    if data is None:
        return _bersih(_muat_berkas())
    return _bersih(data)


def simpan(data: dict) -> None:
    """Tulis data provider ke sumber yang sesuai konteks."""
    bersih = _bersih(data)
    user_id = config.current_user()
    if user_id:
        supabase.providers_simpan(user_id, bersih)
        return
    lama = _muat_berkas()
    if _MIGRASI_KUNCI in lama:
        bersih[_MIGRASI_KUNCI] = lama[_MIGRASI_KUNCI]
    simpan_berkas(bersih)


def migrasi_ke_user(user_id: str | None = None) -> bool:
    """Pindahkan provider dari `runtime.json` ke akun aktif, sekali saja.

    Dipanggil saat pertama kali sebuah akun memakai fitur yang butuh provider.
    Syaratnya: ada akun login, baris provider akun itu masih kosong, berkas
    masih punya provider, dan penanda migrasi belum ada. Berkas tidak dihapus
    -- isinya tetap jadi cadangan untuk CLI -- tetapi penanda membuat akun
    berikutnya tidak ikut mengambil API key yang sama.

    Mengembalikan `True` kalau data benar-benar dipindahkan.
    """
    user_id = str(user_id or config.current_user())
    if not user_id:
        return False
    # Panggilan ini bisa terjadi sebelum scope dipasang (saat autentikasi
    # request), jadi barisnya dibaca langsung dari Supabase.
    if supabase.providers_data(user_id).get("providers"):
        return False
    with _MIGRASI_LOCK:
        if user_id in _MIGRASI_DICOBA:
            return False
        _MIGRASI_DICOBA.add(user_id)
    berkas = _muat_berkas()
    if not berkas.get("providers") or _MIGRASI_KUNCI in berkas:
        return False
    try:
        supabase.providers_simpan(user_id, _bersih(berkas))
    except (ValueError, OSError):
        return False
    berkas[_MIGRASI_KUNCI] = user_id
    try:
        simpan_berkas(berkas)
    except OSError:
        pass
    return True


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


def id_valid(nilai: str) -> bool:
    return bool(_RE_ID.fullmatch(nilai or ""))


def slug(nilai: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", (nilai or "").lower()).strip("-")
