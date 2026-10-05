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

Auto-pilih hanya boleh memakai provider opencode zen (`opencode/...`). Model dari
provider lain (zai, ollama, ...) bergantung pada API key atau layanan yang hanya
hidup di host tertentu, jadi tidak bisa diandalkan untuk pipeline yang berjalan
di container.

Auto-pilih tidak mencoba menilai "kualitas" model (tidak ada metrik yang
andal). Ia hanya memberi skor murah berdasarkan penamaan, yang pada praktiknya
cukup memisahkan model kecil dari model besar:

    free  >  flash/lite/mini/nano/haiku  >  small  >  sisanya

TERTAK ADA: terdaftar di `opencode models` tidak berarti model itu hidup.
Endpoint bisa mati sementara ("Endpoint is unavailable") atau kena rate limit,
lalu gagal terus di tengah pipeline. Karena itu tiap kandidat diuji dengan satu
panggilan kecil, satu per satu, dan yang pertama benar-benar menjawab yang dipakai.
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
_probe_cache: dict[str, bool] = {}

# Auto-pilih hanya boleh memakai provider opencode zen. See module docstring.
_ZEN_PREFIX = "opencode/"

# Probe harus sekecil dan sesingkat mungkin: tugasnya hanya membuktikan model
# menjawab, bukan menilai kualitas jawabannya.
_PROBE_PROMPT = "Balas dengan satu karakter saja: X"
_PROBE_AGENT = "pemetak-soal"
_PROBE_TIMEOUT = 60


def _tier(model_id: str) -> int:
    low = model_id.lower()
    if any(h in low for h in _FREE_HINTS):
        return _TIER_FREE
    if any(h in low for h in _SMALL_HINTS):
        return _TIER_SMALL
    return _TIER_DEFAULT


def _probe_ok(model_id: str) -> bool:
    """True kalau model benar-benar menjawab satu panggilan kecil.

    Keberadaan di `opencode models` cuma berarti model terdaftar; endpoint-nya
    masih bisa mati atau kena rate limit. Tanpa uji ini, auto-pilih bisa
    terkunci ke model yang tidak bisa dipakai dan seluruh pipeline gagal di
    tengah jalan (referensi kosong, jawaban ditolak validator).
    """
    cached = _probe_cache.get(model_id)
    if cached is not None:
        return cached

    import contextlib  # impor lokal: hanya perlu saat probe jalan
    import io

    from generator.opencode_runner import run_opencode  # impor lokal: hindari siklus

    ok = False
    try:
        # Banner "→ opencode run ..." dan isi probe bukan informasi bagi pengguna.
        with contextlib.redirect_stdout(io.StringIO()):
            result = run_opencode(
                _PROBE_PROMPT,
                agent=_PROBE_AGENT,
                model=model_id,
                timeout=_PROBE_TIMEOUT,
            )
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        ok = result.returncode == 0 and bool(output)
    except Exception:  # noqa: BLE001 - probe gagal = model tidak dipakai
        ok = False

    _probe_cache[model_id] = ok
    return ok


def _auto_pick(exclude: tuple[str, ...] = ()) -> str:
    """Pilih model opencode zen termurah yang benar-benar bisa menjawab.

    Kandidat diuji satu per satu (lihat `_probe_ok`) karena urutannya diurutkan
    dari tier termurah dan nama, sehingga model terkecil keburu dipilih padahal
    endpoint-nya justru yang paling sering mati. Kalau semua kandidat gagal,
    dikembalikan string kosong supaya `opencode` memakai default-nya sendiri --
    lebih mungkin jalan daripada memaksa model yang baru saja terbukti mati.
    """
    from generator.opencode_runner import list_models  # impor lokal: menghindari siklus

    candidates = [m for m in list_models() if m and m not in exclude]
    if not candidates:
        print(
            "  ! daftar model opencode kosong/tidak terbaca, model dipakai default opencode",
            flush=True,
        )
        return ""
    # Hanya provider opencode zen; provider lain tidak bisa diandalkan.
    candidates = [m for m in candidates if m.startswith(_ZEN_PREFIX)]
    if not candidates:
        print(
            "  ! tidak ada model provider opencode yang tersedia, "
            "model dipakai default opencode",
            flush=True,
        )
        return ""
    # Stabil: skor dulu, lalu nama, supaya pilihan tidak berganti antar proses
    # hanya karena urutan `opencode models` berubah.
    candidates.sort(key=lambda m: (_tier(m), m))
    for model_id in candidates:
        if _probe_ok(model_id):
            return model_id
        print(
            f"  · model {model_id} tidak merespons, dicoba model berikutnya...",
            flush=True,
        )
    # Semua kandidat mati. opencode memakai default-nya sendiri; joked baik
    # compared to memaksa model yang baru saja terbukti tidak bisa menjawab.
    print(
        f"  ! semua {len(candidates)} model kandidat tidak merespons, "
        "model dipakai default opencode",
        flush=True,
    )
    return ""


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

    # Jangan cache hasil kosong. `opencode models` bisa gagal sesaat (mis. tepat
    # setelah container start), dan mengunci "" selama sisa proses membuat satu
    # kegagalan sesaat menentukan model untuk semua langkah berikutnya.
    if model:
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
    """Bersihkan cache resolusi + hasil probe (dipakai tes)."""
    with _lock:
        _resolved.clear()
        _probe_cache.clear()
