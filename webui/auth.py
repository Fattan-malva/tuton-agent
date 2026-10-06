"""Gerbang sederhana untuk UI web lokal.

Bukan sistem akun penuh: cukup satu pasangan pengguna/kata sandi dari `.env`
(`APP_USERNAME` / `APP_PASSWORD`). Kata sandi kosong berarti UI tidak
memintanya -- hanya untuk pemakaian sendiri di mesin yang aman. Sesinya
berupa token yang ditandatangani HMAC dengan rahasia acak per proses, agar
cookie tidak bisa dipalsu.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time


def buat_secret() -> str:
    return secrets.token_hex(32)


def verifikasi(
    username: str, password: str, app_username: str, app_password: str
) -> bool:
    """True kalau pasangan cocok. Bandingkan konstant-waktu."""
    if not hmac.compare_digest(username, app_username):
        return False
    if not app_password:
        # Kata sandi kosong di .env: login ditolak agar tidak terkunci.
        return False
    return hmac.compare_digest(password, app_password)


def tanda(secret: str, username: str, masa_detik: int = 60 * 60 * 12) -> str:
    """Buat token sesi: `<user>.<exp>.<sig>`."""
    exp = int(time.time()) + masa_detik
    payload = f"{username}.{exp}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}"


def cek_tanda(token: str, secret: str) -> bool:
    """True kalau token sah dan belum kedaluwarsa."""
    if not token or token.count(".") < 2:
        return False
    payload, sig = token.rsplit(".", 1)
    try:
        username, exp = payload.rsplit(".", 1)
        exp = int(exp)
    except ValueError:
        return False
    harapan = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, harapan):
        return False
    return time.time() < exp
