"""Enkripsi kredensial yang disimpan di Supabase (cookie Moodle).

Cookie Moodle adalah kredensial hidup: siapa pun yang memegang nilainya bisa
membuka akun mahasiswa selama sesi belum kedaluwarsa. Karena itu nilainya
tidak pernah disimpan apa adanya di database, melainkan sebagai token Fernet
dengan kunci simetris `COOKIE_ENCRYPTION_KEY` dari `.env`.

Nilai lama yang masih plaintext tetap bisa dibaca (`dekripsi` mengembalikannya
apa adanya) supaya data sebelum perubahan ini tidak hilang; `supabase._get`
mengenkripsi ulang baris seperti itu sekali saat dibaca.

Membuat kunci baru:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Kunci yang hilang/berubah membuat token lama tidak bisa dibaca; pengguna harus
menempel ulang cookie Moodle-nya. Itu disengaja -- lebih baik meminta ulang
daripada diam-diam memakai kunci lemah.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from tuton import config

# Penanda versi/format di depan token. Nilai tanpa awalan ini dianggap
# plaintext lama, bukan ciphertext yang rusak.
AWALAN = "v1:"


def _fernet() -> Fernet:
    """Fernet dari `.env`; melempar `ValueError` kalau kuncinya belum siap."""
    kunci = config.env("COOKIE_ENCRYPTION_KEY")
    if not kunci:
        raise ValueError(
            "COOKIE_ENCRYPTION_KEY belum diisi di .env. Buat kuncinya dengan: "
            "python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\" lalu simpan sebagai "
            "COOKIE_ENCRYPTION_KEY=<kunci>."
        )
    try:
        return Fernet(kunci.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise ValueError(
            "COOKIE_ENCRYPTION_KEY bukan kunci Fernet yang sah "
            "(harus 44 karakter base64 urlsafe)."
        ) from exc


def tersedia() -> bool:
    """True kalau kunci ada dan bisa dipakai (tanpa melempar galat)."""
    try:
        _fernet()
        return True
    except ValueError:
        return False


def terenkripsi(nilai: str) -> bool:
    return str(nilai or "").startswith(AWALAN)


def enkripsi(nilai: str) -> str:
    """Enkripsi satu nilai; string kosong tetap kosong.

    Nilai yang sudah terenkripsi dikembalikan apa adanya supaya pemanggil
    tidak perlu memeriksa bentuknya lebih dulu.
    """
    nilai = str(nilai or "")
    if not nilai or terenkripsi(nilai):
        return nilai
    token = _fernet().encrypt(nilai.encode("utf-8")).decode("ascii")
    return AWALAN + token


def dekripsi(nilai: str) -> str:
    """Buka satu nilai. Plaintext lama dikembalikan apa adanya.

    Token yang tidak bisa dibuka (kunci berganti/rusak) menghasilkan string
    kosong: UI lalu menampilkan "cookie belum diisi" dan pengguna menempel
    ulang, bukan memakai kredensial yang salah tanpa penjelasan.
    """
    nilai = str(nilai or "")
    if not nilai:
        return ""
    if not terenkripsi(nilai):
        return nilai
    try:
        return _fernet().decrypt(nilai[len(AWALAN):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return ""
