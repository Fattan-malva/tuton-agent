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
import re
import shutil
import sys
import threading
import time
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

# Console Windows/cp1252 tidak selalu mendukung karakter UTF-8 (→, ✓, huruf
# beraksen). Paksa stdout/stderr ke UTF-8 supaya cukup `python main.py run`.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

from config import Config, OUTPUT_DIR, now_stamp
from generator import models, state
from generator.docx import save_doc
from generator.opencode_runner import run_opencode
from generator.prompt import (
    build_petak_prompt,
    build_prompt,
    build_referensi_prompt,
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
    # Dokumen dasar untuk .docx. `None` berarti pakai template standar.
    # Form Soal mengisinya dengan berkas "Format Jawaban" milik pengguna bila
    # field itu diisi, sehingga hasil dokumennya mengikuti tata letak yang
    # benar-benar dipakai, bukan template bawaan.
    template: Path | None = None


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
# ditemukan. Kadang menu Diskusi memuat soal tambahan, kadang butir tertentu
# bergantung pada lampiran atau halaman materi lain, dan kadang rubrik ada di
# halaman seksi sementara butirnya ada di halaman aktivitas (atau sebaliknya).
#
# Yang dulunya terjadi: agen `tuton` membuka beberapa halaman untuk tiap item,
# dan tiap item membayar harga penuh untuk halaman yang sama. Satu sesi berisi
# lima item berarti lima kali pembacaan halaman yang isinya identik.
#
# Sekarang: satu proses `pemetak-soal` membaca halaman-halaman itu SEKALI per
# sesi dan menulis peta ringkas. Lima item berikutnya membaca peta yang sama,
# yang isinya jauh lebih kecil karena sudah disaring: hanya butir soal, syarat
# format, rubrik, dan lampiran yang relevan.
# ---------------------------------------------------------------------------
_PETAK_AGENT = "pemetak-soal"

# Peta yang terlalu pendek hampir pasti gagal (agen hanya menulis pengumuman
# lalu berhenti), jadi dipakai sebagai ambang cache. 200 karakter setara satu
# blok butir soal plus syarat format.
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
) -> bool:
    """Jalankan satu agen pembantu dan tunggu berkas yang dijanjikannya.

    Berbeda dengan agen penulis, agen pembantu tidak diperiksa dengan
    `answer_quality_issues`: isinya bukan jawaban melainkan artefak. Yang
    diperiksa hanya benar-benar tertulis dan cukup berisi. Mengembalikan
    `False` membuat pemanggil memakai jalur cadangan.
    """
    path.unlink(missing_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)

    attempts = max(1, Config.TUTON_HELPER_RETRIES)
    for attempt in range(1, attempts + 1):
        try:
            result = run_opencode(
                prompt,
                agent=agent,
                model=model or None,
                timeout=Config.TUTON_TIMEOUT_HELPER,
            )
        except TimeoutError:
            log(f"  ! {label}: timeout (percobaan {attempt}/{attempts})")
            continue
        except Exception as exc:  # noqa: BLE001
            log(f"  ! {label}: {type(exc).__name__}: {exc}")
            continue

        if _artifact_ok(path, min_chars):
            return True
        output = ((result.stdout or "") + (result.stderr or "")).strip()
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

    log(
        f"  · memetakan soal {len(pending)} sesi dengan model kecil "
        "(mencari sekaligus memahami butir, rubrik, dan lampiran)...",
        prefix="  ",
    )
    model = helper_model()
    for sec, path in pending:
        started = time.monotonic()
        try:
            prompt = build_petak_prompt(
                course_name=course.name,
                section_num=sec.number,
                section_title=sec.title,
                section_url=(
                    f"{Config.base_url()}/course/view.php"
                    f"?id={course.id}&section={sec.number}"
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
            )
        except Exception as exc:  # noqa: BLE001
            log(f"  ! peta sesi {sec.number} gagal: {type(exc).__name__}: {exc}")
            continue
        if ok:
            done[sec.number] = path
            log(
                f"  ✓ peta sesi {sec.number} "
                f"({time.monotonic() - started:.1f}s, {path.stat().st_size} byte)",
                prefix="  ",
            )
        else:
            log(
                f"  · peta sesi {sec.number} tidak terbentuk. Agen penulis akan "
                "membaca halaman sumber sendiri: lebih mahal, tapi tetap jalan.",
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


def _pustaka_stage(
    records: list[Prefetched],
    peta_by_section: dict[int, Path],
    *,
    force: bool,
) -> dict[int, Path]:
    """Cari referensi per item, sekali saja, memakai model pembantu.

    Dijalankan setelah `_petak_stage` selesai, bukan paralel dengannya: referensi
    yang baik bergantung pada Understanding butir soalnya, dan dua tahap yang
    keduanya memanggil model secara bersamaan hanya memperpanjang waktu tunggu
    tanpa menambah hasil per menit.
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

    model = helper_model()
    log(
        f"  · mencari referensi {len(pending)} item (maksimal "
        f"{Config.TUTON_MAX_PUSTAKA} per item, tanpa riset di model utama)...",
        prefix="  ",
    )
    for record in pending:
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
            )
            ok = _run_helper(
                prompt,
                path=path,
                agent=_PUSTAKA_AGENT,
                model=model,
                label=f"{record.kind} {record.index}",
                min_chars=_MIN_PUSTAKA_CHARS,
            )
        except Exception as exc:  # noqa: BLE001
            log(f"  ! referensi {record.kind} {record.index} gagal: {exc}")
            continue
        if ok:
            out[id(record)] = path
    return out


def _needs_transcription(record: Prefetched) -> bool:
    """Apakah lampiran item ini perlu ditranskripsi?

    Ya, begitu ada lampiran: di UT PDF/gambar sering berisi soal
    yang tidak pernah ditulis di halaman. Melewatkannya berarti AI menjawab dari
    instruksi saja tanpa butir soalnya -- itu penyebab paling umum jawaban
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
    if not record.transcripts:
        return None
    parts: list[str] = []
    for name, text in record.transcripts.items():
        parts.append(f"## {name}\n\n{text}")
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

    workers = max(1, min(Config.TUTON_TRANSCRIBE_WORKERS, len(todo)))
    log(f"  · transkripsi lampiran {len(todo)} item ({workers} worker)...")

    def work(record: Prefetched) -> None:
        lamp_dir = (record.out_dir or Path(".")) / "lampiran"
        record.transcripts = transcribe_many(record.attachments, lamp_dir)
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
                    f"{len(record.transcripts)} lampiran terbaca "
                    f"({sum(len(v) for v in record.transcripts.values())} karakter)"
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


def answer_quality_issues(text: str) -> list[str]:
    """Deteksi jawaban yang korup/tidak lengkap sebelum masuk ke docx.

    Mengembalikan daftar masalah (kosong = jawaban lolos). Ini pagar terhadap
    dua kegagalan yang pernah terjadi: agent menulis jawaban berisi fragmen
    karakter acak setelah beberapa kali edit, dan jawaban tanpa Daftar Pustaka
    padahal sitasi adalah bagian wajib.
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
        refs = [
            ln for ln in tail.splitlines()
            if re.match(r"\s*(?:\[?\d+\]?[-.)]?|\*)\s+\S", ln)
            and not re.match(r"\s*#+\s", ln)
        ]
        if not refs:
            issues.append("Daftar Pustaka kosong (tidak ada entri)")
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

    jawab = re.search(r"^#+\s*jawab", body, re.IGNORECASE | re.MULTILINE)
    isi = body[jawab.end():] if jawab else body
    if len(isi.strip()) < 120:
        issues.append("isi jawaban terlalu pendek (<120 karakter)")
    return issues


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

    retries = max(1, Config.TUTON_RETRIES)
    rate_limited = False
    result = None
    issues: list[str] = []
    for attempt in range(1, retries + 1):
        try:
            log(f"→ opencode run ... (percobaan {attempt}/{retries})")
            result = run_opencode(
                prompt,
                agent="tuton",
                model=writer_model() or None,
                timeout=Config.TUTON_TIMEOUT,
            )
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
            try:
                existing = jawaban_path.read_text(encoding="utf-8", errors="replace")
                jawaban_path.write_text(
                    f"> PERHATIAN: versi sebelumnya bermasalah ({'; '.join(issues)}). "
                    "Tulis ulang seluruh jawaban dari awal; jangan melakukan edit "
                    "parsial pada teks yang sudah rusak.\n\n" + existing,
                    encoding="utf-8",
                )
            except OSError:
                pass
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
        "kind_label": "Diskusi" if record.kind == "diskusi" else "Tugas",
        "display_index": record.index,
        "file_base": (
            f"{record.course.folder_name}_"
            f"{'Diskusi' if record.kind == 'diskusi' else 'Tugas'}{record.index}"
        ),
    }
    try:
        _, doc_path = save_doc(
            jawaban_md=jawaban_md,
            soal_text=(source.soal_text if source else ""),
            meta=meta,
            out_dir=out_dir,
            template=record.template,
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
    lampiran = [p.name for p in sorted(lamp_dir.glob("*")) if p.is_file()] if lamp_dir.exists() else []
    soal_urls = source.reader_urls()
    if not soal_urls:
        reason = "URL sumber tidak bisa disajikan ke agent"
        log(f"⛔ dilewati: {reason}")
        _fail_item(record, key, "soal_tidak_ditemukan")
        raise SoalNotFound(reason)

    jawaban_path = record.out_dir / f"jawaban_{record.kind}_{record.index}.md"
    attachments = [str(p) for p in record.attachments]
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
    # bergantung: peta memberi butir, transkrip memberi isi lampiran, daftar
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
        futures = [
            pool.submit(_safe_process, record, force=force, mode=mode)
            for record in records
        ]
        for future in as_completed(futures):
            try:
                if future.result():
                    worked += 1
                else:
                    skipped += 1
            except Exception:  # noqa: BLE001 - _safe_process sudah menangani
                skipped += 1
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
    except SoalNotFound as exc:
        log(f"dilewati: {exc}")
    except Exception as exc:  # noqa: BLE001 - satu item tidak boleh mematikan batch
        log(f"error tak terduga: {type(exc).__name__}: {exc}")
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
