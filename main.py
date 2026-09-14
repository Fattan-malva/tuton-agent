from __future__ import annotations

import argparse
import re
import sys
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
from moodle.parser import QuestionParser
from moodle.scraper import Activity, CourseScraper

SEC_TUGAS_INDEX = {3: 1, 5: 2, 7: 3}


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
    worked = 0
    for sec in sections:
        if sesi_filter is not None and sec.number != sesi_filter:
            continue
        diskusi, tugas, _ = scraper.split_assignable(sec.activities)
        work = [
            *[(d, "diskusi") for d in diskusi],
            *[(t, "tugas") for t in tugas],
        ]
        for item, kind in work:
            worked += _process_item(
                session, scraper, downloader, parser,
                course, sec.number, item, kind, force=force,
            )
    print(f"\nSelesai. {worked} item diproses untuk {course.name}.")


def _process_item(
    session, scraper, downloader, parser,
    course, section_num, item, kind, *, force: bool,
) -> int:
    k = state.key(course.id, item.mod_type, item.id)
    if not force and state.is_done(k):
        print(f"  · {item.title} → sudah dikerjakan, dilewati (--force untuk ulang).")
        return 0

    index = _display_index(item, kind, section_num)
    out_dir = OUTPUT_DIR / course.folder_name / f"sesi{section_num}"
    lamp_dir = out_dir / "lampiran"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"  · [{kind}] {item.title} → {out_dir.relative_to(OUTPUT_DIR)}")

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
    from moodle.transcribe import process_attachment

    for p in saved:
        print(f"  · Transkripsi {p.name} ...")
        text = process_attachment(p, lamp_dir)
        if text:
            print(f"    -> {len(text)} karakter")
        soal_md_lines.append("")
        soal_md_lines.append(f"## Isi lampiran: {p.name} (transkripsi)")
        soal_md_lines.append(
            text or "(tidak bisa dibaca otomatis - perlu dicek manual)"
        )
    soal_path = out_dir / "soal.md"
    soal_path.write_text("\n".join(soal_md_lines), encoding="utf-8")

    # 2) Panggil opencode
    jawaban_path = out_dir / f"jawaban_{kind}_{index}.md"
    prompt = build_prompt(
        work_kind=kind,
        index=index,
        course_name=course.name,
        section_num=section_num,
        activity_title=item.title,
        soal_path=soal_path,
        attachment_dir=lamp_dir if saved else lamp_dir,
        jawaban_path=jawaban_path,
    )

    for attempt in (1, 2):
        try:
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
        state.set_item(k, {"status": "failed", "matkul": course.name, "desc": item.title})
        return 0

    if result.returncode == 0:
        ok = (result.stdout or "").strip().splitlines()
        if ok:
            print(f"  {ok[-1][:120]}")

    # 3) Generate .docx (equation OMML asli)
    jawaban_md = jawaban_path.read_text(encoding="utf-8")
    soal_for_docx = soal_path.read_text(encoding="utf-8")
    meta = {
        "nama": Config.NAMA,
        "nim": Config.NIM,
        "prodi": Config.PRODI,
        "matkul": course.name,
        "kind_label": "Diskusi" if kind == "diskusi" else "Tugas",
        "display_index": index,
        "file_base": f"{kind}{index}",
    }
    _, doc_path = save_doc(
        jawaban_md=jawaban_md,
        soal_text=soal_for_docx,
        meta=meta,
        out_dir=out_dir,
    )
    print(f"  ✓ {doc_path.name} siap.")

    # 4) State
    state.set_item(k, {
        "status": "done",
        "matkul": course.name,
        "sesi": section_num,
        "kind": kind,
        "index": index,
        "desc": item.title,
        "outputs": [str(doc_path), str(jawaban_path)],
    })
    return 1


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