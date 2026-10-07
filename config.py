"""Konfigurasi terpusat: .env, path kerja, dan batas agent.

Semua modul lain mengimpor dari sini, tidak ada yang membaca `.env` sendiri.
Satu sumber kebenaran membuat batas agent (jumlah referensi, tahun minimal) bisa
diubah dari satu tempat tanpa menyunting spec agent di `.opencode/agents/`.
"""

from __future__ import annotations

import os
import re
import shutil
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------- path kerja

BASE_DIR = Path(__file__).resolve().parent
TOOLS_DIR = BASE_DIR / "tools"
TEMPLATE_DIR = BASE_DIR / "template"

# `tools/docx.py` mengimpor `from config import TEMPLATE_DIR`, jadi nama di sini
# dipakai langsung oleh sana dan tidak boleh diubah.

OUTPUT_DIR = BASE_DIR / "output"
CACHE_DIR = BASE_DIR / "cache"
KERJA_DIR = BASE_DIR / "_kerja"


def work_dirs(slug: str, nomor: int | None = None) -> dict[str, Path]:
    """Folder kerja untuk satu mata kuliah, atau satu sesi mata kuliah.

    Dua tingkat pemisahan, keduanya perlu:

    - **Per mata kuliah.** Peta soal sesi 2 mata kuliah A bukan peta soal sesi 2
      mata kuliah B. Tanpa pemisahan ini keduanya menulis ke
      `_petak/sesi2.md` yang sama dan saling menimpa.
    - **Per sesi.** Kalau satu sesi dijalankan ulang dengan versi agent yang
      lebih baru, seluruh isi sesi lama (peta, transkrip, draf jawaban, log)
      akan hilang dan tidak bisa dibandingkan dengan hasil baru. Folder
      keluaran juga sudah dipanggil per sesi, dan lampiran yang belum selesai
      diunduh tidak ikut terpotong oleh sesi berikutnya.

    `nomor` boleh `None` untuk pemanggilan yang hanya butuh folder induk,
    misalnya saat membersihkan cache.
    """
    root = KERJA_DIR / slug
    if nomor is not None:
        root = root / f"sesi-{nomor}"
    return {
        "root": root,
        "matkul": KERJA_DIR / slug,
        "petak": root / "_petak",
        "berkas": root / "_berkas",
        "bahan": root / "_bahan",
        "jawaban": root / "_jawaban",
        "log": root / "_log",
    }


def output_dir(slug: str, nomor: int) -> Path:
    """Folder keluaran untuk satu sesi: `output/<matkul>/sesi-<N>/`.

    Nama folder tetap per nomor sesi supaya penelusuran lama tidak berubah.
    Berkas di dalamnya memakai `<slug>_<Jenis>.<nomor>.docx` -- jenis dan
    nomor kegiatan (Diskusi/Tugas), bukan nomor sesi, sehingga nama ikut
    cocok dengan baris di laporan nilai. Lihat `Pipeline._nama_dokumen`.
    """
    return OUTPUT_DIR / slug / f"sesi-{nomor}"


# ---------------------------------------------------------------- pemuatan .env

_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def load_dotenv(path: Path | None = None) -> dict[str, str]:
    """Baca `.env` tanpa dependensi, lalu isi ke `os.environ`.

    `os.environ.setdefault` dipakai supaya variabel yang sudah di-set dari shell
    menang atas isi `.env`. Itu yang membuat pipeline bisa diuji tanpa mengedit
    berkas yang berisi cookie.
    """
    path = Path(path) if path else BASE_DIR / ".env"
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        m = _ENV_LINE.match(raw)
        if not m:
            continue
        key, value = m.group(1), _strip_quotes(m.group(2))
        values[key] = value
        os.environ.setdefault(key, value)
    return values


ENV = load_dotenv()


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


# ---------------------------------------------------------------- moodle

URL_MOODLE = env("URL_MOODLE").rstrip("/")
COOKIE_MOODLE = env("COOKIE_MOODLE")

# Nama cookie sesi Moodle. Nilai di `.env` hanya berisi nilai tanpa nama, jadi
# namanya dipasang di sini.
MOODLE_COOKIE_NAME = "MoodleSession"

# Batas server UT: `sessiontimeout` di halaman depan adalah 21600 detik. Cookie
# yang sudah lewat batas ditolak Moodle, dan pipeline hanya melihat halaman
# login. Gejalanya paling sering disalahartikan sebagai "matkul tidak ada",
# jadi `moodle.cek_login()` memeriksa penanda sudah masuk, bukan status 200.
SESSION_TIMEOUT_SECONDS = 21600


# ---------------------------------------------------------------- model

PRIMARY_MODEL = env("PRIMARY_MODEL", "opencode/big-pickle")
VISION_MODEL = env("VISION_MODEL", "ollama-cloud/gemma4:31b")


# ---------------------------------------------------------------- web app

# Kredensial gerbang UI lokal. Kosongkan APP_PASSWORD agar UI tidak
# memintanya (tidak disarankan bila mesin dipakai bersama).
APP_USERNAME = env("APP_USERNAME", "admin")
APP_PASSWORD = env("APP_PASSWORD", "")

# Alamat tempat server web mendengarkan. Default hanya localhost supaya
# cookie Moodle dan tombol peluncur agent tidak terbuka ke jaringan luar.
WEB_HOST = env("WEB_HOST", "127.0.0.1")
try:
    WEB_PORT = int(env("WEB_PORT", "8000"))
except ValueError:
    WEB_PORT = 8000


def set_env_value(key: str, value: str) -> None:
    """Tulis ulang satu nilai di `.env` tanpa mengubah baris lain.

    Dipakai oleh menu Pengaturan di UI. Nilai tidak di-quote: `load_dotenv`
    sudah membaca nilai sampai akhir baris, jadi token berisi `=` tetap utuh.
    Pemanggil bertanggung jawab menyensor nilai rahasia (cookie, password)
    sebelum menampilkannya kembali ke klien.
    """
    path = BASE_DIR / ".env"
    # .env satu baris per kunci: buang newline yang tidak sengaja ikut
    # ter-tempel saat nilai (mis. cookie) disalin dari halaman lain.
    value = str(value).replace("\r", "").replace("\n", "").strip()
    baris = (
        path.read_text(encoding="utf-8", errors="replace").splitlines()
        if path.is_file() else []
    )
    out: list[str] = []
    ditemu = False
    for raw in baris:
        m = _ENV_LINE.match(raw)
        if m and m.group(1) == key:
            out.append(f"{key}={value}")
            ditemu = True
        else:
            out.append(raw)
    if not ditemu:
        out.append(f"{key}={value}")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    os.environ[key] = value
    if key in globals():
        # WEB_PORT disimpan sebagai int supaya tipe global config tidak
        # berganti dari int ke str hanya karena lewat menu Pengaturan.
        globals()[key] = int(value) if key == "WEB_PORT" and value.isdigit() else value


# ---------------------------------------------------------------- identitas

# `tools/docx.py` menghapus baris tabel yang nilainya kosong, supaya identitas
# mahasiswa contoh di template tidak ikut bocor. Nama key di sini harus persis
# sama dengan yang dicari `_IDENTITAS_LABELS` di sana.
IDENTITAS_KEYS = ("nama", "nim", "semester", "ut_daerah", "prodi")


def identitas() -> dict[str, str]:
    """Identitas mahasiswa untuk tabel kop DOCX.

    Nilai yang tidak diisi dikembalikan sebagai string kosong, bukan `None`.
    `build_docx` memanggil `str(v).strip()` untuk tiap nilai, jadi `None`
    menjadi teks `"None"` di dokumen, bukan baris yang dihapus.
    """
    return {key: env(key.upper()) for key in IDENTITAS_KEYS}


# ---------------------------------------------------------------- batas agent

# Batas research. `research.md` menulis `{MAX}` dan `{TAHUN_MIN}` sebagai
# placeholder, jadi pipeline menulis salinan spec yang sudah di-resolve per run.
MAX_REFERENSI = 5
TAHUN_MIN = date.today().year - 10  # "10 tahun terakhir"

# Jumlah halaman yang boleh dibuka scrapper untuk satu sesi. Spec aslinya 12;
# satu sesi nyata bisa punya 1 forum + 1 tugas + beberapa lampiran + 1 halaman
# bahan ajar, dan 12 kadang habis sebelum semuanya sempat dibuka.
BATAS_HALAMAN_SESI = 18

# Berapa karakter teks soal yang disisipkan ke prompt pemetaan dan prompt
# penulis. Pipeline sudah membuka halaman soal sendiri, jadi teksnya dikirim
# apa adanya; batas ini hanya menjaga agar post forum yang panjang tidak
# menelan seluruh jendela konteks agent.
BATAS_TEKS_SOAL = 6000

# Berapa berkas montage yang boleh dikirim ke model penglihatan untuk satu
# lampiran. Setiap montage adalah satu panggilan `opencode run` dengan model
# vision, jadi angka ini pengatur biaya, bukan saran.
BATAS_MONTASE_PER_LAMPIRAN = 6

# Berapa banyak rekaman 127.0.0.1 yang boleh dibuka per FILE pada Reader
# lokal. Peta soal boleh membuka sampai BATAS_HALAMAN_SESI halaman.
BATAS_URL_CADANGAN = 6

# Berapa kali percobaan ulang saat panggil agent. Percobaan kedua hanya
# dilakukan kalau berkas hasil belum ada atau isinya cuma kerangka, jadi ini
# batas, bukan target.
MAX_Coba_AGENT = 2
TIMEOUT_AGENT_DETIK = 900

# Ukuran minimum berkas hasil agent agar dianggap selesai. Tanpa ambang ini
# peta soal yang sudah ditulis lengkap tapi tidak ditutup `SELESAI` akan
# dipanggil ulang, dan percobaan kedua bisa menimpanya dengan isi lebih
# pendek. Angka ini di bawah ukuran peta soal yang wajar (puluhan ribu byte)
# tapi di atas kerangka berisi judul saja (ratusan byte).
MIN_ISI_HASIL = 800


# ------------------------------------------------------- cari executable opencode

# Windows hanya menempelkan ekstensi `.exe` saat `CreateProcess` mencari
# program di PATH. `shutil.which("opencode")` di mesin ini mengembalikan
# `...\npm\opencode.CMD` -- shim yang dibuat `npm install`, bukan programnya.
# Memanggil shim itu tanpa shell berakhir dengan FileNotFoundError yang
# menyesatkan, karena opencode sebenarnya terpasang.
#
# Jadi shim dibaca dulu: npm menuliskan path `.exe` asli di dalamnya, dan
# path itu yang dipakai sebagai perintah. Kalau shim tidak bisa dibaca,
# lokasi standar paket npm diperiksa, dan terakhir barulah shim dipakai
# lewat `cmd /c`.
_RE_EXE_DALAM_SHIM = re.compile(r'"%dp0%\\([^"]+\.exe)"', re.I)

# Shim npm cuma beberapa KB, tapi `opencode` yang ditemukan `shutil.which`
# di Linux/macOS adalah binary asli atau symlink ke binary (± 200 MB di
# mesin ini). Regex di atas tetap tidak akan cocok di dalam binary, jadi
# membaca seluruhnya hanya membuang waktu: tanpa batas ini satu panggilan
# `cari_opencode()` butuh 4-21 detik, cukup untuk membuat halaman UI dan
# tiap langkah agent terasa macet.
_BATAS_SHIM_BESAR = 1_048_576  # 1 MB


def _executable_dari_shim(shim: Path) -> Path | None:
    """Ambil path `.exe` asli yang ditunjuk shim npm."""
    try:
        if shim.stat().st_size > _BATAS_SHIM_BESAR:
            return None
        isi = shim.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for cocok in _RE_EXE_DALAM_SHIM.findall(isi):
        kandidat = shim.parent / cocok
        if kandidat.is_file():
            return kandidat
    return None


def _executable_dari_paket(shim: Path) -> Path | None:
    """Cari `.exe` di lokasi paket yang biasa dipakai `npm install -g`."""
    akar = shim.parent
    for relatif in (
        Path("node_modules") / "@opencode" / "cli" / "bin" / "opencode.exe",
        Path("node_modules") / "opencode-ai" / "bin" / "opencode.exe",
    ):
        kandidat = akar / relatif
        if kandidat.is_file():
            return kandidat
    for kandidat in sorted(akar.glob("opencode*.exe")):
        if kandidat.is_file():
            return kandidat
    return None


# Hasil sukses `cari_opencode()`; `None` berarti belum pernah dicari.
_CACHE_OPENCODE: Path | None = None


def cari_opencode() -> Path | None:
    """Path executable opencode yang benar-benar bisa dijalankan.

    Mengembalikan `None` kalau opencode tidak terpasang sama sekali. Shim
    `.cmd`/`.bat` yang tidak bisa dipetakan ke `.exe` tetap dikembalikan;
    pemanggil yang harus menjalankannya lewat `cmd /c`.

    Hasil sukses disimpan di memori (`_CACHE_OPENCODE`): pipeline memanggil
    fungsi ini tiap langkah agent dan UI tiap memuat status/model, jadi
    pencarian diulang-ulang cuma memperlambat. Pencarian GAGAL tidak
    disimpan supaya opencode yang baru dipasang langsung ketahuan tanpa
    perlu restart proses.
    """
    global _CACHE_OPENCODE
    if _CACHE_OPENCODE is not None:
        return _CACHE_OPENCODE
    ditemukan = shutil.which("opencode")
    if not ditemukan:
        return None
    shim = Path(ditemukan)
    if shim.suffix.lower() in (".exe", ".com"):
        _CACHE_OPENCODE = shim
        return shim
    for pemeta in (_executable_dari_shim, _executable_dari_paket):
        asli = pemeta(shim)
        if asli is not None:
            _CACHE_OPENCODE = asli
            return asli
    _CACHE_OPENCODE = shim
    return shim


# ---------------------------------------------------------------- agent

# Nama agent di `.opencode/agents/`. Harus sama persis dengan nama berkas
# minus ekstensi.
AGENT_SCRAPPER = "scrapper"
AGENT_RESEARCH = "research"
AGENT_VISION = "vision"
AGENT_WORKER = "worker"

AGENTS_DIR = BASE_DIR / ".opencode" / "agents"


# ---------------------------------------------------------------- reader lokal

READER_HOST = "127.0.0.1"
# Port 0 = minta port bebas dari OS. Reader ini memegang sesi Moodle yang
# aktif, jadi biarkan OS yang memilih portnya.
READER_PORT = 0

TARGET_SOAL = "soal"
TARGET_MATERI = "materi"

# Lama cache HTML dalam detik. Halaman course format onetopic berukuran besar
# dan isinya jarang berubah dalam satu hari kerja.
TTL_CACHE_DETIK = 3600

# Batas ukuran unduhan lampiran, supaya lampiran besar tidak mengisi disk.
MAX_UNDUH_MB = 60


# ---------------------------------------------------------------- identitas matkul

# Kode mata kuliah UT muncul di nama course, misalnya "ALEA4213". Polanya cukup
# sempit untuk tidak salah menangkap kata biasa.
RE_KODE_MATKUL = re.compile(r"\b([A-Z]{4}\d{4})\b")

# Kode kelas biasanya berupa angka di akhir nama course, misalnya
# "Aljabar Linear Elementer 95".
RE_KELAS = re.compile(r"\s(\d{1,3})\s*$")


def slugify(text: str, fallback: str = "matkul") -> str:
    r"""Slug aman untuk nama folder di Windows.

    Windows menolak `<>:"/\|?*` dan nama yang berakhiran titik atau spasi. Nama
    course UT mengandung tanda hubung, spasi, dan kadang kurung, jadi slug tidak
    boleh hanya `lower().replace(" ", "-")`.
    """
    cleaned = re.sub(r'[<>:"/\\|?*]+', " ", text or "")
    cleaned = re.sub(r"[^A-Za-z0-9\-_. ]+", " ", cleaned)
    cleaned = re.sub(r"[\s_]+", "-", cleaned.strip())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-. ")
    return (cleaned or fallback)[:80]


def pisah_kode_matkul(nama: str) -> tuple[str, str]:
    """Pecah nama course jadi (nama_tampilan, kode).

    "Aljabar Linear Elementer 95 (ALEA4213)" ->
    ("Aljabar Linear Elementer 95", "ALEA4213")

    Kalau tidak ada kode, kode dikembalikan kosong dan pemanggil harus
    mendapatkannya dari isi lampiran -- itu yang dicatat di `_judul_dokumen`
    pada `tools/docx.py`.
    """
    m = RE_KODE_MATKUL.search(nama or "")
    if not m:
        return (nama or "").strip(), ""
    kode = m.group(1)
    sisa = (nama[: m.start()] + nama[m.end() :]).strip()
    sisa = re.sub(r"[-()\s]+$", "", sisa).strip()
    return (sisa or nama.strip()), kode


def ensure_dirs() -> None:
    """Buat folder output yang dibutuhkan. Dipanggil sekali saat start."""
    for path in (OUTPUT_DIR, CACHE_DIR):
        path.mkdir(parents=True, exist_ok=True)