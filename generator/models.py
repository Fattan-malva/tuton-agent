"""Pemilihan model per peran, otomatis dari model yang benar-benar tersedia.

Ada dua kelas kerja dengan kebutuhan yang sangat berbeda:

- `writer`  -> agen `tuton`, satu-satunya yang menyusun jawaban. Butuh model
               kuat; tidak bisa di compromises karena outputnya yang dinilai.
- `helper`  -> agen `pemetak-soal` dan `pencari-pustaka`. Tugasnya sempit dan
               mekanis: "baca halaman ini, tulis brief terstruktur" dan
               "cari referensi, tulis maksimal 5 baris". Menjalankan model kuat
               untuk pekerjaan seperti itu membuang kuota tanpa hasil lebih baik.

Prinsip: jangan pernah gagal hanya karena model pilihanmu tidak ada. Kalau
`OPENCODE_MODEL_HELPER` diisi tapi model itu tidak ada di `opencode models`,
kita jatuh ke auto-pilih, bukan error. Model gratis/hilang sering datang dan
pergi, dan pipeline harus tetap jalan.

Auto-pilih tidak mencoba menilai "kualitas" model (tidak ada metrik yang
andal). Ia hanya memberi skor murah berdasarkan penamaan, yang pada praktiknya
cukup memisahkan model kecil dari model besar:

    free  >  flash/lite/mini/nano/haiku  >  small  >  sisanya
"""

from __future__ import annotations

import threading

from config import Config

# Peran yang dipetakan ke env/agen berbeda.
ROLE_WRITER = "writer"
ROLE_HELPER = "helper"

# Skor kecil = lebih murah. Nilai = tingkat.
_TIER_FREE = 0
_TIER_SMALL = 1
_TIER_DEFAULT = 2

# Urutan penANDA dari yang paling murah. Dicek sebagai substring id model
# (huruf kecil), jadi "mimo-v2.6-flash-free" kena dua tingkat sekaligus --
# itu memang yang kita mau: gratis DAN kecil.
_FREE_HINTS = ("free",)
_SMALL_HINTS = ("flash", "lite", "mini", "nano", "haiku", "small", "light")

_lock = threading.Lock()
_resolved: dict[tuple[str, ...], str] = {}


def _tier(model_id: str) -> int:
    low = model_id.lower()
    if any(h in low for h in _FREE_HINTS):
        return _TIER_FREE
    if any(h in low for h in _SMALL_HINTS):
        return _TIER_SMALL
    return _TIER_DEFAULT


def _auto_pick(exclude: tuple[str, ...] = ()) -> str:
    """Pilih model termurah yang tersedia dan belum dipakai peran lain."""
    from generator.opencode_runner import list_models  # impor lokal: hindari siklus

    candidates = [m for m in list_models() if m and m not in exclude]
    if not candidates:
        return ""
    # Stabil: skor dulu, lalu nama, supaya pilihan tidak berganti antar proses
    # hanya karena urutan `opencode models` berubah.
    candidates.sort(key=lambda m: (_tier(m), m))
    return candidates[0]


def resolve(role: str = ROLE_WRITER, *, exclude: tuple[str, ...] = ()) -> str:
    """Kembalikan id model untuk `role`, atau "" untuk pakai default opencode.

    String kosong bukan error: `opencode run` lalu memakai model default-nya
    sendiri. Itu lebih baik daripada memaksa id yang mungkin sudah tidak ada.
    """
    key = (role, *exclude)
    with _lock:
        if key in _resolved:
            return _resolved[key]

    configured = (
        Config.OPENCODE_MODEL if role == ROLE_WRITER
        else Config.OPENCODE_MODEL_HELPER
    ).strip()
    model = ""
    if configured:
        available = _available()
        # Kalau daftar model tidak bisa dibaca (CLI gagal/offline), percayai
        # env: menebak "tidak ada" lebih berbahaya daripada mencoba.
        if not available or configured in available:
            model = configured
    if not model:
        model = _auto_pick(exclude=exclude)

    with _lock:
        _resolved[key] = model
    return model


def _available() -> list[str]:
    from generator.opencode_runner import list_models

    return list_models()


def describe() -> dict[str, str]:
    """Ringkasan peran -> model, untuk log dan display."""
    writer = resolve(ROLE_WRITER)
    helper = resolve(ROLE_HELPER, exclude=(writer,) if writer else ())
    return {
        "writer": writer or "(default opencode)",
        "helper": helper or "(default opencode)",
    }


def reset_cache() -> None:
    """Bersihkan cache resolusi (dipakai tes)."""
    with _lock:
        _resolved.clear()
