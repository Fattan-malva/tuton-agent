"""Orkestrasi pipeline tuton.

Alur (mode `url`, bawaan):

    1. AUTH + DISCOVERY   -> daftar course, section, aktivitas kerja
    2. PREFETCH (paralel)-> kumpulkan & VERIFIKASI URL sumber, unduh lampiran
    3. KERJA (paralel)   -> agent `tuton` ambil soal dari URL, jawab, docx, state

Tahap 2 dipisah dari tahap 3 karena seluruhnya network-bound dan bisa jalan
bersamaan, sementara tahap 3 mahal (satu proses `opencode run` per item) dan
dibatasi `--jobs`.
"""

from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import signal
import sys
import threading
import time
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

# Character kontrol yang tidak sah di XML 1.0 (bikin docx gagal dibuat).
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Skrip non-Latin (CJK/Hangul/Kana/Cyrillic/Arab/Hebrew) tidak pernah muncul di
# jawaban akademik berbahasa Indonesia. Kehadirannya jadi sinyal teks korup —
# contoh nyata: jawaban Basis Data sempat memuat karakter CJK di tengah kata
# "Entitas" dan kata cacat seperti "bluesis".
_FOREIGN_SCRIPT_RE = re.compile(
    r"[⺀-鿿가-힯぀-ヿЀ-ӿ؀-ۿ"
    r"֐-׿]"
)
# Coretan penanda edit yang bocor ke teks (mis. "1:1_changed", "underpid").
_EDIT_ARTIFACT_RE = re.compile(
    r"(?:^|\s)\d+:\d+_(?:changed|removed|added)\b", re.IGNORECASE
)
# Placeholder resmi untuk "tidak ada sumber yang bisa diverifikasi". Ditulis
# agen penulis ketika berkas referensi kosong (lihat generator/prompt.py), dan
# sekarang dianggap hasil yang sah supaya item tetap jadi tanpa sitasi.
_NO_REFERENSI_RE = re.compile(
    r"tidak\s+ada\s+referensi\s+yang\s+terverifikasi", re.IGNORECASE
)

# Console Windows/cp1252 tidak selalu mendukung karakter UTF-8 (→, ✓, huruf
# beraksen). Paksa stdout/stderr ke UTF-8 supaya cukup `python main.py run`.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

from config import Config, OUTPUT_DIR, ensure_dir, now_stamp
from generator import models, opencode_runner, state
from generator.docx import _soal_bersih, save_doc
from generator.opencode_runner import run_opencode
from generator.prompt import (
    _ORANG_LAIN_RE,
    build_petak_prompt,
    build_prompt,
    build_referensi_prompt,
)
from moodle import bahan_ajar
from moodle.lampiran_mahasiswa import (
    looks_like_student_submission,
    pisahkan_lampiran,
)
from moodle.auth import MoodleSession
from moodle.discovery import SoalSource, SourceDiscovery
from moodle.downloader import AttachmentDownloader
from moodle.reader import MoodleReader
from moodle.reader_server import ensure_reader, handle_soal, soalu
from moodle.scraper import Activity, Course, CourseScraper

SEC_TUGAS_INDEX = {3: 1, 5: 2, 7: 3}

# Lampiran yang isinya tidak bisa diambil tanpa model vision.
_NEEDS_TRANSCRIBE_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp",
                    ".bmp", ".tiff", ".docx", ".pptx", ".xlsx", ".xls",
                    ".xlsm", ".ppt", ".odt"}

_PRINT_LOCK = threading.RLock()
_LOCAL = threading.local()
_REAL_STDOUT = sys.stdout


class _RoutedStdout(io.TextIOBase):
    """stdout yang mengarahkan keluaran tiap thread ke buffer sendiri.

    Ini wajib karena item dikerjakan paralel: kalau `print` menulis langsung ke
    stdout proses, baris dari dua item akan saling potong dan bercampur. Dengan
    routing per-thread, setiap item bisa diberi prefix sendiri lalu dicetak utuh
    setelah selesai, tanpa saling mengacak.

    Mode live (`_LOCAL.live`) tetap menyimpan ke buffer, tapi juga langsung
    menyalin ke terminal. Tanpa itu, satu `opencode run` yang-working 3 menit
    tampil sebagai layar yang benar-benar diam -- orang mengira pipeline hang.
    """

    def write(self, text):  # noqa: ANN001, ANN202
        if not text:
            return 0
        buffer = getattr(_LOCAL, "buffer", None)
        if buffer is not None:
            written = buffer.write(text)
            if getattr(_LOCAL, "live", False):
                _echo_live(text)
            return written
        with _PRINT_LOCK:
            return _REAL_STDOUT.write(text)

    def flush(self):  # noqa: D102
        buffer = getattr(_LOCAL, "buffer", None)
        if buffer is not None:
            if getattr(_LOCAL, "live", False):
                _flush_live()
            return None
        with _PRINT_LOCK:
            try:
                _REAL_STDOUT.flush()
            except (OSError, ValueError):
                pass

    def isatty(self):  # noqa: D102
        return False


def _echo_live(text: str) -> None:
    """Salin `print` dari worker ke terminal seketika, satu baris utuh.

    `print` menulis teks dan newline sebagai dua panggilan `write` terpisah,
    jadi sisipan disimpan sampai baris lengkap agar dua thread tidak
    menyisipkan di tengah baris yang sama.
    """
    pending = getattr(_LOCAL, "live_pending", "") + text
    lines = pending.split("\n")
    _LOCAL.live_pending = lines.pop()  # sisipan tanpa newline
    tag = getattr(_LOCAL, "prefix", "")
    with _PRINT_LOCK:
        for line in lines:
            _REAL_STDOUT.write(f"{tag}{line}\n")
        try:
            _REAL_STDOUT.flush()
        except (OSError, ValueError):
            pass


def _flush_live() -> None:
    pending = getattr(_LOCAL, "live_pending", "")
    if not pending:
        return
    _LOCAL.live_pending = ""
    with _PRINT_LOCK:
        _REAL_STDOUT.write(f"{getattr(_LOCAL, 'prefix', '')}{pending}\n")
        try:
            _REAL_STDOUT.flush()
        except (OSError, ValueError):
            pass


def _install_routed_stdout() -> None:
    if not isinstance(sys.stdout, _RoutedStdout):
        sys.stdout = _RoutedStdout()


_install_routed_stdout()


def log(message: str = "", *, prefix: str = "") -> None:
    """Cetak satu blok pesan lewat stdout yang sudah di-route per-thread.

    `prefix` ditambahkan otomatis bila tidak diberikan, memakai prefix yang
    sedang aktif di thread ini (diatur oleh _safe_process).
    """
    tag = prefix or getattr(_LOCAL, "prefix", "")
    with _PRINT_LOCK:
        for line in str(message).splitlines() or [""]:
            _REAL_STDOUT.write(f"{tag}{line}\n")
        try:
            _REAL_STDOUT.flush()
        except (OSError, ValueError):
            pass


class SoalNotFound(RuntimeError):
    """Soal tidak ditemukan di URL mana pun untuk item ini."""


@dataclass
class Prefetched:
    """Hasil tahap pra-ambil untuk satu item."""

    course: Course
    section_num: int
    item: Activity
    kind: str
    index: int
    source: SoalSource | None = None
    attachments: list[Path] = field(default_factory=list)
    transcripts: dict[str, str] = field(default_factory=dict)
    transcript_path: Path | None = None
    out_dir: Path | None = None
    error: str = ""
    pos: int = 0
    total: int = 0
    # Artefak dari tahap sebelumnya. `petak` dipakai bersama semua item dalam
    # satu sesi, sedangkan `referensi` milik item ini saja. Keduanya boleh
    # `None`: pipeline lalu memakai jalur cadangan, bukan berhenti.
    petak: Path | None = None
    referensi: Path | None = None
    # Isi peta sesi, dibaca sekali saat Tahap 1. Dicaching di sini supaya
    # pencarian bahan ajar tidak membaca berkas yang sama berulang-ulang untuk
    # tiap item dalam satu sesi.
    petak_text: str = ""
    # Metadata bahan ajar wajib sesi untuk item ini, kalau ada. `{}` berarti
    # sesi tidak menunjuk buku resmi, jadi Daftar Pustaka Searching adalah
    # temuan agen `pencari-pustaka`, bukan rujukan yang diminta tutor.
    referensi_bahan: dict = field(default_factory=dict)
    # Dokumen dasar untuk .docx. `None` berarti pakai template standar.
    # Form Soal mengisinya dengan berkas "Format Jawaban" milik pengguna bila
    # field itu diisi, sehingga hasil dokumennya mengikuti tata letak yang
    # benar-benar dipakai, bukan template bawaan.
    template: Path | None = None
    # Lampiran yang terbukti kiriman mahasiswa lain: [(berkas, alasan)].
    # Isi lampiran seperti ini TIDAK ikut transkrip dan tidak ikut jadi bahan
    # jawaban. Dari run sungguhan: dua PDF jawaban mahasiswa ikut ter-transkrip
    # dan jawabannya memakai angka yang sama persis dengan salah satunya --
    # jadi tanpa daftar ini, tugasnya tidak dikerjakan sama sekali.
    lampiran_mahasiswa: list[tuple[Path, str]] = field(default_factory=list)
    # Lampiran gambar yang berisi soal (mis. screenshot). Dipakai untuk
    # menyisipkan soal ke depan jawaban di .docx -- kalau soalnya cuma gambar,
    # mengetik ulang dari transkripsi bisa saja keliru.
    gambar_soal: list[Path] = field(default_factory=list)


def _display_index(item: Activity, kind: str, section_num: int) -> int:
    low = item.title.lower()
    m = re.search(r"(?:diskusi|tugas)[.\s-]?(\d+)", low)
    if m:
        return int(m.group(1))
    if kind == "tugas":
        return SEC_TUGAS_INDEX.get(section_num, section_num)
    return section_num


def _print_courses(scraper: CourseScraper):
    courses = scraper.get_courses()
    print("Daftar mata kuliah:")
    for c in courses:
        print(f"  [{c.id}] {c.name}")
    return courses


def cmd_status(args=None):
    st = state._load()  # noqa: SLF001
    items = st.get("items", {})
    if not items:
        print("Belum ada pekerjaan tercatat.")
        return
    print("Status pekerjaan:")
    for k, v in sorted(items.items()):
        flag = "DONE " if v.get("status") == "done" else "FAIL "
        print(f"  [{flag}] {v.get('matkul','?')} | {v.get('desc','?')}")
        for link in v.get("urls", [])[:3]:
            print(f"         sumber: {link}")


def cmd_scrape(args):
    Config.require()
    session = MoodleSession()
    session.check_login()
    scraper = CourseScraper(session)

    courses = scraper.get_courses()
    target = int(args.course) if args.course else None
    for c in courses:
        if target and c.id != target:
            continue
        print(f"\n=== {c.name} ===")
        sections = scraper.get_available_sections(c.id)
        if not sections:
            print("  (belum ada sesi terbuka)")
            continue
        for sec in sections:
            print(f"  Sesi {sec.number}: {sec.title}")
            diskusi, tugas, lain = scraper.split_assignable(sec.activities)
            for d in diskusi:
                print(f"    · DISKUSI: {d.title} [{d.mod_type}:{d.id}]")
            for t in tugas:
                print(f"    · TUGAS  : {t.title} [{t.mod_type}:{t.id}]")
            for x in lain:
                print(f"    · (lain) : {x.title} [{x.mod_type}:{x.id}]")


# ---------------------------------------------------------------------------
# Tahap 2: PREFETCH (kumpulkan + verifikasi URL, unduh lampiran)
# ---------------------------------------------------------------------------
def _prefetch_one(
    discovery: SourceDiscovery,
    downloader: AttachmentDownloader,
    course: Course,
    section_num: int,
    item: Activity,
    kind: str,
) -> Prefetched:
    index = _display_index(item, kind, section_num)
    out_dir = OUTPUT_DIR / course.folder_name / f"sesi{section_num}"
    out_dir.mkdir(parents=True, exist_ok=True)
    lamp_dir = out_dir / "lampiran"
    record = Prefetched(
        course=course,
        section_num=section_num,
        item=item,
        kind=kind,
        index=index,
        out_dir=out_dir,
    )
    try:
        source = discovery.discover(item, kind)
    except Exception as exc:  # noqa: BLE001 - satu item gagal tidak boleh menghentikan batch
        record.error = f"gagal discover: {type(exc).__name__}: {exc}"
        return record
    record.source = source

    # Unduh lampiran supaya (a) AI bisa membacanya lewat tool read, dan
    # (b) transkripsi tetap mungkin saat model tidak punya vision.
    if source.attachments:
        try:
            lamp_dir.mkdir(parents=True, exist_ok=True)
            record.attachments = downloader.download_all(source.attachments, lamp_dir)
        except Exception as exc:  # noqa: BLE001
            log(f"  ! gagal unduh lampiran: {exc}", prefix=f"[{kind}] {item.title} · ")
    return record


# ---------------------------------------------------------------------------
# Tahap 0: PETA SOAL  (satu kali per course + sesi, hasilnya di-cache)
#
# Kenapa tahap ini perlu: di UT, soal tidak selalu ada di halaman yang kebetulan
# ditemukan. Kadang menu Diskusi memuat soal tambahan, kadang soal tertentu
# bergantung pada lampiran atau halaman materi lain, dan kadang rubrik ada di
# halaman seksi sementara soalnya ada di halaman aktivitas (atau sebaliknya).
#
# Yang dulunya terjadi: agen `tuton` membuka beberapa halaman untuk tiap item,
# dan tiap item membayar harga penuh untuk halaman yang sama. Satu sesi berisi
# lima item berarti lima kali pembacaan halaman yang isinya identik.
#
# Sekarang: satu proses `pemetak-soal` membaca halaman-halaman itu SEKALI per
# sesi dan menulis peta ringkas. Lima item berikutnya membaca peta yang sama,
# yang isinya jauh lebih kecil karena sudah disaring: hanya soal, syarat
# format, rubrik, dan lampiran yang relevan.
# ---------------------------------------------------------------------------
_PETAK_AGENT = "pemetak-soal"

# Peta yang terlalu pendek hampir pasti gagal (agen hanya menulis pengumuman
# lalu berhenti), jadi dipakai sebagai ambang cache. 200 karakter setara satu
# blok soal plus syarat format.
_MIN_PETAK_CHARS = 200
# Referensi sah minimal satu baris APA yang lengkap, kira-kira 80 karakter.
# Entri tunggal yang pendek ("1. Tidak ada.") tetap diterima karena mungkin
# memang cuma satu sumber; yang ditolak di sini adalah file kosong.
_MIN_PUSTAKA_CHARS = 20
# Potongan peta yang dikirim ke agen cari referensi. Peta penuh sebenarnya
# sudah cukup kecil, tapi dipotong agar biaya prompt tidak bertambah seiring
# jumlah item dalam satu sesi.
_MAX_PETAK_DIGIT_CHARS = 6000

# Kata umum yang tidak membantu pencocokan judul aktivitas dengan judul
# bagian peta.
_STOP_WORDS = frozenset(
    {
        "dan", "untuk", "dengan", "yang", "dari", "pada", "dalam", "tugas",
        "diskusi", "tube", "pertemuan", "ulang", "tengah", "akhir", "pertama",
        "kedua", "modul", "sesi", "sesi", "kelas", "baru", "materi", "soal",
    }
)


def _petak_dir(course: Course) -> Path:
    """Folder peta, satu per mata kuliah.

    Dipisah dari `sesi<N>/` supaya peta tidak ikut terhitung sebagai hasil kerja
    item di sebelahnya, dan supaya satu file peta dipakai bersama semua item
    dalam sesinya.
    """
    return OUTPUT_DIR / course.folder_name / "_petak"


def _artifact_ok(path: Path, min_chars: int) -> bool:
    """Apakah artefak tahap sebelumnya sudah ada dan isinya masuk akal.

    `min_chars` mencegah artefak yang hanya berisi pengumuman tanpa isi
    dianggap berhasil. Inilah yang membuat cache tidak mengunci kegagalan
    selamanya: tahap yang gagal akan dicoba lagi pada run berikutnya.
    """
    try:
        if not path.is_file():
            return False
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if len(text.strip()) < min_chars:
        return False
    # Jejak kegagalan opencode tidak boleh dihitung sebagai peta atau daftar
    # pustaka yang sah. diperiksa di awal teks saja, karena jawaban boleh saja
    # membahas kata "error" di bagian pemikirannya.
    head = text[:400].lower()
    if "traceback (most recent call last)" in head:
        return False
    return True


def _run_helper(
    prompt: str,
    *,
    path: Path,
    agent: str,
    model: str,
    label: str,
    min_chars: int,
    jejak: list[str] | None = None,
) -> bool:
    """Jalankan satu agen pembantu dan tunggu berkas yang dijanjikannya.

    Berbeda dengan agen penulis, agen pembantu tidak diperiksa dengan
    `answer_quality_issues`: isinya bukan jawaban melainkan artefak. Yang
    diperiksa hanya benar-benar tertulis dan cukup berisi. Mengembalikan
    `False` membuat pemanggil memakai jalur cadangan.

    `jejak` diisi dengan keluaran percobaan terakhir. `_petak_stage` memakainya
    untuk mengenali model yang tidak punya webfetch -- penyebab kegagalan yang
    tidak bisa ditebak dari kode exit, dan yang kalau tidak dikenali akan
    terulang di setiap run.
    """
    path.unlink(missing_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Jejak keluaran terakhir, supaya pemanggil bisa membaca alasan
    # kegagalan yang sebenarnya (mis. tool webfetch tidak ada).
    jejak: list[str] = []

    attempts = max(1, Config.TUTON_HELPER_RETRIES)
    for attempt in range(1, attempts + 1):
        if _stop_diminta():
            raise DihentikanUser("stop diminta sebelum agen pembantu dijalankan")
        try:
            result = run_opencode(
                prompt,
                agent=agent,
                model=model or None,
                timeout=Config.TUTON_TIMEOUT_HELPER,
            )
        except opencode_runner.RunStopped as exc:
            # Stop harus naik ke atas, bukan ditelan jadi "gagal" lalu dicoba
            # lagi. Kalau diteruskan sebagai galat biasa, pipeline masuk retry
            # dan memanggil agen-agen baru justru saat pengguna menekan stop.
            raise DihentikanUser(str(exc)) from exc
        except TimeoutError:
            log(f"  ! {label}: timeout (percobaan {attempt}/{attempts})")
            continue
        except Exception as exc:  # noqa: BLE001
            log(f"  ! {label}: {type(exc).__name__}: {exc}")
            continue

        if _artifact_ok(path, min_chars):
            return True
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        if jejak is not None:
            jejak.append(output)
        if result.returncode != 0 and output:
            tail = " | ".join(output.splitlines()[-3:])[:280]
            log(f"  ! {label}: opencode exit {result.returncode} ({tail})")
        else:
            log(f"  ! {label}: {path.name} tidak tertulis.")
    return False


def helper_model() -> str:
    """Model untuk agen pembantu. String kosong berarti default opencode.

    Sengaja tidak di-hardcode di sini. Pemanggil cukup menyebut perannya, dan
    `generator.models` yang memilih model termurah yang benar-benar tersedia.
    """
    from generator import models  # noqa: PLC0415

    return models.resolve(models.ROLE_HELPER)


def writer_model() -> str:
    """Model untuk agen penulis `tuton`."""
    from generator import models  # noqa: PLC0415

    return models.resolve(models.ROLE_WRITER)


# Bukti model pembantu tidak bisa membuka URL. Ditandai dari keluarannya sendiri,
# bukan dari tebakan: model yang memang tidak punya tool itu menyebut tool itu
# tidak ada.
#
# Dari run sungguhan: `ollama-cloud/gemma4:31b` berjalan di Code Mode yang
# hanya menyingkalkan `browser` dan `opencode`, jadi `tools.webfetch()` selalu
# "Unknown tool". Akibatnya tahap peta gagal setiap kali -- 35 detik terpakai
# untuk NOTHING, lalu agen penulis melakukan dua pekerjaan sekaligus (baca
# halaman + jawab). Menandainya membuat run berikutnya langsung melewati peta.
_BUKAN_WEBFETCH_RE = re.compile(
    r"unknown tool [\"']?webfetch"
    r"|webfetch[^\n]{0,40}(?:is |tidak |not )?(?:available|defined|listed|found)"
    r"|(?:tidak tersedia|tidak ada|not available|no such tool)[^\n]{0,30}webfetch"
    r"|only\s+`?(?:browser|opencode)`?\s+(?:and|are|is)\s+present",
    re.IGNORECASE,
)

# Berkas penanda di cache. Satu berkas per model, jadi ganti model di Settings
# langsung mengembalikan perilaku peta.
_TANPA_WEBFETCH_DIR = OUTPUT_DIR / ".cache" / "helper_tanpa_webfetch"


def _tandai_tanpa_webfetch(model: str) -> None:
    """Catat bahwa model pembantu ini tidak bisa membuka URL."""
    if not model:
        return
    try:
        ensure_dir(_TANPA_WEBFETCH_DIR)
        (_TANPA_WEBFETCH_DIR / f"{model.replace('/', '_')}.flag").write_text(
            now_stamp(), encoding="utf-8"
        )
    except OSError:
        pass  # cache tidak bisa ditulis: cukup kehilangan penghematan sekali


def _sudah_tanpa_webfetch(model: str) -> bool:
    """True kalau model ini sudah pernah terbukti tidak bisa membuka URL."""
    if not model:
        return False
    return (_TANPA_WEBFETCH_DIR / f"{model.replace('/', '_')}.flag").is_file()


def _petak_stage(
    course: Course,
    sections: list,
    *,
    force: bool,
) -> dict[int, Path]:
    """Petakan soal sekali per sesi memakai model pembantu.

    Mengembalikan peta `{nomor_sesi: path}` hanya untuk sesi yang petanya benar
    benar ada di disk, supaya pemanggil bisa membedakan "tidak ada peta" dari
    "peta ada tapi kosong".

    Kegagalan tidak menghentikan pipeline: agen penulis punya jalur cadangan
    untuk membaca halaman sumber sendiri. Yang hilang hanya penghematan biaya.
    """
    done: dict[int, Path] = {}
    pending: list[tuple[object, Path]] = []
    for sec in sections:
        path = _petak_dir(course) / f"sesi{sec.number}.md"
        if not force and _artifact_ok(path, _MIN_PETAK_CHARS):
            done[sec.number] = path
            continue
        pending.append((sec, path))

    if not pending:
        if done:
            log(
                f"  · peta soal: {len(done)} sesi diambil dari cache.",
                prefix="  ",
            )
        return done

    model = helper_model()
    if _sudah_tanpa_webfetch(model):
        log(
            f"  · peta soal dilewati: model pembantu `{model}` tidak punya tool "
            "webfetch, jadi tidak bisa membuka halaman. Set "
            "OPENCODE_MODEL_HELPER ke model lain untuk menghidupkan tahap ini.",
            prefix="  ",
        )
        return done

    log(
        f"  · memetakan soal {len(pending)} sesi dengan model kecil "
        "(mencari sekaligus memahami soal, rubrik, dan lampiran)...",
        prefix="  ",
    )

    jejak: list[str] = []

    def petakan_sesi(sec, path: Path) -> tuple[object, Path, bool]:
        """Satu sesi = satu pemanggilan agen. Berjalan di worker sendiri."""
        started = time.monotonic()
        try:
            prompt = build_petak_prompt(
                course_name=course.name,
                section_num=sec.number,
                section_title=sec.title,
                # WAJIB lewat `soalu()`. Agen `pemetak-soal` tidak punya cookie
                # MoodleSession, jadi URL Moodle mentah membawanya ke halaman
                # login. (Itu yang membuat agent lama berputar-putar: mencoba
                # browser, menggali source code, lalu menggali cache halaman --
                # semua karena URL yang dikirimi tidak bisa dia buka sendiri.)
                # `fresh=True` = abaikan cache, baca Moodle versi terbaru.
                section_url=soalu(
                    f"{Config.base_url()}/course/view.php"
                    f"?id={course.id}&section={sec.number}",
                    fresh=True,
                ),
                out_path=path,
            )
            ok = _run_helper(
                prompt,
                path=path,
                agent=_PETAK_AGENT,
                model=model,
                label=f"{course.name} sesi {sec.number}",
                min_chars=_MIN_PETAK_CHARS,
                jejak=jejak,
            )
        except DihentikanUser:
            raise
        except Exception as exc:  # noqa: BLE001
            log(f"  ! peta sesi {sec.number} gagal: {type(exc).__name__}: {exc}")
            return sec, path, False
        return sec, path, ok

    # Sesi-sesi saling bebas: tiap satu menulis `sesi<N>.md` yang berbeda dan
    # tidak membaca keluaran sesi lain. Karena itu pemetaan berjalan paralel,
    # bukan satu per satu -- dengan model sekecil apa pun, satu `opencode run`
    # tetap memerlukan detik, jadi tiga sesi berurutan berarti tiga kali
    # menunggu.
    workers = max(1, min(Config.TUTON_MAP_WORKERS, len(pending)))
    started_all = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="petak") as pool:
        futures = [
            pool.submit(petakan_sesi, sec, path) for sec, path in pending
        ]
        for future in as_completed(futures):
            try:
                sec, path, ok = future.result()
            except DihentikanUser:
                # Stop: bukan kegagalan peta. Menghitungnya sebagai gagal akan
                # membuat pipeline mencoba jalur cadangan (baca URL tanpa peta),
                # yaitu memulai pekerjaan baru justru saat pengguna berhenti.
                raise
            except Exception as exc:  # noqa: BLE001
                log(f"  ! peta gagal: {type(exc).__name__}: {exc}")
                continue
            if ok:
                done[sec.number] = path
                log(
                    f"  ✓ peta sesi {sec.number} "
                    f"({path.stat().st_size} byte)",
                    prefix="  ",
                )
            else:
                log(
                    f"  · peta sesi {sec.number} tidak terbentuk. Agen penulis akan "
                    "membaca halaman sumber sendiri: lebih mahal, tapi tetap jalan.",
                    prefix="  ",
                )
    log(
        f"  · pemetaan selesai dalam {time.monotonic() - started_all:.1f}s "
        f"({len(done)}/{len(pending) + len(done)} sesi terpetakan)",
        prefix="  ",
    )

    # Kalau modelnya ternyata tidak punya webfetch, tandai sekarang. Tanpa ini
    # run berikutnya mengulang percobaan yang pasti gagal -- dan percobaan itu
    # bukan murah: dari run sungguhan, 35 detik untuk peta yang tidak terbentuk.
    if not done and jejak and _BUKAN_WEBFETCH_RE.search("\n".join(jejak)):
        _tandai_tanpa_webfetch(model)
        log(
            f"  ! model pembantu `{model}` tidak punya tool webfetch. Peta soal "
            "dilewati pada run berikutnya; agen penulis membaca halaman sumber "
            "sendiri. Ganti OPENCODE_MODEL_HELPER supaya peta soal dihitung lagi.",
            prefix="  ",
        )
    return done


# ---------------------------------------------------------------------------
# Tahap 1: DAFTAR PUSTAKA  (satu kali per item, di-cache)
#
# Riset adalah langkah termahal di pipeline ini: satu putaran websearch ditambah
# satu webfetch untuk setiap referensi. Dulu semuanya dilakukan agen `tuton`
# untuk setiap item, padahal daftar referensi yang relevan bisa diambil dari
# sumber yang sama.
#
# Dipisah ke agen `pencari-pustaka` dengan batas keras supaya biayanya
# terkontrol: maksimal 1 websearch dan maksimal 1 webfetch per referensi.
# ---------------------------------------------------------------------------
_PUSTAKA_AGENT = "pencari-pustaka"


def _pustaka_path(record: Prefetched) -> Path:
    out_dir = record.out_dir or (
        OUTPUT_DIR / record.course.folder_name / f"sesi{record.section_num}"
    )
    return out_dir / f"referensi_{record.kind}_{record.index}.md"


def _pustaka_digest(petak: Path | None, record: Prefetched) -> str:
    """Potongan peta yang relevan untuk satu item.

    Peta per sesi bisa memuat beberapa soal. Mengirim peta utuh ke tiap item
    membuat biaya prompt tumbuh linear, padahal tiap item hanya butuh bagiannya.
    Dipotong per heading; kalau tidak ada yang cocok, peta utuh tetap dikirim
    karena lebih baik daripada memetakan kosong.
    """
    if not petak or not petak.is_file():
        return ""
    try:
        text = petak.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if not text.strip():
        return ""

    title = record.item.title.lower()
    words = [
        w for w in re.findall(r"[a-z0-9]{3,}", title) if w not in _STOP_WORDS
    ]
    parts = re.split(r"(?m)^(?=##\s)", text)
    header = parts[0] if parts else ""
    chunks: list[str] = []
    for chunk in parts[1:]:
        if not chunk.strip():
            continue
        haystack = chunk[:600].lower()
        if any(w in haystack for w in words):
            chunks.append(chunk)
    if not chunks:
        return text[:_MAX_PETAK_DIGIT_CHARS]
    return (header + "".join(chunks))[:_MAX_PETAK_DIGIT_CHARS]


def _petak_text(path: Path | None) -> str:
    """Isi peta soal, atau string kosong bila petanya tidak ada."""
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _teks_materi_sesi(record: Prefetched) -> str:
    """Semua teks halaman yang relevan untuk satu item.

    Bahan ajar wajib biasanya disebut di halaman SEKSI ("silakan pelajari
    BMP ... Modul 4"), bukan di halaman aktivitas. Jadi teks yang dikumpulkan
    di sini bukan hanya `soal_text` item, tapi juga peta sesi: peta itu dibaca
    agen dari halaman seksi, dan apa pun yang ia tulis balik ke sana ikut
    terbaca di sini.
    """
    parts: list[str] = []
    if record.source is not None and record.source.soal_text:
        parts.append(record.source.soal_text)
    if record.petak_text:
        parts.append(record.petak_text)
    if record.transcripts:
        parts.extend(record.transcripts.values())
    return "\n".join(parts)


def _referensi_bahan_ajar(records: list[Prefetched]) -> dict[int, dict]:
    """Cari sitasi bahan ajar wajib untuk tiap item, tanpa panggil model.

    Halaman sesi UT hampir selalu menunjuk satu buku resmi dan menautkan
    katalognya. Satu GET ke tautan itu sudah menghasilkan sitasi lengkap yang
    bisa diperiksa dosen -- jadi untuk kasus umum (buku yang memang diminta
    tutor) Tahap 1 tidak perlu dijalankan sama sekali.

    Mengembalikan `{id(record): {"sitasi", "url", "bahan", "siap"}}`.

    `siap` True berarti sitasinya lengkap dan boleh langsung ditulis ke berkas
    referensi. `siap` False dengan `bahan` yang tidak kosong berarti peta knows
    WHICH book the session mandates, but the catalog could not be fetched --
    entri itu tidak boleh dikarang sendiri, tapi konteksnya wajib diteruskan ke
    agen `pencari-pustaka`. Tanpa penerusan itu, agen tidak tahu buku mana yang
    dituju dan berakhir mencari buku topik-topiknya yang mirip, yang justru
    kelihatan sebagai daftar di luar sesi.
    """
    hasil: dict[int, dict] = {}
    # Satu sesi punya satu bahan ajar; jangan ambil halaman yang sama berulang.
    per_url: dict[str, dict] = {}

    for record in records:
        text = _teks_materi_sesi(record)
        if not text:
            continue
        try:
            ditemukan = bahan_ajar.referensi_dari_materi(text)
        except Exception:  # noqa: BLE001 - jalur cepat tidak boleh mematikan pipeline
            continue
        bahan = ditemukan.get("bahan", {}) or {}
        sitasi = ditemukan.get("sitasi", "")
        url = ditemukan.get("url", "")
        if sitasi:
            if url not in per_url:
                per_url[url] = {
                    "sitasi": sitasi,
                    "url": url,
                    "bahan": bahan,
                    "siap": True,
                }
            hasil[id(record)] = per_url[url]
        elif bahan.get("kalimat") or bahan.get("kode"):
            hasil[id(record)] = {
                "sitasi": "",
                "url": url,
                "bahan": bahan,
                "siap": False,
            }
    return hasil


def _tulis_referensi_bahan_ajar(record: Prefetched, info: dict) -> bool:
    """Tulis entri bahan ajar ke berkas referensi item. True bila berhasil.

    Formatnya persis sama dengan yang diminta agen `pencari-pustaka`: satu baris
    per entri, tanpa nomor, tanpa bullet. URL katalog ditambahkan di akhir
    entri karena dua alasan sekaligus: itu bentuk APA 7 yang sah untuk sumber
    daring, dan itulah yang membuat daftar ini bisa diperiksa dosen. `answer_
    quality_issues` juga memakainya untuk mengecualikan bahan ajar wajib dari
    aturan batas 10 tahun -- jadi URL ini bukan hiasan.
    """
    path = _pustaka_path(record)
    entri = f"{info['sitasi'].rstrip()} {info['url']}".strip()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entri + "\n", encoding="utf-8")
    except OSError as exc:
        log(f"  ! gagal menulis referensi bahan ajar: {exc}")
        return False
    return True


def _tahun_min_referensi() -> int:
    """Tahun tertua yang boleh dipakai untuk referensi dari luar sesi."""
    return date.today().year - max(1, Config.TUTON_PUSTAKA_TAHUN_MAX)


def _pustaka_stage(
    records: list[Prefetched],
    peta_by_section: dict[int, Path],
    *,
    force: bool,
) -> dict[int, Path]:
    """Daftar Pustaka per item: bahan ajar dulu, model sebagai cadangan.

    Urutannya penting. Halaman sesi hampir selalu menunjuk buku yang harus
    dipakai, jadi langkah pertama membaca metadata katalog UT secara langsung
    (`moodle.bahan_ajar`) dan menulis Daftar Pustaka tanpa memanggil model sama
    sekali. Hanya item yang bahannya tidak ditemukan yang diteruskan ke agen
    `pencari-pustaka` untuk mencari referensi pelengkap.

    Jalur model berjalan paralel antar item: tiap item menulis berkas berbeda dan
    hanya membaca peta sesi yang sudah selesai ditulis pada tahap sebelumnya.
    """
    todo = [r for r in records if r.source is not None and r.source.ok_links]
    if not todo:
        return {}

    out: dict[int, Path] = {}
    pending: list[Prefetched] = []
    for record in todo:
        path = _pustaka_path(record)
        if not force and _artifact_ok(path, _MIN_PUSTAKA_CHARS):
            out[id(record)] = path
            continue
        pending.append(record)

    if not pending:
        log(f"  · daftar pustaka: {len(out)} item dari cache.", prefix="  ")
        return out

    # Tahap 1a: bahan ajar wajib sesi, deterministik dan tanpa model.
    for record in pending:
        record.petak_text = _petak_text(peta_by_section.get(record.section_num))
    info = _referensi_bahan_ajar(pending)
    if info:
        for record in pending:
            entry = info.get(id(record))
            if not entry or not entry.get("siap"):
                # Sitasi tidak lengkap. Jangan dikarang di sini; konteksnya
                # tetap diteruskan ke agen di tahap 2.
                continue
            if _tulis_referensi_bahan_ajar(record, entry):
                out[id(record)] = _pustaka_path(record)
                record.referensi_bahan = entry
                log(
                    f"  ✓ bahan ajar sesi: {(entry['bahan'].get('judul') or '')[:60]!r}",
                    prefix=f"  [{record.kind} {record.index}] ",
                )

    pending = [r for r in pending if id(r) not in out]
    if not pending:
        log(
            f"  · daftar pustaka: {len(out)} item selesai dari bahan ajar sesi, "
            "tanpa satu pun panggilan model.",
            prefix="  ",
        )
        return out

    model = helper_model()
    log(
        f"  · mencari referensi {len(pending)} item di luar bahan ajar sesi "
        f"(maksimal {Config.TUTON_MAX_PUSTAKA} per item, tahun "
        f"{_tahun_min_referensi()}-{date.today().year})...",
        prefix="  ",
    )

    def cari_referensi(record: Prefetched) -> tuple[Prefetched, Path | None]:
        path = _pustaka_path(record)
        digest = _pustaka_digest(peta_by_section.get(record.section_num), record)
        try:
            prompt = build_referensi_prompt(
                work_kind=record.kind,
                index=record.index,
                course_name=record.course.name,
                section_num=record.section_num,
                activity_title=record.item.title,
                petak_digest=digest,
                transcript_path=record.transcript_path,
                attachment_names=[p.name for p in record.attachments],
                out_path=path,
                max_refs=Config.TUTON_MAX_PUSTAKA,
                tahun_min=_tahun_min_referensi(),
                bahan_ajar={
                    k: v
                    for k, v in (info.get(id(record), {}).get("bahan") or {}).items()
                    if v
                },
            )
            ok = _run_helper(
                prompt,
                path=path,
                agent=_PUSTAKA_AGENT,
                model=model,
                label=f"{record.kind} {record.index}",
                min_chars=_MIN_PUSTAKA_CHARS,
            )
        except DihentikanUser:
            raise
        except Exception as exc:  # noqa: BLE001
            log(f"  ! referensi {record.kind} {record.index} gagal: {exc}")
            return record, None
        return record, path if ok else None

    workers = max(1, min(Config.TUTON_HELPER_WORKERS, len(pending)))
    started_all = time.monotonic()
    with ThreadPoolExecutor(
        max_workers=workers, thread_name_prefix="pustaka"
    ) as pool:
        for record, path in pool.map(cari_referensi, pending):
            if path is not None:
                out[id(record)] = path
    log(
        f"  · pencarian referensi selesai dalam {time.monotonic() - started_all:.1f}s",
        prefix="  ",
    )
    return out


def _needs_transcription(record: Prefetched) -> bool:
    """Apakah lampiran item ini perlu ditranskripsi?

    Ya, begitu ada lampiran: di UT PDF/gambar sering berisi soal
    yang tidak pernah ditulis di halaman. Melewatkannya berarti AI menjawab dari
    instruksi saja tanpa soalnya -- itu penyebab paling umum jawaban
    meleset dari nilai sebenarnya.
    """
    if not record.attachments:
        return False
    # Semua jenis lampiran diproses. Bedanya hanya di biaya: .xlsx/.docx/.txt
    # diekstrak Python (instan), sedangkan gambar/PDF scan memakai model vision
    # (mahal). Jawabannya tetap "ya", karena di UT PDF/gambar lampiran sering
    # kali justru zawaras utama soal sementara halamannya hanya instruksi umum.
    return True


def _write_transcript_file(record: Prefetched, lamp_dir: Path) -> Path | None:
    """Gabungkan semua transkripsi ke satu file markdown yang mudah dibaca AI."""
    # Folder dibuat di sini, bukan hanya di pemanggil transkripsi. Fungsi ini
    # dipanggil juga oleh Form Soal dan oleh jalur tanpa transkripsi vision --
    # dan dua pemanggil itu tidak pernah menyentuh folder lampiran, sehingga
    # penulisan berakhir dengan `FileNotFoundError` yang tidak menyuruh siapa pun
    # membuat folder.
    ensure_dir(lamp_dir)

    # Klasifikasi diulang di sini kalau pemanggil belum melakukannya. Agen
    # penulis punya `read`: kalau transkrip masih memuat isi jawaban mahasiswa,
    # isinya akan terbaca hanya dengan satu panggilan. Jadi pengecualian tidak
    # boleh bergantung pada pengingat di pemanggil -- harus aman kalau
    # diabaikan.
    # `transitive` = daftar (Path, alasan). Nama berkas diturunkan dari Path
    # supaya satu bentuk saja yang dipakai di seluruh fungsi ini.
    transitive: list[tuple[Path, str]] = [
        (Path(n), a) for n, a in record.lampiran_mahasiswa
    ]
    for name, text in (record.transcripts or {}).items():
        if any(name == b.name for b, _ in transitive):
            continue
        alasan = looks_like_student_submission(Path(name), text)
        if alasan:
            transitive.append((Path(name), alasan))
            record.lampiran_mahasiswa = [(b.name, a) for b, a in transitive]

    # Transkrip lampiran mahasiswa lain dihapus dari disk, bukan cuma tidak
    # dipakai. Ada satu sub-bagian di bawah yang menyebut berkasnya, dan agent
    # yang punya `read` bisa saja tetap membukanya -- dan isinya jawaban jadi.
    # Hanya transkrip turunannya yang dihapus, BUKAN berkas lampiran aslinya:
    # lampiran ada di folder karena di situ tutor bisa memverifikasi
    # sendiri; menghapusnya berarti isi aslinya hilang tanpa jejak.
    for berkas, _alasan in transitive:
        sisa = lamp_dir / f"transkrip_{berkas.stem}.md"
        if not sisa.is_file():
            continue
        try:
            sisa.unlink()
        except OSError:
            pass

    bagian_soal = {
        nama: teks
        for nama, teks in (record.transcripts or {}).items()
        if not any(nama == b.name for b, _ in transitive)
    }
    if not bagian_soal:
        return None
    parts: list[str] = []
    for name, text in bagian_soal.items():
        parts.append(f"## {name}\n\n{text}")
    if transitive:
        # Disebut agar agent tahu lampirannya ADA dan sengaja dilewati, bukan
        # lupa. Tanpa ini, agent akan mencari-cari dan mengarang sendiri.
        daftar = ", ".join(berkas.name for berkas, _ in transitive)
        parts.append(
            "## Lampiran yang TIDAK dipakai (jawabannya)\n\n"
            f"Ada {len(transitive)} lampiran: {daftar}.\n"
            "Lampiran ini kiriman mahasiswa lain, bukan soal. Isinya jawaban "
            "yang sudah jadi. JANGAN dibaca, jangan diringkas, jangan dijadikan "
            "kerangka jawaban. Kerjakan soal sendiri dari materi di atas."
        )
    # Nama WAJIB per-item. Folder lampiran dipakai bersama oleh semua item dalam
    # satu sesi, jadi nama tetap "transkrip.md" berarti dua item yang jalan
    # paralel menulis berkas yang sama dan salah satunya hilang tanpa jejak.
    path = lamp_dir / f"transkrip_{record.kind}{record.index}.md"
    header = (
        "# Transkripsi Lampiran\n\n"
        "Isi di bawah ini DIEKSTRAK OTOMATIS dari lampiran soal "
        "(gambar/PDF/dokumen) oleh sistem, bukan oleh kamu. inilah cara "
        "konten visual lampiran diterjemahkan menjadi teks.\n"
    )
    path.write_text(header + "\n\n---\n\n".join(parts) + "\n", encoding="utf-8")
    return path


def _transcribe_stage(records: list[Prefetched]) -> None:
    """Transkripsi lampiran untuk semua item, paralel dengan worker terbatas.

    Worker dibatasi terpisah dari `--jobs` karena tiap transkripsi vision adalah
    satu panggilan model: menjalankannya sebanyak `--jobs` sekaligus berisiko kena
    rate limit tanpa perlu.
    """
    todo = [r for r in records if r.source is not None and _needs_transcription(r)]
    if not todo:
        return
    from moodle.transcribe import transcribe_many
    from moodle.ocr import IMAGE_EXT as _IMAGE_EXT

    workers = max(1, min(Config.TUTON_TRANSCRIBE_WORKERS, len(todo)))
    log(f"  · transkripsi lampiran {len(todo)} item ({workers} worker)...")

    def work(record: Prefetched) -> None:
        lamp_dir = (record.out_dir or Path(".")) / "lampiran"
        # Pisahkan dulu: lampiran mahasiswa lain tidak boleh ikut transkrip,
        # karena isinya adalah jawaban -- dan agent yang membacanya akan
        # mengikuti. Pemisahan dilakukan SEBELUM transkripsi supaya tidak ada
        # satu pun karakter jawaban orang lain yang masuk ke prompt.
        lampiran_soal, record.lampiran_mahasiswa = pisahkan_lampiran(
            [Path(p) for p in record.attachments]
        )
        if record.lampiran_mahasiswa:
            for nama, alasan in record.lampiran_mahasiswa:
                log(f"    · tidak dipakai: {nama} ({alasan})")
        record.gambar_soal = [
            p for p in lampiran_soal if p.suffix.lower() in _IMAGE_EXT
        ]
        record.transcripts = transcribe_many(lampiran_soal, lamp_dir)
        record.transcript_path = _write_transcript_file(record, lamp_dir)

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="transcribe") as pool:
        futures = {pool.submit(work, record): record for record in todo}
        for future in as_completed(futures):
            record = futures[future]
            try:
                future.result()
            except Exception as exc:  # noqa: BLE001
                log(f"  ! transkripsi {record.item.title} gagal: {exc}")
                continue
            if record.transcripts:
                log(
                    f"  ✓ {record.item.title}: "
                    f"{len(record.transcripts)} lampiran soal terbaca "
                    f"({sum(len(v) for v in record.transcripts.values())} karakter)"
                    + (
                        f", {len(record.lampiran_mahasiswa)} lampiran mahasiswa lain "
                        "dilewati"
                        if record.lampiran_mahasiswa
                        else ""
                    )
                )
            else:
                log(f"  · {record.item.title}: tidak ada lampiran yang bisa dibaca")
    log(f"  · transkripsi selesai dalam {time.monotonic() - started:.1f}s")


def _prefetch_all(
    discovery: SourceDiscovery,
    downloader: AttachmentDownloader,
    jobs: list[tuple[Course, int, Activity, str]],
) -> list[Prefetched]:
    """Verifikasi URL + unduh lampiran untuk semua item, paralel."""
    total = len(jobs)
    results: list[Prefetched] = []
    workers = max(1, min(Config.TUTON_PREFETCH_WORKERS, total))
    log(f"  · pra-ambil {total} item ({workers} worker paralel)...")
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="prefetch") as pool:
        futures = {
            pool.submit(
                _prefetch_one, discovery, downloader, course, section, item, kind
            ): (course, section, item, kind)
            for course, section, item, kind in jobs
        }
        done = 0
        for future in as_completed(futures):
            course, section, item, kind = futures[future]
            done += 1
            prefix = f"[{done}/{total}] [{kind}] {item.title} · "
            try:
                record = future.result()
            except Exception as exc:  # noqa: BLE001
                # out_dir tetap diisi: _process_record memakainya tanpa cek,
                # jadi record tanpa out_dir akan menggagalkan AssertionError
                # dan menutup item dengan pesan yang menyesatkan.
                record = Prefetched(
                    course=course,
                    section_num=section,
                    item=item,
                    kind=kind,
                    index=_display_index(item, kind, section),
                    out_dir=OUTPUT_DIR / course.folder_name / f"sesi{section}",
                    error=f"{type(exc).__name__}: {exc}",
                )
            record.pos = done
            results.append(record)
            if record.error:
                log(f"! {record.error}", prefix=prefix)
                continue
            assert record.source is not None
            source = record.source
            if source.ok_links:
                log(
                    f"✓ {source.summary()} | utama: {source.primary_url}"
                    + (
                        f" | lampiran: {len(record.attachments)}"
                        if record.attachments
                        else ""
                    ),
                    prefix=prefix,
                )
            else:
                log(f"✗ {source.note}", prefix=prefix)
    log(f"  · pra-ambil selesai dalam {time.monotonic() - started:.1f}s")
    # `_prefetch_all` selesai sesuai urutan network, yang acak. Item yang lambat
    # bisa saja jadi "1/3" padahal dikirim pertama. Kembalikan sesuai urutan
    # submit supaya posisi di log dan urutan diproses konsisten.
    order = {(c.id, s, i.mod_type, i.id): n for n, (c, s, i, _k) in enumerate(jobs)}
    results.sort(
        key=lambda r: order.get(
            (r.course.id, r.section_num, r.item.mod_type, r.item.id), 10_000
        )
    )
    return results


# ---------------------------------------------------------------------------
# Tahap 3: KERJA
# ---------------------------------------------------------------------------
def _as_list(value) -> list[str]:
    """Normalisasi argumen yang bisa berupa string tunggal atau list."""
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if str(v).strip()]
    return [value] if str(value).strip() else []


def _custom_index(title: str, kind: str) -> int:
    """Nomor display untuk soal form: ambil angka dari judul (mis. 'Diskusi 2'),
    fallback ke 1 bila tidak ada nomor."""
    m = re.search(r"(?:diskusi|tugas)[.\s-]?(\d+)", title.lower())
    return int(m.group(1)) if m else 1


# Frasa yang membuat jawaban terdengar seperti hasil model, bukan tulisan
# mahasiswa. Daftar ini bukan soal selera; tiap entri pernah muncul di
# keluaran nyata dan langsung dibaca dosen. "bayangkan" masuk daftar karena
# kata itu dipakai ulang sebagai jeda di hampir semua jawaban -- satu kata
# yang terlihat di tiap paragraf langsung menutup credibilitas tulisan.
_AI_TELL_RE = re.compile(
    r"\bbayangkan\b"
    r"|\bsaya\s+akan\s+(?:membahas|menguraikan|membahaskan)\b"
    r"|\bsebagai\s+(?:seorang\s+)?(?:AI|asisten|pembantu)\b"
    r"|\bdalam\s+konteks\s+(?:ini|today|hari\s+ini)\s*,?\s*(?:kita|saya)\b"
    r"|\bdi\s+dalam\s+era\s+digital\b"
    r"|\bsalah\s+satu\s+hal\s+yang\s+(?:penting|menarik)\b"
    r"|\btidak\s+kurang(?:an)?\s+(?:untuk\s+)?(?:membahas|menguraikan)\b"
    r"|\bmenurut\s+penulis\b"
    r"|\bkesimpulan\s+nya\b"
    r"|\b(?:penting\s+untuk\s+)?dicatat\s+bahwa\b",
    re.IGNORECASE,
)

# Sisa kerangka kerja skill `humanizer` yang bocor ke jawaban. Skill itu punya
# dua mode; mode "pasted" mengembalikan draft mentah beserta daftar pola yang
# masih tersisa. Kalau isinya tidak dibuang utuh, "Draft:", "**Before:**", dan
# daftar "Remaining patterns" ikut masuk ke dokumen dan langsung kelihatan.
_HUMANIZER_SCAFFOLD_RE = re.compile(
    r"^\s*(?:draft|before|after)\s*:"
    r"|\*\*\s*(?:before|after)\s*\*\*"
    r"|remaining\s+patterns?"
    r"|^\s*-\s*\|\s*\^?(?:AI|pattern)\s+phrase",
    re.IGNORECASE | re.MULTILINE,
)

# Kata kerja orang pertama yang harus muncul. Tanpa ini jawaban bisa lolos
# seluruh gate lain dan tetap impersonal: evidence-nya ada di keluaran lama,
# `jawaban_diskusi_4.md` punya 1365 kata dan nol kemunculan "saya".
_SAYA_RE = re.compile(r"\bsaya\b", re.IGNORECASE)

# Entri referensi boleh menyebut ISBN, jumlah halaman, atau catatan penerbit
# hanya kalau ia berasal dari katalog resmi UT. Untuk sumber lain, metadata
# seperti itu tidak bisa dicek dan sering dikarang model.
_METADATA_KATALOG_RE = re.compile(r"\bISBN\b|\b\d{1,4}\s*hlm\.?\b", re.IGNORECASE)
_URL_UT_RE = re.compile(r"https?://\S*\.?ut\.ac\.id", re.IGNORECASE)


def _tahun_dalam_referensi(entri: str) -> int | None:
    """Tahun terbit dari satu entri referensi, atau None kalau tidak ada.

    Yang dibaca pertama kali adalah tahun di dalam kurung -- `Suprapto. (2025).`
    -- karena itu satu-satunya tahun yang pasti menunjuk tanggal terbit.
    Tahun empat digit lain di entri (mis. dalam judul atau catatan penerbit)
    bisa apa saja, jadi tidak dipakai.
    """
    dalam_kurung = re.search(r"\((?:[^()]{0,40}?)\b(1[5-9]\d{2}|20\d{2}|21\d{2})\b", entri)
    if dalam_kurung:
        return int(dalam_kurung.group(1))
    return None


def _entri_referensi(tail: str) -> list[str]:
    """Daftar entri dari isi bagian 'Daftar Pustaka'.

    Tiga bentuk diterima, karena tiga hal menulis Daftar Pustaka di pipeline ini:
    pipeline sendiri (satu baris polos), agen `pencari-pustaka` (satu baris polos),
    dan jawaban versi lama (nomor atau bullet di depan). Bentuk polos harus
    tetap diterima -- kalau tidak, Daftar Pustaka yang justru paling sesuai
    aturan APA 7 akan dianggap kosong dan item ditolak.

    Yang bukan entri: heading, baris kosong, baris placeholder
    'TIDAK ADA REFERENSI YANG TERVERIFIKASI', dan baris yang jelas kerangka
    kerja (lihat `_HUMANIZER_SCAFFOLD_RE`).

    Placeholder harus dibuang di sini, bukan nanti. Kalau ia ikut terhitung
    sebagai entri, pemanggil sekaligus melihat "ada entri" dan "ada
    placeholder", lalu menyimpulkan agen menulis keduanya padahal tidak --
    padahal satu-satunya isi Daftar Pustaka itu placeholder-nya sendiri.
    """
    entries: list[str] = []
    for raw in (tail or "").splitlines():
        baris = raw.strip()
        if not baris or baris.startswith("#"):
            continue
        if _HUMANIZER_SCAFFOLD_RE.match(baris):
            continue
        # Buang penanda markdown di depan entri: bullet, nomor, atau bold.
        baris = re.sub(r"^(?:[-*+]|\[?\d+\]?[.)]?)\s+", "", baris)
        baris = baris.strip("*_ ").strip()
        if not baris or _NO_REFERENSI_RE.search(baris):
            continue
        entries.append(baris)
    return entries


def _cek_entri_referensi(entries: list[str]) -> list[str]:
    """Periksa entri Daftar Pustaka: boleh dari mana, dan harus bisa dicek.

    Dua aturan yang ditegakkan di sini. Pertama, rujukan yang dicari sendiri
    harus masuk 10 tahun terakhir -- dua entri dalam jawaban produksi yang lalu
    berasal dari luar sesi sama sekali (1966 dan 2010), dan itu terlihat langsung
    oleh dosen. Kedua, ISBN dan jumlah halaman hanya boleh muncul pada entri
    katalog resmi UT, karena di luar itu metadata seperti itu tidak bisa diperiksa
    dan justru sering dikarang model.
    """
    issues: list[str] = []
    tahun_min = _tahun_min_referensi()
    terlalu_lama: list[str] = []
    metadata_ngarang: list[str] = []

    for entri in entries:
        # Entri katalog UT: pipeline menuliskannya langsung dari halaman
        # pustaka.ut.ac.id, jadi isinya terverifikasi dan exempt dari batas
        # tahun -- bahan ajar yang ditunjuk tutor memang boleh tua.
        dari_katalog_ut = bool(_URL_UT_RE.search(entri))
        tahun = _tahun_dalam_referensi(entri)
        if (
            not dari_katalog_ut
            and tahun is not None
            and tahun < tahun_min
        ):
            terlalu_lama.append(f"{entri[:60]} (tahun {tahun})")
        if not dari_katalog_ut and _METADATA_KATALOG_RE.search(entri):
            metadata_ngarang.append(entri[:60])

    if terlalu_lama:
        issues.append(
            f"referensi di luar batas {Config.TUTON_PUSTAKA_TAHUN_MAX} tahun "
            f"terakhir: {'; '.join(terlalu_lama[:2])}"
        )
    if metadata_ngarang:
        issues.append(
            "referensi non-katalog UT menyebut ISBN/jumlah halaman yang tidak "
            f"bisa diverifikasi: {'; '.join(metadata_ngarang[:2])}"
        )
    return issues


def answer_quality_issues(text: str) -> list[str]:
    """Deteksi jawaban yang korup, tidak lengkap, atau terdengar seperti model.

    Mengembalikan daftar masalah (kosong = jawaban lolos). Ini pagar terhadap
    kegagalan yang pernah terjadi: karakter korup setelah beberapa kali edit,
    jawaban tanpa Daftar Pustaka padahal sitasi bagian wajib, jawaban yang
    berbahasa orang ketiga padahal harus ditulis sebagai "saya", dan referensi
    yang mengarang ISBN atau terlalu lama untuk dipakai.
    """
    issues: list[str] = []
    body = (text or "").strip()
    if not body:
        return ["jawaban kosong"]

    if _CTRL_RE.search(body):
        issues.append("mengandung karakter kontrol")
    if _FOREIGN_SCRIPT_RE.search(body):
        issues.append("mengandung script non-Latin (teks korup)")
    if _EDIT_ARTIFACT_RE.search(body):
        issues.append("mengandung coretan edit (mis. '1:1_changed')")

    if not re.search(r"^#+\s*daftar\s+pustaka", body, re.IGNORECASE | re.MULTILINE):
        issues.append("tidak ada bagian 'Daftar Pustaka'")
    else:
        tail = re.split(
            r"^#+\s*daftar\s+pustaka", body, maxsplit=1,
            flags=re.IGNORECASE | re.MULTILINE,
        )[-1]
        refs = _entri_referensi(tail)
        # Placeholder "TIDAK ADA REFERENSI YANG TERVERIFIKASI" adalah jawaban
        # yang jujur, bukan kegagalan. Prompt (generator/prompt.py) menyuruh
        # agent menulis baris itu persis ketika tahap `pencari-pustaka` gagal
        # atau memang tidak menemukan sumber. Sebelumnya baris ini tidak
        # cocok pola entri di atas, jadi selalu dihitung "kosong" dan item
        # ditolak -- padahal akan ditolak juga kalau kita memaksa agent
        # mengarang referensi. Jadi: boleh lolos, tapi dicatat supaya
        # docx bisa menandainya dan jangan dikira punya sitasi.
        has_placeholder = any(
            _NO_REFERENSI_RE.search(ln) for ln in tail.splitlines()
        )
        if not refs and not has_placeholder:
            issues.append("Daftar Pustaka kosong (tidak ada entri)")
        elif refs and has_placeholder:
            # Dua-duanya: berarti agent menulis placeholder padahal punya
            # entri. Buang placeholder-nya, sisanya tetap dipakai.
            issues.append(
                "Daftar Pustaka memuat placeholder 'TIDAK ADA REFERENSI' "
                "beberapa kali padahal sudah ada entri"
            )
        elif len(refs) > Config.TUTON_MAX_PUSTAKA:
            # Batas jumlah entri adalah batas biaya, bukan selera. Setiap
            # entri tambahan berarti satu putaran webfetch pada tahap
            # `pencari-pustaka`, dan daftar yang terlalu panjang juga tidak
            # terbaca. Menegakkan batas di sini membuat pagu ini bekerja:
            # prompt bisa saja salah, tapi hasil akhirnya tetap tidak bisa
            # melewatinya.
            issues.append(
                f"Daftar Pustaka berisi {len(refs)} entri, "
                f"melebihi batas {Config.TUTON_MAX_PUSTAKA}"
            )
        else:
            issues.extend(_cek_entri_referensi(refs))

    jawab = re.search(r"^#+\s*jawab", body, re.IGNORECASE | re.MULTILINE)
    isi = body[jawab.end():] if jawab else body
    if len(isi.strip()) < 120:
        issues.append("isi jawaban terlalu pendek (<120 karakter)")

    # Bahasa orang pertama. Ini yang paling sering hilang tanpa kelihatan: jawaban
    # boleh lengkap, referensinya boleh sah, tapi tetap impersonal karena ditulis
    # sebagai laporan. Yang diminta tutor adalah tulisan mahasiswa, jadi "saya"
    # wajib muncul.
    if len(isi.split()) >= 40 and not _SAYA_RE.search(isi):
        issues.append('tidak ada kata "saya" (jawaban harus ditulis orang pertama)')

    tell = _AI_TELL_RE.search(body)
    if tell:
        issues.append(f'berbahasa model: memakai frasa "{tell.group(0).strip()}"')
    scaffold = _HUMANIZER_SCAFFOLD_RE.search(body)
    if scaffold:
        issues.append(
            f'bocor kerangka humanizer: "{scaffold.group(0).strip()[:40]}"'
        )

    # Menyalin jawaban orang lain. Ini bukan rapa, ini kegagalan tugas: isi
    # yang diambil dari balasan mahasiswa lain berarti tugas ini tidak dikerjakan
    # sama sekali. Gate menangkap dua sisi yang berbeda.
    #
    # Sisi pertama dan paling penting adalah kesaksian yang benar-benar ada di
    # teks ("seperti yang ditulis mahasiswa lain", "disalin dari forum"). Kalau
    # kalimat seperti ini lolos ke berkas yang diserahkan, pengajar langsung
    # tahu sumbernya -- dan plaintext-nya jadi bukti sendiri.
    #
    # Sisi kedua adalah kalimat yang terlalu rapi untuk ditulis sendiri: anak
    # kosakata seragam, kalimat lengkap, tanpa satu pun kata ganti orang
    # pertama. Itu ciri teks yang diambil dari dokumen lain, bukan ditulis sambil
    # mengerjakan. Syaratnya sengaja dibuat ketat supaya teks yang benar-benar
    # ditulis dengan "saya" tidak ikut tertangkap.
    curang = _ORANG_LAIN_RE.search(isi)
    if curang:
        issues.append(
            "menyebut atau memakai jawaban orang lain: "
            f'"{curang.group(0).strip()}"'
        )
    elif _terlalu_rapi(isi):
        issues.append(
            "teks terlalu serapi dan tanpa kata ganti orang pertama; "
            "kemungkinan bukan ditulis sendiri"
        )
    return issues


# Kata ganti orang pertama. "Saya" adalah kata yang harus muncul kalau teks itu
# ditulis sendiri; ketidakhadirannya pada teks panjang yang rapi adalah tanda
# teks itu diambil dari sumber lain.
_KORBAN_RE = re.compile(r"\b(saya|aku|gua|kami|kita)\b", re.IGNORECASE)


def _terlalu_rapi(isi: str) -> bool:
    """Deteksi teks yang terlalu rapi untuk hasil kerja sendiri.

    Syaratnya sengaja dibuat pendek dan kasar, karena ini alat bantu keputusan,
    bukan pembuktian. Yang dipancing bukan "teks bagus", melainkan "teks yang
    tidak mungkin ditulis orang yang sedang mengerjakan tugas": kalimat lengkap
    semua, rata, tanpa satu pun kata ganti orang pertama, dalam jawaban yang
    panjang.

    Dua ambang, keduanya harus terpenuhi:

    - panjang: di bawah 120 kata, teks terlalu pendek untuk penilaian ini.
    - serapi: minimal 8 kalimat yang masing-masing punya isi, dan nol kata ganti
      orang pertama di seluruh teks.

    Verifikasi: jawaban yang dikerjakan sendiri hampir selalu memakai "saya" atau
    "kita" -- itu diminta aturan orang pertama, dan teks yang tidak memakainya
    sudah ditolak `_SAYA_RE` di atas. Jadi sinyal ini praktis tidak pernah
    menyalakan gate pada teks yang benar-benar dikerjakan.
    """
    if len(isi.split()) < 120:
        return False
    if _KORBAN_RE.search(isi):
        return False
    kalimat = [k for k in re.split(r"[.!?]\s+", isi.strip()) if len(k.split()) >= 4]
    return len(kalimat) >= 8


def _fail_item(record: Prefetched, key: str, reason: str) -> None:
    state.set_item(
        key,
        {
            "status": "failed",
            "matkul": record.course.name,
            "sesi": record.section_num,
            "kind": record.kind,
            "index": record.index,
            "desc": record.item.title,
            "created_at": now_stamp(),
            "finished_at": now_stamp(),
            "reason": reason,
        },
    )


# Pola rate limit harus spesifik. Versi lama mencantumkan `429` dan `503`
# polos, sehingga baris biasa seperti "halaman 429 karakter" atau nomor port
# ikut cocok -- dan karena ceknya berjalan sebelum jawaban diperiksa, satu item
# yang jawabannya sudah jadi tetap ditandai gagal.
_RATE_LIMIT_RE = re.compile(
    r"rate[ _-]?limit|too many requests|"
    r"(?:status|status\s*code|http|code|error)\D{0,3}429\b|"
    r"\b429\b\D{0,20}(?:too many requests|rate)|"
    r"(?:quota|credit)\b[^.\n]{0,40}(?:exhaust|exceed|depleted|insufficient|habis)|"
    r"(?:insufficient|out of|no)\s+(?:remaining\s+)?(?:quota|credit)\b|"
    r"overloaded|service unavailable|"
    r"(?:status|status\s*code|http|code|error)\D{0,3}503\b|"
    r"try again later",
    re.I,
)

def _env_rate_limit_sleep() -> int:
    from config import _env  # noqa: PLC0415

    return int(_env("TUTON_RATE_LIMIT_SLEEP", "90"))


def _is_rate_limit(text: str) -> bool:
    return bool(_RATE_LIMIT_RE.search(text or ""))


class DihentikanUser(RuntimeError):
    """Pengguna menekan Stop; pipeline harus berhenti, bukan mencoba lagi.

    Dipisah dari `TimeoutError` karena akibatnya berbeda. Timeout = "item ini
    gagal, coba lagi" -- masuk ke antrean retry lalu `state.json` boleh ditulis
    `failed`. Stop = "berhenti sekarang" -- retry harus dilewati, dan item
    yang belum selesai TIDAK boleh ditandai `failed`, karena itu akan membuat
    run berikutnya mengulang pekerjaan yang memang tidak sempat jalan.

    Tanpa pemisahan ini, satu klik Stop cukup untuk mengisi `state.json` dengan
    `failed` untuk tiap item yang sedang jalan -- persis kondisi yang membuat
    pengguna mengira pipeline "rusak sendiri".
    """


def _stop_diminta() -> bool:
    """True kalau pengguna meminta stop (sinyal dari server atau Ctrl-C)."""
    return opencode_runner.stop_requested()


def _pasang_handler_stop() -> None:
    """Ubah sinyal SIGTERM/SIGINT jadi berhenti bersih, bukan keluar diam-diam.

    Server memanggil proses ini lewat SIGTERM saat tombol Stop ditekan. Tanpa
    handler, SIGTERM langsung membunuh proses di tengah jalan: worker
    `opencode` yang sedang jalan menjadi anak yatim yang tidak tercatat, dan
    buffer log item hilang tanpa sempat dicetak.
    """
    def _tangan(signum, _frame):
        log(f"\n! stop diminta (sinyal {signum}). Menghentikan semua sesi...")
        opencode_runner.request_stop()

    for nama in ("SIGTERM", "SIGINT", "SIGBREAK"):
        sig = getattr(signal, nama, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _tangan)
        except (OSError, ValueError):
            # Bukan thread utama (mis. di dalam pool), atau sinyal tidak
            # didukung di OS ini. Tidak apa-apa: `server.py` tetap mematikan
            # proses lewat grup proses.
            pass


def _run_agent(
    record: Prefetched,
    key: str,
    *,
    prompt: str,
    jawaban_path: Path,
    prefix: str = "",
) -> bool:
    """Jalankan agent `tuton` dengan validasi kualitas. True kalau lolos.

    `prefix` dibiarkan kosong supaya baris cukup dari prefix thread yang
    dipasang `_safe_process`; kalau diisi di sini, tiap baris akan tercetak dua
    kali (satu dari sini, satu lagi saat buffer item dicetak).
    """
    started_at = now_stamp()
    started_mono = time.monotonic()
    jawaban_path.unlink(missing_ok=True)
    # Sisa draf dari versi lama dibersihkan di sini. Prompt sekarang menyuruh
    # agent me-humanize berkas jawaban itu sendiri, tapi `draf_jawaban.md`
    # dari run sebelumnya akan tetap tertinggal dan ikut terbawa ke folder yang
    # dikirim ke tutor.
    for sisa_draf in jawaban_path.parent.glob("draf_*.md"):
        try:
            sisa_draf.unlink()
        except OSError:
            pass

    retries = max(1, Config.TUTON_RETRIES)
    rate_limited = False
    result = None
    issues: list[str] = []
    # Catatan hasil gate untuk percobaan berikutnya. Versi lama menulis catatan
    # ini ke dalam berkas jawaban lalu langsung menghapus berkasnya -- jadi
    # namanya frasa yang salah, tapi agennya tidak pernah membacanya, dan
    # percobaan kedua mengulang kesalahan yang sama dengan kalimat yang sama.
    catatan = ""
    for attempt in range(1, retries + 1):
        # Cek stop SEBELUM percobaan baru dimulai. Kalau stop terjadi saat
        # `time.sleep(5)` atau `time.sleep(wait)` di bawah, percobaan berikut
        # akan berjalan utuh padahal user sudah minta berhenti.
        if _stop_diminta():
            log("dihentikan sebelum percobaan berikutnya dimulai.")
            raise DihentikanUser("stop diminta")
        try:
            log(f"→ opencode run ... (percobaan {attempt}/{retries})")
            result = run_opencode(
                prompt + catatan,
                agent="tuton",
                model=writer_model() or None,
                timeout=Config.TUTON_TIMEOUT,
            )
        except opencode_runner.RunStopped as exc:
            log(f"dihentikan: {exc}")
            raise DihentikanUser(str(exc)) from exc
        except TimeoutError:
            log(f"! opencode timeout di percobaan {attempt}/{retries}")
            continue
        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            log(f"! opencode exit {result.returncode}\n{output[-1200:]}")
        rate_limited = rate_limited or _is_rate_limit(output)
        # Cek jawaban DULU. Dulu urutannya terbalik: begitu output mengandung
        # kata "rate limit", item langsung tidur lalu mengulang -- padahal
        # opencode sering sudah menulis jawaban lengkap di percobaan pertama.
        if not (jawaban_path.exists() and jawaban_path.stat().st_size > 100):
            if rate_limited and attempt < retries:
                wait = _env_rate_limit_sleep() * attempt
                log(
                    f"! provider menyatakan rate limit. Menunggu {wait}s sebelum "
                    f"mencoba lagi (percobaan {attempt}/{retries}). Jangan "
                    "menambah --jobs sampai batas ini selesai."
                )
                time.sleep(wait)
                continue
            log(f"! jawaban belum tertulis (percobaan {attempt}/{retries})")
            if attempt < retries:
                time.sleep(5)
            continue

        issues = answer_quality_issues(
            jawaban_path.read_text(encoding="utf-8", errors="replace")
        )
        if not issues:
            break
        log(
            f"! kualitas jawaban belum memenuhi ({'; '.join(issues)}) "
            f"[percobaan {attempt}/{retries}]"
        )
        if attempt < retries:
            # Beri tahu agent apa yang salah supaya tidak mengulang kesalahan.
            # Catatan masuk ke PROMPT, bukan ke berkas jawaban: berkas jawaban
            # ditulis ulang dari nol pada percobaan berikutnya, jadi catatan
            # yang disimpan di sana ikut terhapus sebelum sempat dibaca.
            catatan = (
                "\n\n---\n\nPERHATIAN, versi sebelumnya ditolak karena:\n"
                + "\n".join(f"- {masalah}" for masalah in issues)
                + "\n\nTulis ulang seluruh jawaban dari awal, bukan edit parsial. "
                "Perbaiki setiap masalah di atas secara harfiah: kalau yang "
                "disebut adalah frasa yang dilarang, frasa itu harus hilang dari "
                "teks, bukan hanya dijelaskan ulang.\n"
            )
            jawaban_path.unlink(missing_ok=True)
    else:
        # `rate_limited` hanya relevan kalau jawaban memang tidak pernah
        # tertulis. Kalau jawabannya ada tapi(mutu) jelek, penyebabnya kualitas
        # -- bukan provider.
        if rate_limited and not issues:
            reason = (
                "rate limit provider. Item ini aman dijalankan ulang nanti "
                "tanpa --force."
            )
            log(f"✗ gagal: {reason}")
        else:
            reason = "; ".join(issues) or (
                "jawaban tidak tertulis (kemungkinan timeout atau error provider)"
            )
            log(f"✗ gagal menghasilkan jawaban yang layak: {reason}")
        _fail_item(record, key, reason)
        return False

    if result is not None and result.returncode == 0:
        ok = (result.stdout or "").strip().splitlines()
        if ok:
            log(ok[-1][:120])

    finished_at = now_stamp()
    return _write_docx(
        record,
        key,
        jawaban_path=jawaban_path,
        started_at=started_at,
        started_mono=started_mono,
        finished_at=finished_at,
    )


def _kode_matkul_item(record: Prefetched) -> str:
    """Kode mata kuliah item ini, dari mana pun yang menyebutnya.

    Urutan sumber: transkrip lampiran soal, lalu peta sesi, lalu teks Reader.
    Yang pertama dipilih karena transkrip lampiran soal hampir selalu memuat
    header dokumen resmi UT yang mencantumkan kodenya.
    """
    for teks in (
        "\n".join((record.transcripts or {}).values()),
        record.petak_text or "",
        source_note(record),
        _teks_referensi_item(record),
    ):
        kode = bahan_ajar.find_kode_matkul(teks)
        if kode:
            return kode
    # Terakhir: kode mungkin sudah ada di nama folder/nama course.
    for sumber in (record.course.name, record.course.folder_name):
        kode = bahan_ajar.find_kode_matkul(sumber)
        if kode:
            return kode
    return ""


def source_note(record: Prefetched) -> str:
    """Teks sumber Reader milik item ini, kalau sudah diambil."""
    source = record.source
    return (getattr(source, "soal_text", "") or "") if source else ""


def _teks_referensi_item(record: Prefetched) -> str:
    """Isi berkas referensi item ini, atau string kosong.

    Dipakai sebagai sumber terakhir untuk kode mata kuliah. Buku ajar resmi
    selalu mencantumkan kodenya di judul (`Aljabar Linear Elementer 2
    (MATA4113)`), dan di Diskusi UT kode itu sering TIDAK muncul di halaman
    sesi maupun di nama course Moodle -- satu-satunya tempat ia muncul resmi
    adalah katalog, yang dibaca agen saat menyusun Daftar Pustaka.
    """
    path = record.referensi
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _write_docx(
    record: Prefetched,
    key: str,
    *,
    jawaban_path: Path,
    started_at: str,
    started_mono: float,
    finished_at: str,
) -> bool:
    out_dir = record.out_dir or (
        OUTPUT_DIR / record.course.folder_name / f"sesi{record.section_num}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    log("→ membuat docx ...")
    jawaban_md = jawaban_path.read_text(encoding="utf-8")
    source = record.source
    meta = {
        "nama": Config.NAMA,
        "nim": Config.NIM,
        "prodi": Config.PRODI,
        "semester": Config.SEMESTER,
        "ut_daerah": Config.UT_DAERAH,
        "matkul": record.course.name,
        # Nama course di Moodle tidak memuat kode ("Aljabar Linear Elementer 95"),
        # sedangkan kode ada di isi lampiran ("STMA4113"). Ambil dari sana supaya
        # judul dokumen jadi "Diskusi 4 - Aljabar Linear Elementer 95 (STMA4113)".
        "matkul_kode": _kode_matkul_item(record),
        "kind_label": "Diskusi" if record.kind == "diskusi" else "Tugas",
        "display_index": record.index,
        "file_base": (
            f"{record.course.folder_name}_"
            f"{'Diskusi' if record.kind == 'diskusi' else 'Tugas'}{record.index}"
        ),
    }
    # Soal untuk .docx. Dua sumber, sesuai bentuk aslinya:
    #   - `soal_text` dari Reader untuk soal yang berupa teks;
    #   - `gambar_soal` (lampiran gambar yang lolos klasifikasi) untuk soal
    #     yang berupa screenshot -- dan itu yang terjadi di Diskusi UT, di mana
    #     halaman forum cuma berisi instruksi umum dan soalnya ada di gambar.
    # Kalau teks Reader-nya cuma kalimat pengantar, transkripsi lampiran dipakai
    # sebagai ganti supaya bagian Soal tidak kosong.
    soal_teks = (source.soal_text if source else "") or ""
    if not record.gambar_soal and len(_soal_bersih(soal_teks)) < 120:
        transkrip_soal = "\n\n".join(
            teks for nama, teks in (record.transcripts or {}).items()
        )
        if transkrip_soal.strip():
            soal_teks = transkrip_soal
    try:
        _, doc_path = save_doc(
            jawaban_md=jawaban_md,
            soal_text=soal_teks,
            meta=meta,
            out_dir=out_dir,
            template=record.template,
            include_soal=True,
            gambar_soal=list(record.gambar_soal),
        )
    except Exception as exc:  # noqa: BLE001
        log(f"✗ gagal membuat docx: {type(exc).__name__}: {exc}")
        _fail_item(record, key, f"docx gagal: {exc}")
        return False
    log(f"✓ {doc_path.name} siap.")

    state.set_item(
        key,
        {
            "status": "done",
            "matkul": record.course.name,
            "sesi": record.section_num,
            "kind": record.kind,
            "index": record.index,
            "desc": record.item.title,
            "created_at": started_at,
            "finished_at": finished_at,
            "duration_sec": round(time.monotonic() - started_mono, 1),
            "urls": [link.url for link in source.ok_links] if source else [],
            "outputs": [str(doc_path), str(jawaban_path)],
            "version": state.OUTPUT_VERSION,
        },
    )
    log(f"⏱ {started_at} → {finished_at}")
    return True


def _process_record(record: Prefetched, *, force: bool, mode: str) -> bool:
    """Kerjakan satu item yang sudah di-prefetch."""
    key = f"{record.course.id}:{record.item.mod_type}:{record.item.id}"
    if not force and state.is_done(key):
        log(
            f"· {record.item.title} → sudah dikerjakan, dilewati "
            "(--force untuk ulang).",
            prefix=f"[{record.kind}] ",
        )
        return False

    assert record.out_dir is not None
    source = record.source
    if source is None or not source.ok_links:
        reason = record.error or (source.note if source else "tidak ada sumber")
        log(f"⛔ dilewati: {reason}")
        _fail_item(record, key, "soal_tidak_ditemukan")
        raise SoalNotFound(reason)

    lamp_dir = record.out_dir / "lampiran"
    # Lampiran dinormalisasi ke `Path` sekali di sini. Datanya datang dari
    # beberapa tempat (downloader, jalur file, pemanggilan manual) dan salah
    # satu bisa memberi string; setelah itu semua pemakai cukup `.name`,
    # `.stem`, `.suffix` tanpa perlu memastikan tipenya.
    record.attachments = [Path(p) for p in record.attachments]
    # Lampiran mahasiswa lain DISEBARKAN dari daftar yang dilihat agent. Daftar
    # lampiran bukan sekadar informasi: agent yang punya tool `read` bisa
    # membukanya sendiri, jadi disebut berarti عامًا. Dari run sungguhan, agent
    # membaca PDF jawaban mahasiswa lalu mengikuti isinya.
    nama_mahasiswa = {nama for nama, _ in record.lampiran_mahasiswa}
    # `transcripts` sudah peta {nama_berkas: teks}, jadi kuncinya langsung
    # berupa nama -- bukan objek Path.
    transkrip = set(record.transcripts or {})
    lampiran = (
        [
            p.name
            for p in sorted(lamp_dir.glob("*"))
            if p.is_file()
            and p.name not in nama_mahasiswa
            and not p.name.startswith("transkrip_")
            and p.name not in transkrip
        ]
        if lamp_dir.exists()
        else []
    )
    soal_urls = source.reader_urls()
    if not soal_urls:
        reason = "URL sumber tidak bisa disajikan ke agent"
        log(f"⛔ dilewati: {reason}")
        _fail_item(record, key, "soal_tidak_ditemukan")
        raise SoalNotFound(reason)

    jawaban_path = record.out_dir / f"jawaban_{record.kind}_{record.index}.md"
    # Sama seperti `lampiran` di atas: lampiran mahasiswa lain tidak boleh
    # disebut sebagai bahan bacaan.
    attachments = [
        str(p) for p in record.attachments if p.name not in nama_mahasiswa
    ]
    can_read_files = _agent_can_read_files()
    if mode == "url":
        # Peta soal dan daftar referensi datang dari tahap sebelumnya. Kalau
        # salah satunya kosong, `build_prompt` otomatis menaruh instruksi
        # webfetch sebagai cadangan, jadi agen penulis tetap bisa jalan.
        prompt = build_prompt(
            mode="url",
            work_kind=record.kind,
            index=record.index,
            course_name=record.course.name,
            section_num=record.section_num,
            activity_title=record.item.title,
            soal_urls=soal_urls,
            source_urls=[link.url for link in source.ok_links],
            attachments=attachments,
            transcript_path=record.transcript_path,
            lampiran_dir=lamp_dir,
            jawaban_path=jawaban_path,
            agent_can_read_files=can_read_files,
            petak_path=record.petak,
            pustaka_path=record.referensi,
        )
    else:
        # Mode file: susun soal.md dari konten Reader supaya tetap konsisten.
        from generator.prompt import build_file_prompt  # noqa: PLC0415

        soal_text = source.soal_text or ""
        soal_path = record.out_dir / "soal.md"
        soal_path.write_text(soal_text, encoding="utf-8")
        prompt = build_file_prompt(
            work_kind=record.kind,
            index=record.index,
            course_name=record.course.name,
            section_num=record.section_num,
            activity_title=record.item.title,
            soal_path=soal_path,
            attachment_dir=lamp_dir,
            lampiran=lampiran,
            jawaban_path=jawaban_path,
        )

    return _run_agent(record, key, prompt=prompt, jawaban_path=jawaban_path)


_VISION_CACHE: dict[str, bool] = {}


def _agent_can_read_files() -> bool:
    """Apakah model agent `tuton` bisa melihat gambar/PDF.

    Kalau belum tahu, dijawab dari env TUTON_TRANSCRIBE (auto). Kita tidak
    menjalankan probe vision secara default karena itu satu panggilan model
    mahal; jalankan `python main.py vision-probe` bila perlu memastikan.
    """
    mode = (Config.TUTON_TRANSCRIBE or "auto").lower()
    if mode == "never":
        return True   # file diserahkan ke agent secara eksplisit
    if mode == "always":
        return False  # transkripsi selalu dipakai
    # auto: default hemat, agent tetap boleh read kalau memang_diblokir
    return bool(_VISION_CACHE.get("can_read", False))


# ---------------------------------------------------------------------------
# Orkestrasi per course / seluruh run
# ---------------------------------------------------------------------------
def _gather_jobs(
    scraper: CourseScraper,
    course_id: int,
    *,
    sesi_filter: int | None,
    kind_filter: str,
) -> tuple[Course | None, list[tuple[Course, int, Activity, str]]]:
    courses = scraper.get_courses()
    course = next((c for c in courses if c.id == course_id), None)
    jobs: list[tuple[Course, int, Activity, str]] = []
    if course is None:
        return None, jobs
    for sec in scraper.get_available_sections(course_id):
        if sesi_filter is not None and sec.number != sesi_filter:
            continue
        diskusi, tugas, _ = scraper.split_assignable(sec.activities)
        if kind_filter in ("all", "diskusi"):
            jobs.extend((course, sec.number, d, "diskusi") for d in diskusi)
        if kind_filter in ("all", "tugas"):
            jobs.extend((course, sec.number, t, "tugas") for t in tugas)
    return course, jobs


def _process_course(
    session: MoodleSession,
    scraper: CourseScraper,
    downloader: AttachmentDownloader,
    reader: MoodleReader,
    course_id: int,
    *,
    sesi_filter: int | None,
    force: bool,
    kind_filter: str = "all",
    mode: str = "url",
    jobs_workers: int = 1,
    remap: bool = False,
) -> int:
    """Kerjakan satu mata kuliah: peta -> referensi -> jawaban -> docx.

    Dua sakelar cache, dan bedanya disengaja:

    - `force`   mengulang PENULISAN jawaban saja. Peta soal dan daftar pustaka
                masih dipakai dari cache. Ini kasus yang paling sering terjadi:
                jawaban sebelumnya salah, tapi datanya sudah benar.
    - `remap`   membuang cache peta dan referensi, lalu memetakan ulang. Pakai
                ini hanya kalau peta itu sendiri yang keliru, misalnya tutor
                baru saja mengganti naskah soal. Menjalankan `--force` tanpa
                `--remap` saat peta keliru hanya menghasilkan jawaban keliru
                yang sama, dua kali bayar.
    """
    course, jobs = _gather_jobs(
        scraper, course_id, sesi_filter=sesi_filter, kind_filter=kind_filter
    )
    if course is None:
        log(f"Kursus id {course_id} tidak ditemukan.")
        return 0

    log(f"\n=== {course.name} ===")
    # Model yang dipakai ditampilkan sekali per mata kuliah. Dua peran dengan
    # biaya yang jauh berbeda; kalau keduanya jatuh ke model termahal, pemetaan
    # dan pencarian referensi tidak menambah penghematan apa pun.
    roles = models.describe()
    log(
        f"  · model: penulis `{roles['writer']}` · pembantu `{roles['helper']}`",
        prefix="  ",
    )
    total = len(jobs)
    if total == 0:
        label = {"all": "tugas dan diskusi", "tugas": "tugas", "diskusi": "diskusi"}[
            kind_filter
        ]
        log(
            f"  · TOTAL: 0 item (filter: {label}"
            + (f", sesi {sesi_filter}" if sesi_filter is not None else "")
            + ")"
        )
        return 0
    log(f"  · TOTAL: {total} item (filter: {kind_filter}, mode: {mode})")

    # Lewati yang sudah selesai sebelum kerja mahal apa pun.
    pending: list[tuple[Course, int, Activity, str]] = []
    for job in jobs:
        _, _, item, _ = job
        k = f"{course.id}:{item.mod_type}:{item.id}"
        if not force and state.is_done(k):
            log(f"  · {item.title} → sudah dikerjakan, dilewati.", prefix="  ")
            continue
        pending.append(job)

    if not pending:
        log("  · tidak ada item baru.")
        return 0

    # Tahap 0: peta soal per sesi. Harus selesai sebelum transkripsi dan
    # pencarian referensi, karena ketiganya membaca artefak yang saling
    # bergantung: peta memberi soal, transkrip memberi isi lampiran, daftar
    # referensi memakai keduanya untuk memilih sumber.
    sections = [s for s in scraper.get_available_sections(course_id)
                if s.number in {sec for _, sec, _, _ in pending}]
    peta_by_section = (
        _petak_stage(course, sections, force=remap) if mode == "url" else {}
    )

    discovery = SourceDiscovery(reader, make_url=soalu)
    records = _prefetch_all(discovery, downloader, pending)
    _transcribe_stage(records)

    # Tahap 1: daftar pustaka per item, memakai peta dan transkrip.
    if mode == "url":
        referensi_by_id = _pustaka_stage(records, peta_by_section, force=remap)
        for record in records:
            record.petak = peta_by_section.get(record.section_num)
            record.referensi = referensi_by_id.get(id(record))

    # Kerjakan; satu item gagal TIDAK lagi memblokir sisa item di seksi yang
    # sama (perilaku lama: `blocked_session` menghentikan satu sesi penuh).
    total_records = len(records)
    for pos, record in enumerate(records, 1):
        record.pos = pos
        record.total = total_records

    worked = 0
    skipped = 0
    workers = max(1, min(jobs_workers, len(records)))
    log(f"  · mengerjakan {len(records)} item dengan {workers} worker...")
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="solve") as pool:
        # Item yang belum dimulai dibatalkan, bukan dijalankan lalu dihentikan
        # di tengah jalan. Tanpa ini, satu klik Stop tetap membayar token untuk
        # seluruh antrean yang belum sempat dimulai.
        futures = [
            pool.submit(_safe_process, record, force=force, mode=mode)
            for record in records
        ]
        try:
            for future in as_completed(futures):
                try:
                    if future.result():
                        worked += 1
                    else:
                        skipped += 1
                except Exception:  # noqa: BLE001 - _safe_process sudah menangani
                    skipped += 1
        except KeyboardInterrupt:
            opencode_runner.request_stop()
            for future in futures:
                future.cancel()
            log("\n! stop diminta: membatalkan item yang belum mulai.")
        if _stop_diminta():
            # `as_completed` sudah berhenti, tapi future yang tidak batal masih
            # bisa punya worker aktif. Tunggu sampai semua worker keluar supaya
            # tidak ada `opencode run` yang menulis setelah pipeline ditutup.
            for future in futures:
                future.cancel()
                try:
                    future.result(timeout=Config.TUTON_TIMEOUT + 30)
                except Exception:  # noqa: BLE001 - hanya untuk menunggu keluar
                    pass

    if _stop_diminta():
        log(
            f"\nBerhenti karena permintaan pengguna. {worked} item sudah selesai "
            "sebelum stop; sisakan `pending` supaya run berikutnya melanjutkan, "
            "bukan mengulang dari awal."
        )
        return worked

    log(f"\nSelesai. {worked} item jadi untuk {course.name}"
        + (f", {skipped} dilewati/gagal." if skipped else "."))
    return worked


def _safe_process(record: Prefetched, *, force: bool, mode: str) -> bool:
    """Kerjakan satu item, menahan log-nya sendiri lalu menampilkannya utuh.

    Buffernya per-thread, jadi dua item yang jalan bersamaan tidak saling
    menimpa keluaran. Mode live menyalin apa pun yang di-`print` ke terminal
    seketika; kalau tidak, satu `opencode run` yang working beberapa menit
    terlihat seperti pipeline hang. Karena isi buffer sudah tampil live, blok
    yang dicetak ulang di akhir dilewati.
    """
    tag = f"[{record.pos}/{record.total}] " if record.total > 1 else ""
    prefix = f"{tag}[{record.kind}] {record.item.title} - "
    buffer = io.StringIO()
    _LOCAL.buffer = buffer
    _LOCAL.prefix = prefix
    _LOCAL.live = True
    _LOCAL.live_pending = ""
    ok = False
    try:
        ok = _process_record(record, force=force, mode=mode)
    except DihentikanUser as exc:
        # Jangan tulis `failed`: item ini belum selesai, dan ditandai begitu
        # akan membuatnya terulang dari nol pada run berikutnya -- persis
        # pekerjaan yang tidak pernah sempat selesai.
        log(f"dihentikan: {exc}")
        ok = False
    except SoalNotFound as exc:
        log(f"dilewati: {exc}")
    except Exception as exc:  # noqa: BLE001 - satu item tidak boleh mematikan batch
        log(f"error tak terduga: {type(exc).__name__}: {exc}")
        if os.environ.get("TUTON_DEBUG_TRACEBACK"):
            # Traceback penuh hanya atas permintaan. Jenis galat saja sering
            # tidak cukup: `AttributeError: 'str' object has no attribute
            # 'name'` tidak_memberi tahu pemanggil mana yang salah.
            import traceback

            log(traceback.format_exc())
        state.set_item(
            f"{record.course.id}:{record.item.mod_type}:{record.item.id}",
            {
                "status": "failed",
                "matkul": record.course.name,
                "sesi": record.section_num,
                "kind": record.kind,
                "index": record.index,
                "desc": record.item.title,
                "reason": f"{type(exc).__name__}: {exc}",
            },
        )
        ok = False
    finally:
        _flush_live()
        _LOCAL.buffer = None
        _LOCAL.prefix = ""
        _LOCAL.live = False
        _LOCAL.live_pending = ""
    return ok


def cmd_run(args):
    Config.require()
    # Handler stop dipasang sebelum apa pun yang mungkin berjalan lama, supaya
    # SIGTERM dari server (tombol Stop) dan Ctrl-C punya akibat yang sama.
    _pasang_handler_stop()
    # Run sebelumnya di proses yang sama bisa meninggalkan tanda stop; kalau
    # tidak dihapus, item pertama akan langsung berhenti.
    opencode_runner.clear_stop()
    session = MoodleSession()
    session.check_login()
    scraper = CourseScraper(session)
    downloader = AttachmentDownloader(session)
    reader = MoodleReader()

    # Mode soal hanya punya satu jalur resmi sekarang: pipeline tiga tahap.
    # `--soal-mode file` masih ada sebagai jalur uji A/B (Form Soal memakai
    # jalur yang sama persis), tapi tidak lagi bisa datang dari .env: dulu ini
    # sakelarnya, dan sakelar yang tersembunyi membuat hasil run tidak bisa
    # dijelaskan hanya dari log.
    mode = getattr(args, "soal_mode", "") or "url"
    if mode not in ("url", "file"):
        mode = "url"
    jobs_workers = int(getattr(args, "jobs", 0) or Config.TUTON_JOBS or 1)
    remap = bool(getattr(args, "remap", False))
    ensure_reader()  # nyalakan hanya sekali; idempoten

    sesi_filter = int(args.sesi) if args.sesi else None
    kind_filter = getattr(args, "kind", None) or "all"
    if args.course:
        _process_course(
            session, scraper, downloader, reader,
            int(args.course), sesi_filter=sesi_filter, force=args.force,
            kind_filter=kind_filter, mode=mode, jobs_workers=jobs_workers,
            remap=remap,
        )
    else:
        for c in scraper.get_courses():
            _process_course(
                session, scraper, downloader, reader,
                c.id, sesi_filter=sesi_filter, force=args.force,
                kind_filter=kind_filter, mode=mode, jobs_workers=jobs_workers,
                remap=remap,
            )


def cmd_solve(args):
    """Kerjakan soal dari form (teks manual / file upload) tanpa scrape otomatis."""
    Config.require()
    _pasang_handler_stop()
    opencode_runner.clear_stop()
    session = MoodleSession()
    session.check_login()
    scraper = CourseScraper(session)
    reader = MoodleReader()

    courses = scraper.get_courses()
    course = next((c for c in courses if c.id == args.course), None)
    if course is None:
        log(f"Kursus id {args.course} tidak ditemukan.")
        return

    kind = args.kind
    sesi = args.sesi
    title = (args.title or f"{kind} {sesi}").strip()
    index = _custom_index(title, kind)

    out_dir = OUTPUT_DIR / course.folder_name / f"sesi{sesi}"
    lamp_dir = out_dir / "lampiran"
    out_dir.mkdir(parents=True, exist_ok=True)
    lamp_dir.mkdir(parents=True, exist_ok=True)

    log(f"\n=== {course.name} (form soal) ===")
    log(f"  · [{kind}] {title} → {out_dir.relative_to(OUTPUT_DIR)}")

    body_parts: list[str] = []
    if getattr(args, "text", ""):
        text_path = Path(args.text)
        if text_path.exists():
            body = text_path.read_text(encoding="utf-8", errors="replace").strip()
            if body:
                body_parts.append(body)
            text_path.unlink(missing_ok=True)

    saved: list[Path] = []
    for raw_file in _as_list(getattr(args, "file", "")):
        upload_path = Path(raw_file)
        if not upload_path.exists():
            log(f"  ! file lampiran tidak ditemukan: {upload_path}")
            continue
        dest = lamp_dir / upload_path.name
        if dest.exists() and not dest.samefile(upload_path):
            dest = lamp_dir / f"custom_{int(time.time() * 1000)}_{upload_path.name}"
        try:
            shutil.move(str(upload_path), str(dest))
        except OSError as exc:
            log(f"  ! gagal menyimpan lampiran {upload_path.name}: {exc}")
            continue
        saved.append(dest)
        log(f"  · Lampiran disimpan: {dest.name}")

    from moodle.transcribe import process_attachment

    transcribed: list[str] = []
    for p in saved:
        log(f"  · Transkripsi {p.name} ...")
        text = process_attachment(p, lamp_dir)
        if text.strip():
            log(f"    -> {len(text)} karakter")
        else:
            log(
                f"    ! GAGAL membaca {p.name}. Unggah PDF/gambar/DOCX/XLSX/PPTX, "
                "atau tulis soal langsung di kolom teks."
            )
        transcribed.append(text or "")
        body_parts.append(f"## Isi lampiran: {p.name} (transkripsi)")
        body_parts.append(text or "(tidak bisa dibaca otomatis - perlu dicek manual)")

    key = f"custom:{course.id}:{kind}:{sesi}:{index}"
    soal_path = out_dir / "soal.md"
    if not body_parts:
        soal_path.write_text(
            "\n".join([f"# {title}", ""])
            + "\nTIDAK ADA SOAL DITEMUKAN. Proses dihentikan, tidak ada jawaban "
            "yang dibuat.\n",
            encoding="utf-8",
        )
        state.set_item(
            key,
            {
                "status": "failed",
                "matkul": course.name,
                "sesi": sesi,
                "kind": kind,
                "index": index,
                "desc": title,
                "reason": "soal_tidak_ditemukan",
            },
        )
        log(f"  ⛔ Soal kosong untuk '{title}'. Proses dihentikan.")
        return

    soal_text = "\n".join([f"# {title}", "", *body_parts])
    soal_path.write_text(soal_text, encoding="utf-8")

    # Form soal selalu pakai mode file: sumbernya file unggahan, bukan URL
    # Moodle. Prompt mode file membaca file soal yang baru kita tulis.
    from generator.prompt import build_file_prompt  # noqa: PLC0415

    # Field "Format Jawaban" opsional. Berkas .docx yang diunggah pengguna
    # dipakai langsung sebagai dokumen dasar keluaran, sehingga margin, font,
    # dan style dokumennya benar-benar miliknya. Disalin ke folder khusus,
    # bukan ke `template/`, supaya file unggahan tidak diam-diam menggantikan
    # template standar pada run berikutnya.
    format_path: Path | None = None
    format_note = (getattr(args, "format_note", "") or "").strip()
    raw_format = (getattr(args, "format", "") or "").strip()
    if raw_format:
        upload = Path(raw_format)
        if upload.exists():
            fmt_dir = out_dir / "_format"
            fmt_dir.mkdir(parents=True, exist_ok=True)
            dest = fmt_dir / (
                upload.name if upload.suffix.lower() == ".docx" else "format.docx"
            )
            if dest.exists() and not dest.samefile(upload):
                dest = fmt_dir / f"format_{int(time.time())}.docx"
            try:
                shutil.move(str(upload), str(dest))
            except OSError as exc:
                log(f"  ! gagal menyimpan Format Jawaban: {exc}")
            else:
                format_path = dest
                log(f"  · Format Jawaban dipakai sebagai dokumen dasar: {dest.name}")
        else:
            log(f"  ! berkas Format Jawaban tidak ditemukan: {upload}")

    jawaban_path = out_dir / f"jawaban_{kind}_{index}.md"
    prompt = build_file_prompt(
        work_kind=kind,
        index=index,
        course_name=course.name,
        section_num=sesi,
        activity_title=title,
        soal_path=soal_path,
        attachment_dir=lamp_dir,
        lampiran=[p.name for p in saved],
        jawaban_path=jawaban_path,
        format_path=format_path,
        format_note=format_note,
    )
    record = Prefetched(
        course=course,
        section_num=sesi,
        item=Activity(mod_type="custom", id=index, title=title, section=sesi, course_id=course.id),
        kind=kind,
        index=index,
        out_dir=out_dir,
        template=format_path,
    )
    _run_agent(record, key, prompt=prompt, jawaban_path=jawaban_path)
    log("Selesai. 1 item diproses untuk %s (form soal)." % course.name)


# ---------------------------------------------------------------------------
# Diagnostic commands
# ---------------------------------------------------------------------------
def cmd_probe(args):
    """Tampilkan persis apa yang akan dibaca AI dari setiap URL sumber."""
    Config.require()
    session = MoodleSession()
    session.check_login()
    scraper = CourseScraper(session)
    reader = MoodleReader()
    base = ensure_reader()
    log(f"Reader Lokal: {base or '(gagal dinyalakan)'}")
    if not base:
        log("Tidak bisa melanjutkan tanpa Reader.")
        return

    course, jobs = _gather_jobs(
        scraper, int(args.course), sesi_filter=int(args.sesi) if args.sesi else None,
        kind_filter=getattr(args, "kind", None) or "all",
    )
    if course is None:
        log(f"Kursus id {args.course} tidak ditemukan.")
        return
    log(f"\n=== {course.name} · {len(jobs)} item ===")
    discovery = SourceDiscovery(reader, make_url=soalu)
    for course_, section, item, kind in jobs:
        log(f"\n--- [{kind}] {item.title} (sesi {section}) ---")
        source = discovery.discover(item, kind)
        log(f"    ringkasan: {source.summary() or source.note}")
        for link in source.links:
            flag = "OK  " if link.ok else "GAGAL"
            log(f"    [{flag}] {link.role:9s} {link.note:28s} {link.url}")
        primary = source.ok_links[0] if source.ok_links else None
        if primary is None:
            log("    (tidak ada sumber yang bisa dibaca AI)")
            continue
        limit = int(getattr(args, "lines", 60) or 60)
        url = primary.reader_url
        log(f"    -> agent akan webfetch: {url}")
        status, ctype, body = handle_soal(primary.url, primary.role)
        log(f"    <- HTTP {status} · {ctype}")
        preview = body.strip().splitlines()[:limit]
        for line in preview:
            log(f"       | {line}")
        if len(body.strip().splitlines()) > limit:
            log(f"       | ... ({len(body.strip().splitlines()) - limit} baris lagi)")


def cmd_vision_probe(args):
    """Cek apakah model agent `tuton` bisa membaca gambar/PDF.

    Membuat gambar kecil berisi kode acak, lalu tanya agent untuk membacanya.
    Kalau kode yang kembali benar, model punya vision dan kita bisa HENTI
    menjalankan proses transkripsi terpisah (hemat waktu besar per lampiran).
    """
    Config.require()
    import random
    import string

    from PIL import Image, ImageDraw

    token = "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    work = OUTPUT_DIR / ".jobs"
    work.mkdir(parents=True, exist_ok=True)  # `cmd_vision_probe` tidak lewat `require`
    path = work / f"vision_probe_{token}.png"
    img = Image.new("RGB", (600, 200), "white")
    draw = ImageDraw.Draw(img)
    draw.text((40, 80), f"KODE: {token}", fill="black")
    img.save(str(path))
    log(f"Gambar probe: {path}")
    log(f"Kode yang benar: {token}")

    from generator.opencode_runner import _resolve_opencode

    prompt = (
        f"Buka file gambar `{path}` dengan tool read, lalu tulis HANYA kode yang "
        "terlihat di dalamnya, tanpa penjelasan lain."
    )
    cmd = _resolve_opencode() + ["run", "-", "--agent", "tuton", "--title", "vision-probe"]
    model = Config.OPENCODE_MODEL
    if model:
        cmd += ["--model", model]
    import subprocess

    result = subprocess.run(
        cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=Config.TUTON_TIMEOUT,
        cwd=str(Path(__file__).resolve().parent),
    )
    output = (result.stdout or "") + (result.stderr or "")
    log(f"--- output agent ---\n{output.strip()}")
    if token in output:
        _VISION_CACHE["can_read"] = True
        log(
            f"✓ Model BISA melihat gambar. Set OPENCODE_MODEL accordingly atau "
            "biarkan TUTON_TRANSCRIBE=auto memakai file langsung."
        )
    else:
        _VISION_CACHE["can_read"] = False
        log(
            "✗ Model TIDAK bisa melihat gambar. Transkripsi via vision model akan "
            "tetap dipakai (TUTON_TRANSCRIBE=auto/always)."
        )
    path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(prog="tuton", description="Agent tuton UT")
    sub = parser.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="Scrape + kerjakan + buat .doc")
    p_run.add_argument("--course", help="ID mata kuliah (default: semua)")
    p_run.add_argument("--sesi", help="Hanya sesi tertentu")
    p_run.add_argument(
        "--kind", choices=["all", "tugas", "diskusi"], default="all",
        help="Jenis pekerjaan yang diproses",
    )
    p_run.add_argument(
        "--force", action="store_true",
        help="Tulis ulang jawaban item yang sudah selesai. Peta soal dan daftar "
             "pustaka tetap dipakai dari cache.",
    )
    p_run.add_argument(
        "--remap", action="store_true",
        help="Buang cache peta soal dan daftar pustaka, lalu buat ulang. Pakai "
             "hanya kalau soalnya sendiri berubah dan peta hasil lama jadi salah.",
    )
    p_run.add_argument(
        "--jobs", type=int, default=0,
        help="Berapa item dikerjakan bersamaan (default dari TUTON_JOBS)",
    )
    p_run.add_argument(
        "--soal-mode", choices=["url", "file"], default="",
        help="url (default): AI ambil soal dari URL; file: tempel soal.md (lama)",
    )
    p_run.set_defaults(fn=cmd_run)

    p_scrape = sub.add_parser("scrape", help="Lihat kursus/sesi/aktivitas saja")
    p_scrape.add_argument("--course", help="ID mata kuliah")
    p_scrape.set_defaults(fn=cmd_scrape)

    p_solve = sub.add_parser(
        "solve", help="Kerjakan soal custom dari form (teks / file) tanpa scrape otomatis"
    )
    p_solve.add_argument("--course", required=True, type=int)
    p_solve.add_argument("--sesi", required=True, type=int)
    p_solve.add_argument("--kind", required=True, choices=["tugas", "diskusi"])
    p_solve.add_argument("--title", default="")
    p_solve.add_argument("--text", default="")
    p_solve.add_argument("--file", action="append", default=[])
    # Field "Format Jawaban". Keduanya opsional: kosong berarti memakai template
    # standar. `--format` menerima satu berkas .docx contoh yang dipakai
    # sebagai dokumen dasar keluaran; `--format-note` menerima keterangan
    # bebas dari pengguna.
    p_solve.add_argument(
        "--format", default="", help="Berkas .docx contoh format jawaban (opsional)"
    )
    p_solve.add_argument(
        "--format-note", default="", help="Keterangan format jawaban (opsional)"
    )
    p_solve.set_defaults(fn=cmd_solve)

    p_status = sub.add_parser("status", help="Lihat progres")
    p_status.set_defaults(fn=cmd_status)

    p_probe = sub.add_parser(
        "probe", help="Tampilkan URL sumber + isi yang akan dibaca AI (diagnostik)"
    )
    p_probe.add_argument("--course", required=True, type=int)
    p_probe.add_argument("--sesi", default="")
    p_probe.add_argument("--kind", choices=["all", "tugas", "diskusi"], default="all")
    p_probe.add_argument("--lines", type=int, default=60, help="Baris preview per sumber")
    p_probe.set_defaults(fn=cmd_probe)

    p_vision = sub.add_parser(
        "vision-probe", help="Cek apakah model tuton bisa melihat gambar/PDF"
    )
    p_vision.set_defaults(fn=cmd_vision_probe)

    args = parser.parse_args()
    if not args.cmd:
        cmd_run(
            argparse.Namespace(
                course=None, sesi=None, force=False, remap=False, kind="all",
                jobs=0, soal_mode="",
            )
        )
        return
    try:
        args.fn(args)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
