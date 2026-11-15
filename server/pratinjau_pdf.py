"""Pratinjau DOCX lewat PDF sementara hasil LibreOffice.

PDF hanya hidup selama pratinjau terbuka: klien memanggil `hapus()` saat
pratinjau ditutup. Kalau klien hilang tanpa sempat menutup (tab ditutup,
jaringan putus), `bersihkan_kadaluarsa()` menghapusnya setelah `TTL_DETIK`.
Setiap sesi terikat ke pemiliknya, jadi akun lain tidak bisa membaca atau
menghapusnya.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

TTL_DETIK = 600
TIMEOUT_KONVERSI = 120

# Satu proses LibreOffice dalam satu waktu. Dua instance dengan profil yang
# sama saling mengunci dan gagal diam-diam, jadi konversi diantrikan.
_KUNCI_KONVERSI = threading.Lock()
_KUNCI_SESI = threading.Lock()
_SESI: dict[str, dict] = {}


class PratinjauGagal(Exception):
    """Konversi tidak bisa dilakukan; pesannya aman ditampilkan ke pengguna."""


def _soffice() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def buat(user_id: str, docx_bytes: bytes) -> str:
    """Konversi DOCX ke PDF sementara dan kembalikan ID sesinya."""
    # DOCX adalah arsip ZIP. LibreOffice mau mengonversi apa pun (termasuk
    # teks biasa), jadi tanpa pemeriksaan ini berkas rusak lolos sebagai PDF.
    if not docx_bytes.startswith(b"PK\x03\x04"):
        raise PratinjauGagal("Berkas bukan DOCX yang sah.")
    exe = _soffice()
    if not exe:
        raise PratinjauGagal("LibreOffice belum terpasang di server.")
    bersihkan_kadaluarsa()

    folder = Path(tempfile.mkdtemp(prefix="pratinjau-"))
    try:
        sumber = folder / "sumber.docx"
        sumber.write_bytes(docx_bytes)
        profil = folder / "profil"  # profil LibreOffice terisolasi per sesi
        with _KUNCI_KONVERSI:
            proc = subprocess.run(
                [
                    exe,
                    f"-env:UserInstallation=file://{profil}",
                    "--headless",
                    "--norestore",
                    "--convert-to", "pdf",
                    "--outdir", str(folder),
                    str(sumber),
                ],
                capture_output=True,
                timeout=TIMEOUT_KONVERSI,
            )
        pdf = folder / "sumber.pdf"
        if proc.returncode != 0 or not pdf.is_file():
            raise PratinjauGagal("Konversi PDF gagal.")
        sumber.unlink()
        shutil.rmtree(profil, ignore_errors=True)
    except subprocess.TimeoutExpired:
        shutil.rmtree(folder, ignore_errors=True)
        raise PratinjauGagal("Konversi PDF melewati batas waktu.")
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise

    id_ = uuid.uuid4().hex
    with _KUNCI_SESI:
        _SESI[id_] = {"user": user_id, "folder": folder, "dibuat": time.monotonic()}
    return id_


def ambil_pdf(user_id: str, id_: str) -> bytes:
    """Isi PDF milik pemanggil. `KeyError` kalau tidak ada atau bukan miliknya."""
    with _KUNCI_SESI:
        sesi = _SESI.get(id_)
    if not sesi or sesi["user"] != user_id:
        raise KeyError(id_)
    return (sesi["folder"] / "sumber.pdf").read_bytes()


def hapus(user_id: str, id_: str) -> bool:
    """Hapus folder PDF sesi milik pemanggil. True kalau ada yang dihapus."""
    with _KUNCI_SESI:
        sesi = _SESI.get(id_)
        if not sesi or sesi["user"] != user_id:
            return False
        del _SESI[id_]
    shutil.rmtree(sesi["folder"], ignore_errors=True)
    return True


def bersihkan_kadaluarsa() -> int:
    """Hapus sesi yang melewati TTL. Kembalikan jumlah sesi yang dibersihkan."""
    batas = time.monotonic() - TTL_DETIK
    with _KUNCI_SESI:
        kadaluarsa = [k for k, s in _SESI.items() if s["dibuat"] < batas]
        sesi_list = [_SESI.pop(k) for k in kadaluarsa]
    for sesi in sesi_list:
        shutil.rmtree(sesi["folder"], ignore_errors=True)
    return len(sesi_list)
