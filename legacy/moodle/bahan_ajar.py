"""Bahan ajar wajib sesi, diambil tanpa model.

Halaman sesi UT hampir selalu menyebut buku yang harus dipakai, lalu menautkan
katalog resmi Perpustakaan UT. Contoh nyata dari halaman Sesi 4 Logika
Informatika:

    "silakan pelajari **BMP MSIM4103 Modul 4** sebagai referensi utama"
    Source: https://pustaka.ut.ac.id/lib/msim4103-logika-informatika-edisi-2/

Satu GET ke tautan itu sudah memberi metadata yang lengkap dan resmi: penulis,
edisi, tahun terbit, penerbit, ISBN. Itu persis bentuk Daftar Pustaka yang
diminta tutor, dan tautannya bisa dibuka dosen untuk checking sendiri. Jadi
modul ini menggantikan panggilan model `pencari-pustaka` pada kasus yang
umum: hemat satu proses `opencode run` per item, dan hasilnya tidak mungkin
mengarang karena tidak ada yang mengarang.

Referensi pelengkap dari luar tetap ditangani agen, tapi agennya baru dipanggil
kalau pathway ini tidak menghasilkan apa pun.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from config import Config

_TIMEOUT = 25
_CACHE_TTL = 7 * 24 * 3600
_CACHE_DIR = Config.TUTON_CACHE_DIR / "bahan_ajar"

# Halaman katalog resmi Perpustakaan UT. Hanya dua host ini yang boleh dipanggil.
_ALLOWED_HOSTS = frozenset({"pustaka.ut.ac.id", "opac.ut.ac.id"})

_SLUG_RE = re.compile(
    r"https?://(?:pustaka|opac)\.ut\.ac\.id/lib/([a-z0-9][a-z0-9\-]*)",
    re.IGNORECASE,
)

# Kalimat yang menunjuk sumber resmi sesi. Dipakai untuk mencari konteks yang
# menyebut buku mana yang dimaksud, bukan sekadar tautan mana yang ada.
_BAHAN_RE = re.compile(
    r"[^.\n]{0,160}?"
    r"(?:silakan\s+pelajari|bahan\s+ajar|buku\s+acuan|referensi\s+utama|"
    r"buku\s+yang\s+digunakan|modul\s+yang\s+harus\s+dipelajari)"
    r"[^.\n]{0,200}",
    re.IGNORECASE,
)

# "BMP MSIM4103 Modul 4" -> kode buku dan nomor modul.
_BMP_RE = re.compile(
    r"\bBMP\s+([A-Z]{2,}[A-Z0-9]*\d[A-Z0-9]*)\s*(?:Modul\s*(\d+))?",
    re.IGNORECASE,
)

# Label metadata di halaman katalog. Pola diambil longgar: nilai sering
# dibungkus tag atau tanda bintang, jadi harus tahan sisipan karakter apa pun.
_FIELD_LABELS = {
    "penulis": r"Penulis",
    "edisi": r"Edisi",
    "sks": r"SKS",
    "modul": r"Modul",
    "halaman": r"Halaman",
    "isbn": r"ISBN",
    "kota": r"Kota Terbit",
    "tahun": r"Tahun Terbit",
    "penerbit": r"Penerbit",
}

def _cache_path(url: str) -> Path:
    return _CACHE_DIR / f"{hashlib.sha1(url.encode()).hexdigest()}.json"


def _cache_get(url: str) -> dict | None:
    path = _cache_path(url)
    try:
        if time.time() - path.stat().st_mtime > _CACHE_TTL:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _cache_put(url: str, data: dict) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(url).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def _page_text(page_html: str) -> str:
    """HTML katalog -> teks polos satu label per baris."""
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", page_html)
    text = re.sub(r"(?s)<[^>]+>", "\n", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text)


def find_bahan_ajar(text: str) -> dict:
    """Cari bahan ajar wajib pada teks halaman sesi.

    Mengembalikan dict dengan kunci opsional `slug`, `url`, `kode`, `modul`,
    dan `kalimat`. Dict kosong berarti halaman ini tidak menyebut bahan ajar.
    """
    text = text or ""
    out: dict = {}

    match = _SLUG_RE.search(text)
    if match:
        slug = match.group(1)
        out["slug"] = slug
        out["url"] = f"https://pustaka.ut.ac.id/lib/{slug}/"

    kalimat = _BAHAN_RE.search(text)
    if kalimat:
        # Potongan kalimat diambil dari teks mentah dengan jendela lebar, lalu
        # dirapikan, supaya nama buku yang terpotong tidak ikut terpotong.
        start = max(0, kalimat.start())
        raw = text[start:start + 400]
        out["kalimat"] = re.sub(r"\s+", " ", raw).strip()[:300]

    bmp = _BMP_RE.search(text)
    if bmp:
        out["kode"] = bmp.group(1).upper()
        if bmp.group(2):
            out["modul"] = int(bmp.group(2))
    return out


def _clean_title(page_html: str) -> str:
    """Judul buku dari <h1>, atau <title> kalau <h1> tidak ada.

    <h1> dipakai lebih dulu karena <title> pada situs katalog selalu diberi
    imbuhan nama situs ("... - Perpustakaan UT") yang bukan bagian judul.
    """
    raw = ""
    h1 = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", page_html)
    if h1:
        raw = re.sub(r"<[^>]+>", " ", h1.group(1))
    else:
        title = re.search(r"(?is)<title[^>]*>(.*?)</title>", page_html)
        if title:
            raw = title.group(1)

    text = re.sub(r"\s+", " ", html.unescape(raw)).strip()
    for suffix in (
        r"\s*[|–—-]\s*(?:Perpustakaan|Bahan Ajar|Pustaka\s+UT|UT)\s*$",
        r"\s*\|\s*Libnara\s*$",
    ):
        text = re.sub(suffix, "", text, flags=re.IGNORECASE)
    return text.strip(" -–—|")


def _parse_citation(url: str, page_html: str) -> dict:
    text = _page_text(page_html)
    data: dict = {"url": url, "judul": _clean_title(page_html)}

    for key, label in _FIELD_LABELS.items():
        found = re.search(rf"(?im)^\s*{label}\s*[:\-]?\s*(.+?)\s*$", text)
        if not found:
            continue
        value = re.sub(r"\s+", " ", found.group(1)).strip(" *·-–—")
        if value and len(value) < 200:
            data[key] = value

    # "ISBN Elektronik" ikut cocok pola `ISBN`; pisahkan supaya dua angka
    # berbeda tidak tertukar.
    if "isbn" in data and re.match(r"(?i)elektronik", data["isbn"]):
        data["isbn_cetak"] = data.pop("isbn")

    # "Halaman 354 hlm. -- ilustrasi ;27 cm." -> cukup angka halamannya.
    halaman = re.search(r"(\d+)\s*hlm", data.get("halaman", ""))
    if halaman:
        data["halaman"] = halaman.group(1)

    tahun = re.search(r"\b(1[89]\d{2}|20\d{2})\b", data.get("tahun", ""))
    data["tahun"] = tahun.group(1) if tahun else ""

    return data


def fetch_citation(url: str) -> dict:
    """Ambil metadata satu halaman katalog. Satu GET, tanpa model.

    Mengembalikan dict metadata, atau dict kosong bila gagal. Kegagalan bukan
    kondisi yang ditangani khusus: pemanggil jatuh ke agen `pencari-pustaka`
    seperti sebelumnya.
    """
    url = str(url or "").strip()
    # Host dibandingkan sebagai hostname hasil parsing, bukan sebagai substring.
    # Cek substring akan menerima `pustaka.ut.ac.id.evil.example`, yang sama
    # sekali bukan situs UT -- halaman sesi bisa memuat tautan seperti itu.
    if not url or urlparse(url).hostname not in _ALLOWED_HOSTS:
        return {}

    cached = _cache_get(url)
    if cached is not None:
        return cached

    try:
        resp = requests.get(
            url,
            timeout=_TIMEOUT,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "id-ID,id;q=0.9",
            },
        )
        resp.raise_for_status()
    except (requests.RequestException, OSError):
        return {}

    data = _parse_citation(url, resp.text)
    if data.get("tahun"):
        _cache_put(url, data)
    return data if data.get("tahun") else {}


def apa7(data: dict) -> str:
    """Susun satu entri Daftar Pustaka bentuk APA 7 dari metadata katalog.

    Contoh: `Suprapto. (2025). Logika informatika (Edisi 2). Universitas Terbuka.`

    Tidak ada nomor di depan. APA 7 menomori daftar pustaka dengan urutan
    alfabetis, dan penomoran otomatis Word akan menghitung butir jawaban yang
    mendahuluinya -- bukan yang kita mau di sini.
    """
    if not data or not data.get("tahun"):
        return ""

    penulis = str(data.get("penulis") or "").strip() or "Universitas Terbuka"
    tahun = str(data["tahun"]).strip()
    # Judul dipakai persis seperti ditulis penerbit. Menurunkannya ke
    # sentence case lebih bersih secara tipografi, tapi kode ini tidak bisa
    # membedakan "Java" dan "MySQL" dari kata biasa -- salah kapitalisasi
    # pada nama diri justru lebih mencolok daripada Title Case.
    judul = re.sub(r"\s+", " ", str(data.get("judul") or "")).strip(" .")
    edisi = str(data.get("edisi") or "").strip()
    penerbit = str(data.get("penerbit") or "").strip()
    kota = str(data.get("kota") or "").strip()

    parts = [f"{penulis}. ({tahun})."]
    if judul:
        if edisi and not re.search(rf"edisi\s+{re.escape(edipi(edisi))}", judul, re.I):
            judul = f"{judul} (Edisi {edipi(edisi)})"
        parts.append(f" {judul}.")
    if penerbit:
        if kota and kota.lower() != penerbit.lower():
            parts.append(f" {kota}: {penerbit}.")
        else:
            parts.append(f" {penerbit}.")
    return "".join(parts).strip()


def edipi(value: str) -> str:
    """Pangkas sisa kalimat pada label angka, mis. '2 (Edisi 2)' -> '2'."""
    return re.sub(r"\s*\(.*$", "", str(value or "")).strip()


def referensi_dari_materi(page_text: str) -> dict:
    """Jalur singkat: teks halaman sesi -> bahan ajar plus sitasi APA 7.

    Mengembalikan `{"bahan": {...}, "sitasi": "...", "url": "..."}`. Nilai
    `sitasi` kosong kalau bahan ajar tidak ditemukan atau halamannya gagal
    diambil, dan pemanggil lalu memakai jalur agen.
    """
    bahan = find_bahan_ajar(page_text)
    url = bahan.get("url", "")
    if not url:
        return {"bahan": bahan, "sitasi": "", "url": ""}

    meta = fetch_citation(url)
    sitasi = apa7(meta)
    if not sitasi:
        return {"bahan": bahan, "sitasi": "", "url": url}
    return {"bahan": {**bahan, **meta}, "sitasi": sitasi, "url": url}


# Kode mata kuliah UT: 4-8 huruf/k angka yang diawali huruf dan mengandung
# angka, misalnya `MATA4113`, `STMA4113`, `MSIM4103`, `EKTP4101`. Pola ini
# dipakai untuk judul dokumen dan tidak boleh terlalu longgar: `sesi4` dan
# `modul2` bukan kode mata kuliah.
_RE_KODE_MK = re.compile(
    r"(?<![A-Za-z0-9])((?:MATA|STMA|MATM|MSI|MSIM|PK|EKTP|MK|TM|KB)"
    r"[A-Z]?\d{4})(?![A-Za-z0-9])"
)


def find_kode_matkul(text: str) -> str:
    """Kode mata kuliah yang disebut di teks halaman, atau string kosong.

    Dipakai untuk judul dokumen: `Diskusi 4 - Aljabar Linear Elementer 95
    (MATA4113)`. Tanpa kode, berkas yang dikumpulkan ke tutor dari beberapa
    mata exceedingly Kuliah akan sama-sama unidentified -- dan pengajar tidak
    bisa memastikan berkas itu miliknya.
    """
    m = _RE_KODE_MK.search(text or "")
    return m.group(1).upper() if m else ""
