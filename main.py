from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
from pathlib import Path

# Console Windows/cp1252 tidak selalu mendukung karakter UTF-8 (→, ✓, huruf
# beraksen). Paksa stdout/stderr ke UTF-8 supaya cukup `python main.py run`.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

from config import Config, OUTPUT_DIR
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
        all_work.extend((d, "diskusi", sec.number) for d in diskusi)
        all_work.extend((t, "tugas", sec.number) for t in tugas)

    total = len(all_work)
    print(f"  · TOTAL: {total} item")
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


def _custom_index(title: str, kind: str) -> int:
    """Nomor display untuk soal form: ambil angka dari judul (mis. 'Diskusi 2'),
    fallback ke 1 bila tidak ada nomor."""
    m = re.search(r"(?:diskusi|tugas)[.\s-]?(\d+)", title.lower())
    return int(m.group(1)) if m else 1


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

    result = None
    for attempt in (1, 2):
        try:
            print(f"  · {progress_flag}[{kind}] {item_title} → opencode run ...")
            result = run_opencode(prompt)
        except TimeoutError:
            print("  ! opencode timeout, coba ulang...")
            continue
        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "")[-1200:]
            print(f"  ! opencode exit {result.returncode}\n{tail}")
        if jawaban_path.exists() and jawaban_path.stat().st_size > 100:
            break
        print("  ! jawaban belum tertulis, percobaan ulang...")
    else:
        print("  ✗ Gagal menghasilkan jawaban.")
        state.set_item(key, {"status": "failed", "matkul": course.name, "desc": item_title})
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
        "outputs": [str(doc_path), str(jawaban_path)],
    })
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
    if getattr(args, "file", ""):
        upload_path = Path(args.file)
        if upload_path.exists():
            dest = lamp_dir / upload_path.name
            if dest.exists():
                dest = lamp_dir / f"custom_{int(time.time() * 1000)}_{upload_path.name}"
            shutil.move(str(upload_path), str(dest))
            saved.append(dest)

    from moodle.transcribe import process_attachment

    transcribed: list[str] = []
    for p in saved:
        print(f"  · Transkripsi {p.name} ...")
        text = process_attachment(p, lamp_dir)
        if text:
            print(f"    -> {len(text)} karakter")
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
    if args.course:
        _process_course(
            session, scraper, downloader, parser,
            int(args.course), sesi_filter=sesi_filter, force=args.force,
        )
    else:
        for c in scraper.get_courses():
            _process_course(
                session, scraper, downloader, parser,
                c.id, sesi_filter=sesi_filter, force=args.force,
            )


def main():
    parser = argparse.ArgumentParser(prog="tuton", description="Agent tuton UT")
    sub = parser.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="Scrape + kerjakan + buat .doc")
    p_run.add_argument("--course", help="ID mata kuliah (default: semua)")
    p_run.add_argument("--sesi", help="Hanya sesi tertentu")
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
    p_solve.add_argument("--file", default="", help="Path file lampiran soal yang di-upload (opsional)")
    p_solve.set_defaults(fn=cmd_solve)

    p_status = sub.add_parser("status", help="Lihat progres")
    p_status.set_defaults(fn=cmd_status)

    args = parser.parse_args()
    if not args.cmd:
        # Tanpa sub-perintah = full flow (run): kerjakan yang belum selesai,
        # item yang sudah selesai otomatis dilewati (state.json).
        cmd_run(argparse.Namespace(course=None, sesi=None, force=False))
        return
    try:
        args.fn(args)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()