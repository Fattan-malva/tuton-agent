from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
from pathlib import Path

# Character kontrol yang tidak sah di XML 1.0 (bikin docx gagal dibuat).
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Skrip non-Latin (CJK/Hangul/Kana/Cyrillic/Arab/Hebrew) tidak pernah muncul di
# jawaban akademik berbahasa Indonesia. Kehadirannya jadi sinyal teks korup —
# contoh nyata: jawaban Basis Data sempat memuat karakter CJK di tengah kata
# "Entitas" dan kata cacat seperti "bluesis".
_FOREIGN_SCRIPT_RE = re.compile(
    r"[\u2e80-\u9fff\uac00-\ud7af\u3040-\u30ff\u0400-\u04ff\u0600-\u06ff"
    r"\u0590-\u05ff]"
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
from generator import state
from generator.docx import save_doc
from generator.opencode_runner import run_opencode
from generator.prompt import build_prompt
from moodle.auth import MoodleSession
from moodle.downloader import AttachmentDownloader
from moodle.parser import QuestionParser, question_body
from moodle.scraper import Activity, CourseScraper

SEC_TUGAS_INDEX = {3: 1, 5: 2, 7: 3}


class SoalNotFound(RuntimeError):
    """Soal tidak ditemukan di mana pun (tab seksi di course maupun forum)."""


def _print_courses(scraper: CourseScraper):
    courses = scraper.get_courses()
    print("Daftar mata kuliah:")
    for c in courses:
        print(f"  [{c.id}] {c.name}")
    return courses


def _display_index(item: Activity, kind: str, section_num: int) -> int:
    low = item.title.lower()
    m = re.search(r"(?:diskusi|tugas)[.\s-]?(\d+)", low)
    if m:
        return int(m.group(1))
    if kind == "tugas":
        return SEC_TUGAS_INDEX.get(section_num, section_num)
    return section_num


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


def _process_course(
    session: MoodleSession,
    scraper: CourseScraper,
    downloader: AttachmentDownloader,
    parser: QuestionParser,
    course_id: int,
    *,
    sesi_filter: int | None,
    force: bool,
    kind_filter: str = "all",
):
    courses = scraper.get_courses()
    course = next((c for c in courses if c.id == course_id), None)
    if not course:
        print(f"Kursus id {course_id} tidak ditemukan.")
        return

    print(f"\n=== {course.name} ===")
    sections = scraper.get_available_sections(course_id)
    all_work: list[tuple[Activity, str, int]] = []
    for sec in sections:
        if sesi_filter is not None and sec.number != sesi_filter:
            continue
        diskusi, tugas, _ = scraper.split_assignable(sec.activities)
        if kind_filter in ("all", "diskusi"):
            all_work.extend((d, "diskusi", sec.number) for d in diskusi)
        if kind_filter in ("all", "tugas"):
            all_work.extend((t, "tugas", sec.number) for t in tugas)

    total = len(all_work)
    if total == 0:
        label = {"all": "tugas dan diskusi", "tugas": "tugas", "diskusi": "diskusi"}[
            kind_filter
        ]
        print(
            f"  · TOTAL: 0 item (filter: {label}"
            + (f", sesi {sesi_filter}" if sesi_filter is not None else "")
            + ")"
        )
        return
    print(f"  · TOTAL: {total} item (filter: {kind_filter})")
    worked = 0
    blocked_section: int | None = None
    for pos, (item, kind, section_num) in enumerate(all_work, 1):
        # item per-sesi tergabung di all_work, jadi begitu satu soal tak
        # ditemukan, sesi itu dilewati utuh lalu lanjut ke sesi/matkul lain.
        if blocked_section == section_num:
            continue
        try:
            worked += _process_item(
                session, scraper, downloader, parser,
                course, section_num, item, kind,
                pos=pos, total=total, force=force,
            )
        except SoalNotFound as exc:
            print(f"\n  ⛔ Sesi {section_num} dilewati: {exc}")
            print("  Sisa item sesi ini tidak dikerjakan; lanjut sesi/matkul berikut.")
            blocked_section = section_num
    print(f"\nSelesai. {worked} item diproses untuk {course.name}.")


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

    jawab = re.search(r"^#+\s*jawab", body, re.IGNORECASE | re.MULTILINE)
    isi = body[jawab.end():] if jawab else body
    if len(isi.strip()) < 120:
        issues.append("isi jawaban terlalu pendek (<120 karakter)")
    return issues


def _finish_work(
    *,
    course,
    section_num: int,
    item_title: str,
    kind: str,
    index: int,
    soal_path: Path,
    out_dir: Path,
    lamp_dir: Path,
    soal_text: str,
    key: str,
    progress_flag: str = "",
) -> int:
    """Lanjutan setelah soal.md siap: opencode → jawaban.md → docx → state."""
    jawaban_path = out_dir / f"jawaban_{kind}_{index}.md"
    started_at = now_stamp()
    started_mono = time.monotonic()
    prompt = build_prompt(
        work_kind=kind,
        index=index,
        course_name=course.name,
        section_num=section_num,
        activity_title=item_title,
        soal_path=soal_path,
        attachment_dir=lamp_dir,
        jawaban_path=jawaban_path,
    )

    # Jawaban lama dari percobaan sebelumnya dihapus supaya check "sudah
    # ditulis" di bawah tidak meniru file basi.
    jawaban_path.unlink(missing_ok=True)

    result = None
    issues: list[str] = []
    for attempt in (1, 2, 3):
        try:
            print(f"  · {progress_flag}[{kind}] {item_title} → opencode run ...")
            result = run_opencode(prompt)
        except TimeoutError:
            print("  ! opencode timeout, coba ulang...")
            continue
        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "")[-1200:]
            print(f"  ! opencode exit {result.returncode}\n{tail}")
        if not (jawaban_path.exists() and jawaban_path.stat().st_size > 100):
            print("  ! jawaban belum tertulis, percobaan ulang...")
            continue

        issues = answer_quality_issues(
            jawaban_path.read_text(encoding="utf-8", errors="replace")
        )
        if not issues:
            break
        print(f"  ! kualitas jawaban belum memenuhi ({'; '.join(issues)})")
        print("  ! percobaan ulang dengan instruksi perbaikan...")
        if attempt < 3:
            # Beri tahu agent apa yang salah supaya tidak mengulang kesalahan.
            try:
                jawaban_path.write_text(
                f"> PERHATIAN: versi sebelumnya bermasalah ({'; '.join(issues)}). "
                "Tulis ulang seluruh jawaban dari awal; jangan melakukan edit "
                "parsial pada teks yang sudah rusak.\n\n"
                    + jawaban_path.read_text(encoding="utf-8", errors="replace"),
                    encoding="utf-8",
                )
            except OSError:
                pass
            jawaban_path.unlink(missing_ok=True)
    else:
        print(f"  ✗ Gagal menghasilkan jawaban yang layak: {'; '.join(issues)}")
        state.set_item(key, {
            "status": "failed",
            "matkul": course.name,
            "sesi": section_num,
            "kind": kind,
            "index": index,
            "desc": item_title,
            "created_at": started_at,
            "finished_at": now_stamp(),
            "reason": "; ".join(issues) or "jawaban tidak lengkap",
        })
        return 0

    if result.returncode == 0:
        ok = (result.stdout or "").strip().splitlines()
        if ok:
            print(f"  {ok[-1][:120]}")

    # 3) Generate .docx (equation OMML asli)
    print(f"  · {progress_flag}[{kind}] {item_title} → membuat docx ...")
    jawaban_md = jawaban_path.read_text(encoding="utf-8")
    # Jangan baca ulang soal.md dari disk: agent opencode bisa menghapus/memindahnya
    # saat bekerja. Pakai konten yang sudah kita susun di memori.
    finished_at = now_stamp()
    meta = {
        "nama": Config.NAMA,
        "nim": Config.NIM,
        "prodi": Config.PRODI,
        "matkul": course.name,
        "kind_label": "Diskusi" if kind == "diskusi" else "Tugas",
        "display_index": index,
        "file_base": f"{course.folder_name}_{'Diskusi' if kind == 'diskusi' else 'Tugas'}{index}",
    }
    _, doc_path = save_doc(
        jawaban_md=jawaban_md,
        soal_text=soal_text,
        meta=meta,
        out_dir=out_dir,
    )
    print(f"  ✓ {doc_path.name} siap.")

    # 4) State
    state.set_item(key, {
        "status": "done",
        "matkul": course.name,
        "sesi": section_num,
        "kind": kind,
        "index": index,
        "desc": item_title,
        "created_at": started_at,
        "finished_at": finished_at,
        "duration_sec": round(time.monotonic() - started_mono, 1),
        "outputs": [str(doc_path), str(jawaban_path)],
    })
    print(f"  ⏱ {started_at} → {finished_at}")
    return 1


def _process_item(
    session, scraper, downloader, parser,
    course, section_num, item, kind, *, force: bool,
    pos: int = 0, total: int = 0,
) -> int:
    k = state.key(course.id, item.mod_type, item.id)
    if not force and state.is_done(k):
        print(f"  · {item.title} → sudah dikerjakan, dilewati (--force untuk ulang).")
        return 0

    index = _display_index(item, kind, section_num)
    out_dir = OUTPUT_DIR / course.folder_name / f"sesi{section_num}"
    lamp_dir = out_dir / "lampiran"
    out_dir.mkdir(parents=True, exist_ok=True)

    progress_flag = f"[{pos}/{total}] " if total else ""
    print(f"  · {progress_flag}[{kind}] {item.title} → {out_dir.relative_to(OUTPUT_DIR)}")

    # 1) Soal + lampiran
    parsed = parser.parse(item)
    soal_md_lines = [
        f"# {parsed.title}",
        "",
        parsed.question or "(soal kosong / perlu dibaca dari lampiran)",
    ]
    saved = downloader.download_all(parsed.attachment_urls, lamp_dir)
    if saved:
        soal_md_lines.append("")
        soal_md_lines.append("## Lampiran")
        soal_md_lines.extend(f"- {p.name}" for p in saved)

    # Transkripsi isi lampiran (gambar/PDF via model vision -> agent transcriber;
    # Excel/docx via ekstraksi Python). teks masuk ke soal.md agar model menjawab
    # cukup dari satu file teks.
    print(f"  · {progress_flag}[{kind}] {item.title} → transkripsi ...")
    from moodle.transcribe import process_attachment

    transcribed = []
    for p in saved:
        print(f"  · Transkripsi {p.name} ...")
        text = process_attachment(p, lamp_dir)
        if text:
            print(f"    -> {len(text)} karakter")
        transcribed.append(text or "")
        soal_md_lines.append("")
        soal_md_lines.append(f"## Isi lampiran: {p.name} (transkripsi)")
        soal_md_lines.append(
            text or "(tidak bisa dibaca otomatis - perlu dicek manual)"
        )
    soal_path = out_dir / "soal.md"

    # 1b) Verifikasi soal benar-benar ada. Jika kosong di semua sumber
    #     (tab seksi course/view.php#tabs-tree-start, deskripsi forum, post
    #     pembuka), BERHENTI — jangan mengarang jawaban.
    _useful_transcripts = [
        t for t in transcribed
        if t.strip() and "tidak bisa dibaca otomatis" not in t[:80]
    ]
    _has_soal = bool(
        question_body(parsed.question)
        or _useful_transcripts
    )
    if not _has_soal:
        soal_path.write_text(
            "\n".join(soal_md_lines) + "\n\nTIDAK ADA SOAL DITEMUKAN. "
            "Proses dihentikan, tidak ada jawaban yang dibuat.\n",
            encoding="utf-8",
        )
        state.set_item(k, {
            "status": "failed",
            "matkul": course.name,
            "sesi": section_num,
            "desc": item.title,
            "reason": "soal_tidak_ditemukan",
        })
        raise SoalNotFound(
            f"Soal untuk '{item.title}' tidak ditemukan di halaman course "
            f"(#tabs-tree-start) maupun forum. Proses dihentikan."
        )
    soal_path.write_text("\n".join(soal_md_lines), encoding="utf-8")

    # 2) opencode → docx → state
    return _finish_work(
        course=course,
        section_num=section_num,
        item_title=item.title,
        kind=kind,
        index=index,
        soal_path=soal_path,
        out_dir=out_dir,
        lamp_dir=lamp_dir,
        soal_text="\n".join(soal_md_lines),
        key=k,
        progress_flag=progress_flag,
    )


def cmd_solve(args):
    """Kerjakan soal dari form (bukan scrape): teks soal manual atau file upload."""
    Config.require()
    session = MoodleSession()
    session.check_login()
    scraper = CourseScraper(session)

    courses = scraper.get_courses()
    course = next((c for c in courses if c.id == args.course), None)
    if not course:
        print(f"Kursus id {args.course} tidak ditemukan.")
        return

    kind = args.kind
    sesi = args.sesi
    title = (args.title or f"{kind} {sesi}").strip()
    index = _custom_index(title, kind)

    out_dir = OUTPUT_DIR / course.folder_name / f"sesi{sesi}"
    lamp_dir = out_dir / "lampiran"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Wajib: file upload dipindahkan ke lampiran. Tanpa mkdir, shutil.move gagal
    # dengan FileNotFoundError sehingga tidak ada lampiran yang bisa ditranskripsi.
    lamp_dir.mkdir(parents=True, exist_ok=True)

    progress_flag = "[1/1] "
    print(f"\n=== {course.name} (form soal) ===")
    print(f"  · {progress_flag}[{kind}] {title} → {out_dir.relative_to(OUTPUT_DIR)}")

    soal_md_lines = [f"# {title}", ""]
    custom_body: list[str] = []

    if getattr(args, "text", ""):
        text_path = Path(args.text)
        if text_path.exists():
            body = text_path.read_text(encoding="utf-8", errors="replace").strip()
            if body:
                custom_body.append(body)
                soal_md_lines.append(body)
            text_path.unlink(missing_ok=True)

    saved: list[Path] = []
    for raw_file in _as_list(getattr(args, "file", "")):
        upload_path = Path(raw_file)
        if not upload_path.exists():
            print(f"  ! file lampiran tidak ditemukan: {upload_path}")
            continue
        dest = lamp_dir / upload_path.name
        if dest.exists() and not dest.samefile(upload_path):
            dest = lamp_dir / f"custom_{int(time.time() * 1000)}_{upload_path.name}"
        try:
            shutil.move(str(upload_path), str(dest))
        except OSError as exc:
            print(f"  ! gagal menyimpan lampiran {upload_path.name}: {exc}")
            continue
        saved.append(dest)
        print(f"  · Lampiran disimpan: {dest.name}")

    from moodle.transcribe import process_attachment

    transcribed: list[str] = []
    for p in saved:
        print(f"  · Transkripsi {p.name} ...")
        text = process_attachment(p, lamp_dir)
        if text.strip():
            print(f"    -> {len(text)} karakter")
        else:
            print(
                f"    ! GAGAL membaca {p.name}. Format mungkin tidak didukung "
                f"atau isinya kosong. Unggah PDF/gambar/DOCX/XLSX/PPTX, atau "
                f"tulis soal langsung di kolom teks."
            )
        transcribed.append(text or "")
        soal_md_lines.append("")
        soal_md_lines.append(f"## Isi lampiran: {p.name} (transkripsi)")
        soal_md_lines.append(text or "(tidak bisa dibaca otomatis - perlu dicek manual)")

    _useful = [
        t for t in transcribed
        if t.strip() and "tidak bisa dibaca otomatis" not in t[:80]
    ]
    key = f"custom:{course.id}:{kind}:{sesi}:{index}"
    soal_path = out_dir / "soal.md"
    if not custom_body and not _useful:
        soal_path.write_text(
            "\n".join(soal_md_lines) + "\n\nTIDAK ADA SOAL DITEMUKAN. "
            "Proses dihentikan, tidak ada jawaban yang dibuat.\n",
            encoding="utf-8",
        )
        state.set_item(key, {
            "status": "failed",
            "matkul": course.name,
            "sesi": sesi,
            "kind": kind,
            "index": index,
            "desc": title,
            "reason": "soal_tidak_ditemukan",
        })
        print(f"  ⛔ Soal kosong untuk '{title}'. Proses dihentikan.")
        return

    soal_path.write_text("\n".join(soal_md_lines), encoding="utf-8")

    _finish_work(
        course=course,
        section_num=sesi,
        item_title=title,
        kind=kind,
        index=index,
        soal_path=soal_path,
        out_dir=out_dir,
        lamp_dir=lamp_dir,
        soal_text="\n".join(soal_md_lines),
        key=key,
        progress_flag=progress_flag,
    )
    print(f"Selesai. 1 item diproses untuk {course.name} (form soal).")


def cmd_run(args):
    Config.require()
    session = MoodleSession()
    session.check_login()
    scraper = CourseScraper(session)
    downloader = AttachmentDownloader(session)
    parser = QuestionParser(session)

    sesi_filter = int(args.sesi) if args.sesi else None
    kind_filter = getattr(args, "kind", None) or "all"
    if args.course:
        _process_course(
            session, scraper, downloader, parser,
            int(args.course), sesi_filter=sesi_filter, force=args.force,
            kind_filter=kind_filter,
        )
    else:
        for c in scraper.get_courses():
            _process_course(
                session, scraper, downloader, parser,
                c.id, sesi_filter=sesi_filter, force=args.force,
                kind_filter=kind_filter,
            )


def main():
    parser = argparse.ArgumentParser(prog="tuton", description="Agent tuton UT")
    sub = parser.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="Scrape + kerjakan + buat .doc")
    p_run.add_argument("--course", help="ID mata kuliah (default: semua)")
    p_run.add_argument("--sesi", help="Hanya sesi tertentu")
    p_run.add_argument(
        "--kind",
        choices=["all", "tugas", "diskusi"],
        default="all",
        help="Jenis pekerjaan yang diproses: all (default), tugas, atau diskusi",
    )
    p_run.add_argument("--force", action="store_true", help="Ulangi meski sudah selesai")
    p_run.set_defaults(fn=cmd_run)

    p_scrape = sub.add_parser("scrape", help="Lihat kursus/sesi/aktivitas saja")
    p_scrape.add_argument("--course", help="ID mata kuliah")
    p_scrape.set_defaults(fn=cmd_scrape)

    p_solve = sub.add_parser(
        "solve",
        help="Kerjakan soal custom dari form (teks / file) tanpa scrape otomatis",
    )
    p_solve.add_argument("--course", required=True, type=int, help="ID mata kuliah")
    p_solve.add_argument("--sesi", required=True, type=int, help="Nomor sesi")
    p_solve.add_argument("--kind", required=True, choices=["tugas", "diskusi"], help="Jenis pekerjaan")
    p_solve.add_argument("--title", default="", help="Judul aktivitas (contoh: 'Diskusi 1')")
    p_solve.add_argument("--text", default="", help="Path file teks berisi soal (opsional bila --file ada)")
    p_solve.add_argument(
        "--file",
        action="append",
        default=[],
        help="Path file lampiran yang di-upload; boleh diulang untuk beberapa file",
    )
    p_solve.set_defaults(fn=cmd_solve)

    p_status = sub.add_parser("status", help="Lihat progres")
    p_status.set_defaults(fn=cmd_status)

    args = parser.parse_args()
    if not args.cmd:
        # Tanpa sub-perintah = full flow (run): kerjakan yang belum selesai,
        # item yang sudah selesai otomatis dilewati (state.json).
        cmd_run(argparse.Namespace(course=None, sesi=None, force=False, kind="all"))
        return
    try:
        args.fn(args)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()