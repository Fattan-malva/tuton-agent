"""Test integrasi end-to-end tanpa Moodle sungguhan.

Alasannya: semua fase baru (Reader, discovery, transkripsi otomatis, prompt
URL-only, docx, state) saling BERGANTUNG. Uji satu per satu tidak cukup -- yang
perlu dibuktikan adalah rantainya tersambung dari URL sampai file .docx.

Cara kerjanya:
  1. Server HTTP lokal menyajikan halaman Moodle tiruan (fixture).
  2. Config diarahkan ke server itu, sehingga guard SSRF Reader tetap diuji
     karena host yang diizinkan memang berubah.
  3. `run_opencode` di-stub: menulis jawaban valid dan MENYIMPAN prompt-nya,
     sehingga kita bisa memeriksa apa yang sebenarnya diterima AI.
  4. `main.cmd_run` dijalankan sungguhan, lalu semua output diperiksa.

Tidak ada panggilan jaringan keluar dan tidak ada biaya model.
"""

from __future__ import annotations

import json
import shutil
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

PASS: list[str] = []
FAIL: list[tuple[str, str]] = []
PROMPTS: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append((name, detail))
        print(f"  FAIL  {name}  {detail}")


# ---------------------------------------------------------------------------
# Fixture: PDF berteks layer (dibuat pymupdf, bukan file biner statis)
# ---------------------------------------------------------------------------
def _make_pdf(path: Path) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (60, 100),
        "Tugas Praktikum 1 - Basis Data",
        fontsize=16,
    )
    page.insert_text(
        (60, 140),
        "1. Jelaskan perbedaan model relasi 1NF, 2NF, dan 3NF.",
        fontsize=11,
    )
    page.insert_text(
        (60, 165),
        "2. Buat rancangan database untuk sistem informasi absensi mahasiswa.",
        fontsize=11,
    )
    doc.save(str(path))
    doc.close()


# ---------------------------------------------------------------------------
# Fixture: server Moodle tiruan
# ---------------------------------------------------------------------------
class MockMoodle(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    base = ""

    def log_message(self, *_args):  # noqa: D102
        return

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, body: str, status: int = 200) -> None:
        self._send(status, body.encode("utf-8"), "text/html; charset=utf-8")

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        query = urlparse(self.path).query
        b = MockMoodle.base

        if path == "/my/courses.php":
            return self._html(
                f'<html><body><nav class="navbar"><a href="/my/">My courses</a></nav>'
                f'<div class="mycourses"><a href="{b}/course/view.php?id=1">Basis Data 64</a></div>'
                f"</body></html>"
            )

        if path == "/course/view.php" and "section=1" in query:
            return self._html(f"""
            <html><head><title>Basis Data</title></head><body class="sidebar-one header-light">
            <nav class="main-navigation"><a href="/">Home</a></nav>
            <div id="page"><div id="region-main" class="content-col">
              <ol class="breadcrumb"><li class="breadcrumb-item">Basis Data 64</li></ol>
              <h1>AKTIVITAS BELAJAR 2</h1>
              <div class="summarytext"><p>Silakan kerjakan aktivitas belajar minggu ini
              dengan teliti. Values are 3NF and 2NF.</p></div>
              <div id="module-11" class="activity"><div class="activity-altcontent">
                <h3>Forum Diskusi.1</h3>
                <a href="{b}/mod/forum/view.php?id=11">Buka diskusi</a>
              </div></div>
              <div id="module-22" class="activity"><div class="activity-altcontent">
                <h3>Tugas.1</h3>
                <a href="{b}/mod/assign/view.php?id=22">Buka tugas</a>
              </div></div>
            </div></div>
            <footer class="footer-container">Copyright UT</footer>
            </body></html>
            """)

        if path == "/course/view.php":
            # `&amp;` wajib, bukan `&` mentah: `&section` dibaca parser HTML
            # sebagai entitas `&sect` (tanda paragraf), sehingga href-nya
            # menjadi `id=1§ion=1` dan selector `a[href*='section=']` tidak
            # pernah cocok -- halaman nav jadi tidak menghasilkan section
            # sama sekali.
            return self._html(
                f'<html><body><div id="region-main">'
                f'<a href="{b}/course/view.php?id=1&amp;section=1">'
                "AKTIVITAS BELAJAR 2</a></div></body></html>"
            )

        if path == "/mod/forum/view.php":
            return self._html(f"""
            <html><head><title>Forum Diskusi.1</title></head>
            <body class="sidebar-one">
            <div id="page"><div id="region-main" class="content-col">
              <ol class="breadcrumb"><li class="breadcrumb-item">Basis Data 64</li>
                <li class="breadcrumb-item">AKTIVITAS BELAJAR 2</li></ol>
              <h1>Forum Diskusi.1</h1>
              <div class="forumdescription"><p>Diskusikan topik minggu ini. Balas 2 teman.</p></div>
              <div id="introattachments">
                <h3>Lampiran</h3>
                <a href="{b}/pluginfile.php/1/mod_forum/soal_diskusi.pdf"> soal_diskusi.pdf</a>
                <img src="{b}/theme/image.php/mb2iq/core/icon.pdf" alt="ikon pdf">
                <img src="{b}/pluginfile.php/1/user/icon/avatar.jpg" alt="avatar saya">
              </div>
              <article class="forum-post"><div class="post-content-container" data-region="content"
                   id="post-content-1">
                <p><strong>Topik Diskusi Ke 1</strong></p>
                <p>Berikan 3 contoh implementasi operasi dasar pada basis data untuk
                   sistem informasi aset di perguruan tinggi.</p>
                <ul><li>Create, Read, Update, Delete</li></ul>
                <a href="{b}/mod/forum/discuss.php?f=11">Lihat semua post</a>
              </div></article>
              <article class="forum-post"><div class="post-content-container" id="post-content-2">
                <p>Jawaban teman lain, tidak boleh dipakai.</p></div></article>
            </div></div>
            <div class="footer-container">Copyright</div>
            </body></html>
            """)

        if path == "/mod/forum/discuss.php":
            return self._html(f"""
            <html><body><div id="page"><div id="region-main" class="content-col">
              <h1>Diskusi 1 - semua post</h1>
              <div class="forumdescription"><p>Diskusikan topik minggu ini. Balas 2 teman.</p></div>
              <div class="post-content-container" id="post-content-1">
                <p><strong>Topik Diskusi Ke 1</strong></p>
                <p>Berikan 3 contoh implementasi operasi dasar pada basis data.</p>
              </div>
              <div class="post-content-container" id="post-content-2">
                <p>Jawaban teman lain.</p></div>
            </div></div></body></html>
            """)

        if path == "/mod/assign/view.php":
            return self._html(f"""
            <html><head><title>Tugas.1</title></head><body class="sidebar-one">
            <div id="page"><div id="region-main" class="content-col">
              <ol class="breadcrumb"><li class="breadcrumb-item">Basis Data 64</li>
                <li class="breadcrumb-item">Tugas.1</li></ol>
              <h1>Tugas.1</h1>
              <div class="activity-description" id="intro">
                <p>Kerjakan soal berikut dengan teliti.
                   <strong>Jumlah kata minimal 500 kata.</strong></p>
                <ol>
                  <li>Jelaskan perbedaan model relasi 1NF, 2NF, dan 3NF beserta
                      contoh skemanya.</li>
                  <li>Buat rancangan database untuk sistem absensi mahasiswa.</li>
                </ol>
                <p>Format jawaban: <strong>PDF</strong>, font Times New Roman 12,
                   spasi 1.5.</p>
              </div>
              <div class="box generalbox">
                <h2>Pedoman Penilaian</h2>
                <table class="gradingtable">
                  <tr><th>Aspek</th><th>Bobot</th></tr>
                  <tr><td>Ketepatan konsep</td><td>40</td></tr>
                  <tr><td>Kelengkapan rancangan</td><td>40</td></tr>
                  <tr><td>Kerapian</td><td>20</td></tr>
                </table>
              </div>
              <div id="introattachments">
                <a href="{b}/pluginfile.php/2/mod_assign/tugas1.pdf"> tugas1.pdf</a>
              </div>
              <div class="box generalbox"><h3>Submission status</h3>
                <table><tr><td>Submission status</td><td>No submissions have been made yet</td></tr>
                <tr><td>Grading status</td><td>Not graded</td></tr></table>
              </div>
            </div></div>
            <div class="footer-container">Copyright</div>
            </body></html>
            """)

        if path.startswith("/pluginfile.php"):
            name = path.rsplit("/", 1)[-1]
            if name.endswith(".pdf"):
                return self._send(200, self.server.pdf_bytes, "application/pdf")  # type: ignore[attr-defined]
            # Aset tema: harus dibuang, bukan dianggap lampiran.
            return self._send(200, b"\x89PNG\r\n\x1a\n" + b"0" * 400, "image/png")

        if path == "/login/index.php":
            return self._html("<html><body>login</body></html>", 303)

        return self._html("<html><body>tidak ditemukan</body></html>", 404)


# ---------------------------------------------------------------------------
# Stub agent
# ---------------------------------------------------------------------------
GOOD_ANSWER = """## Jawab

### a. Perbedaan 1NF, 2NF, dan 3NF

1NF mensyaratkan setiap atribut atomik. 2NF menambahkan fungsi dependensi penuh
terhadap kunci utama. 3NF menghilangkan dependensi transitif.

Penjelasan ini didasarkan pada lampiran tugas dan halaman resmi yang diberikan.

### b. Rancangan database absensi

Entitas: Mahasiswa, MataKuliah, Enrollment, Absensi.

## Daftar Pustaka

1. Connolly, T., & Begg, C. (2015). *Database Systems* (6th ed.). Pearson. ISBN 978-1-4479-3248-8.
2. https://doi.org/10.1145/3292500.3330718
"""


def _stub_transcribe_opencode(prompt: str, **_kwargs):
    """Stub agent transcriber: menulis transkrip dengan isi PDF tiruan."""
    for line in prompt.splitlines():
        if "{OUT}" in line or "transkrip_" in line:
            for token in line.replace("{", "").replace("}", "").split():
                if token.endswith(".md") and ("transkrip_" in token):
                    out = Path(token)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_text(
                        "Tugas Praktikum 1 - Basis Data\n"
                        "1. Jelaskan perbedaan model relasi 1NF, 2NF, dan 3NF.\n"
                        "2. Buat rancangan database untuk sistem informasi "
                        "absensi mahasiswa.\n",
                        encoding="utf-8",
                    )
    return type("R", (), {"returncode": 0, "stdout": "SELESAI", "stderr": ""})()


def _stub_run_opencode(prompt: str, **_kwargs):
    """Meniru `run_opencode`: catat prompt, tulis jawaban ke path yang diminta."""
    PROMPTS.append(prompt)
    for line in prompt.splitlines():
        if line.startswith("7. Tulis jawaban final") or "Tulis jawaban final dalam format" in line:
            for token in line.split("`"):
                if token.endswith(".md"):
                    out = Path(token)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_text(GOOD_ANSWER, encoding="utf-8")
                    break
    return type("R", (), {"returncode": 0, "stdout": "Selesai", "stderr": ""})()


def main() -> int:
    import config

    fixtures = Path(__file__).parent / "output" / ".testdata"
    if fixtures.exists():
        shutil.rmtree(fixtures)
    fixtures.mkdir(parents=True, exist_ok=True)
    pdf_path = fixtures / "dummy.pdf"
    _make_pdf(pdf_path)
    pdf_bytes = pdf_path.read_bytes()

    server = ThreadingHTTPServer(("127.0.0.1", 0), MockMoodle)
    server.pdf_bytes = pdf_bytes  # type: ignore[attr-defined]
    port = server.server_address[1]
    base = f"http://127.0.0.1:{port}"
    MockMoodle.base = base
    threading.Thread(target=server.serve_forever, daemon=True).start()

    # Arahkan Config ke mock. `load_dotenv(override=True)` membuat variabel
    # lingkungan tidak bisa menimpa .env, jadi patch dilakukan di kelas Config.
    import os

    os.environ["TUTON_CACHE_DIR"] = str(fixtures / "cache")
    config.Config.base_url = classmethod(lambda cls: base)  # type: ignore[assignment]
    config.Config.cookies = classmethod(lambda cls: {"MoodleSession": "dummy"})  # type: ignore[assignment]
    config.Config.NAMA = "Mahasiswa Uji"
    config.Config.NIM = "0000001"
    config.Config.PRODI = "Sains Data"
    config.Config.TUTON_CACHE_DIR = fixtures / "cache"

    import moodle.reader as reader_mod
    import moodle.reader_server as rs

    reader_mod.Config = config.Config
    rs.Config = config.Config

    # Arahkan OUTPUT_DIR ke folder uji supaya state.json asli tidak tersentuh.
    import main as main_mod
    from generator import state as state_mod

    main_mod.OUTPUT_DIR = fixtures / "out"
    main_mod.output_dir = main_mod.OUTPUT_DIR
    main_mod.ensure_reader = rs.ensure_reader
    main_mod.soalu = rs.soalu
    main_mod.run_opencode = _stub_run_opencode
    # `moodle.transcribe` mengimpor run_opencode secara langsung, jadi harus
    # di-stub juga. Tanpa ini test memanggil opencode sungguhan.
    import moodle.transcribe as transcribe_mod

    transcribe_mod.run_opencode = _stub_transcribe_opencode
    # `state.STATE_FILE` dihitung saat import dari config.OUTPUT_DIR. Kalau tidak
    # dipatch, test menulis ke output/state.json milik user sungguhan.
    state_mod.STATE_FILE = fixtures / "out" / "state.json"
    state_mod._STATE = None
    state_mod._STATE_STAMP = None

    try:
        print("\n[1] Discovery: URL terverifikasi & konten benar")
        reader = reader_mod.MoodleReader()
        rs.ensure_reader()
        discovery = main_mod.SourceDiscovery(reader, make_url=rs.soalu)
        from moodle.scraper import Activity

        forum = Activity(mod_type="forum", id=11, title="Forum Diskusi.1",
                         section=1, course_id=1)
        assign = Activity(mod_type="assign", id=22, title="Tugas.1", section=1, course_id=1)

        src_f = discovery.discover(forum, "diskusi")
        src_a = discovery.discover(assign, "tugas")

        check("diskusi: URL thread tidak dobel",
              all("/mod/forum/mod/forum/" not in link.url for link in src_f.links),
              str([link.url for link in src_f.links]))
        check("diskusi: post pembuka terbaca",
              "3 contoh implementasi" in src_f.soal_text, src_f.soal_text[:120])
        check("diskusi: post teman lain dibuang",
              "tidak boleh dipakai" not in src_f.soal_text)
        check("diskusi: aset tema bukan lampiran",
              all("user/icon" not in u and "theme/image" not in u
                  for u in src_f.attachments), str(src_f.attachments))
        check("diskusi: PDF jadi lampiran",
              any(u.endswith("soal_diskusi.pdf") for u in src_f.attachments),
              str(src_f.attachments))
        check("tugas: rubrik jadi markdown",
              "Pedoman Penilaian" in src_a.soal_text and "| Aspek | Bobot |" in src_a.soal_text)
        check("tugas: instruksi khusus tutor terbaca",
              "minimal 500 kata" in src_a.soal_text)
        check("tugas: tabel status BUKAN dianggap rubrik",
              src_a.soal_text.count("Pedoman Penilaian") == 1,
              str(src_a.soal_text.count("Pedoman Penilaian")))
        check("tugas: format jawaban terbaca", "Times New Roman 12" in src_a.soal_text)
        check("tugas: 2 sumber terverifikasi (halaman+seksi)",
              len(src_a.ok_links) >= 2, str(src_a.summary()))
        check("tugas: rubrik TIDAK tampil dua kali",
              src_a.soal_text.count("Pedoman Penilaian / Rubrik") == 0
              and src_a.soal_text.count("| Aspek | Bobot |") <= 1,
              str(src_a.soal_text.count("| Aspek | Bobot |")))

        print("\n[2] Reader: endpoint & keamanan")
        status, ctype, body = rs.handle_soal(src_a.primary_url, "halaman")
        check("handle_soal 200", status == 200, f"status={status}")
        check("isi markdown (bukan HTML mentah)", ctype.startswith("text/markdown"), ctype)
        check("isi memuat butir soal", "1NF" in body)
        status_f, ctype_f, raw = rs.handle_file(src_a.attachments[0])
        check("handle_file 200", status_f == 200, f"status={status_f}")
        check("handle_file mengembalikan PDF", ctype_f == "application/pdf", ctype_f)
        check("PDF benar-benar byte PDF", raw[:4] == b"%PDF", str(raw[:8]))
        status_x, _, _ = rs.handle_file("http://evil.example.com/x.pdf")
        check("SSRF ditolak di /file", status_x == 403, f"status={status_x}")

        print("\n[3] Pipeline penuh: cmd_run")
        args = main_mod.argparse.Namespace(
            course=1, sesi=1, force=True, kind="all", jobs=2, soal_mode=""
        )
        main_mod.cmd_run(args)
        check("agent dipanggil untuk 2 item", len(PROMPTS) == 2, f"{len(PROMPTS)} prompt")

        out_root = fixtures / "out"
        state_path = out_root / "state.json"
        check("state.json dibuat", state_path.exists())
        if state_path.exists():
            data = json.loads(state_path.read_text(encoding="utf-8"))
            items = data.get("items", {})
            done = [v for v in items.values() if v.get("status") == "done"]
            check("2 item berstatus done", len(done) == 2, f"{len(done)} done")
            check("URL sumber tersimpan di state",
                  all(v.get("urls") for v in done), str(done[:1]))
            check("semua output benar-benar ada",
                  all(Path(p).exists() for v in done for p in v.get("outputs", [])))

        docs = sorted(out_root.rglob("*.docx"))
        check("2 file .docx dibuat", len(docs) == 2, str([d.name for d in docs]))

        print("\n[4] Transkripsi otomatis")
        transcripts = sorted(out_root.rglob("transkrip_*.md"))
        check("transkrip.md dibuat per item", len(transcripts) == 2,
              str([t.name for t in transcripts]))
        if transcripts:
            isi = transcripts[0].read_text(encoding="utf-8")
            check("transkrip memuat isi PDF (teks layer)",
                  "1NF" in isi and "absensi" in isi, isi[:140])
        # Satu file gabungan per item, bukan satu file per berkas lampiran.
        # Kalau ada 4 file, berarti penulisan per-berkas lama masih ikut jalan.
        check("hanya ada satu file transkrip per item",
              len(transcripts) == 2, f"{len(transcripts)} file")

        print("\n[5] Prompt yang diterima AI")
        if PROMPTS:
            p = PROMPTS[0]
            check("prompt berisi URL Reader", "http://127.0.0.1:" in p and "/soal?u=" in p)
            check("prompt menyuruh webfetch", "webfetch" in p)
            check("prompt TIDAK menempel soal.md", "soal.md" not in p)
            check("prompt menyebut rubrik", "Rubrik" in p or "rubrik" in p)
            check("prompt menunjuk file transkrip", "transkrip_" in p)
            check("prompt tidak menumpuk transkripsi inline",
                  "Topik Diskusi Ke 1</strong>" not in p)
            check("prompt punya Daftar Pustaka", "Daftar Pustaka" in p)
            check("identitas masuk prompt", "Mahasiswa Uji" in p)
            check("token Reader ada di URL", "&t=" in p)
        diskusi_prompts = [p for p in PROMPTS if "Jenis pekerjaan: diskusi" in p]
        tugas_prompts = [p for p in PROMPTS if "Jenis pekerjaan: tugas" in p]
        check("prompt diskusi dapat aturan manfaat",
              any("Manfaat dan Relevansi" in p for p in diskusi_prompts),
              f"{len(diskusi_prompts)} prompt diskusi")
        check("prompt tugas tidak dapat aturan manfaat",
              all("Manfaat dan Relevansi" not in p for p in tugas_prompts),
              f"{len(tugas_prompts)} prompt tugas")

        print("\n[6] Sesi kedaluwarsa ditangani")
        import moodle.auth as auth_mod

        auth_mod.Config = config.Config
        # Server yang selalu membalas 303 ke /login/index.php, seperti Moodle
        # saat MoodleSession kedaluwarsa.
        class ExpiredMoodle(MockMoodle):
            def do_GET(self):  # noqa: N802
                self.send_response(303)
                self.send_header("Location", f"{self.base}/login/index.php")
                self.send_header("Content-Length", "0")
                self.end_headers()

        expired_server = ThreadingHTTPServer(("127.0.0.1", 0), ExpiredMoodle)
        expired_server.pdf_bytes = pdf_bytes  # type: ignore[attr-defined]
        eport = expired_server.server_address[1]
        ebase = f"http://127.0.0.1:{eport}"
        ExpiredMoodle.base = ebase
        threading.Thread(target=expired_server.serve_forever, daemon=True).start()

        saved_base = config.Config.base_url
        config.Config.base_url = classmethod(lambda cls: ebase)  # type: ignore[assignment]
        auth_mod.Config = config.Config
        try:
            expired = auth_mod.MoodleSession()
            try:
                expired.check_login()
                check_login_msg = "TIDAK menghasilkan error (bug)"
            except auth_mod.SessionExpired as exc:
                check_login_msg = str(exc)
            except Exception as exc:  # noqa: BLE001
                check_login_msg = f"{type(exc).__name__}: {exc}"
            check("pesan expired menyebut MoodleSession",
                  "MoodleSession" in check_login_msg, check_login_msg[:110])
            check("bukan TooManyRedirects yang bocor",
                  "TooManyRedirects" not in check_login_msg, check_login_msg[:110])
        finally:
            config.Config.base_url = saved_base  # type: ignore[assignment]
            auth_mod.Config = config.Config
            expired_server.shutdown()
            expired_server.server_close()

        print("\n[7] Mode file (A/B) tetap jalan")
        PROMPTS.clear()
        args_file = main_mod.argparse.Namespace(
            course=1, sesi=1, force=True, kind="tugas", jobs=1, soal_mode="file"
        )
        main_mod.cmd_run(args_file)
        check("mode file menghasilkan 1 prompt", len(PROMPTS) == 1, f"{len(PROMPTS)}")
        if PROMPTS:
            check("mode file menunjuk soal.md", "soal.md" in PROMPTS[0])
            check("mode file tidak pakai URL Reader", "/soal?u=" not in PROMPTS[0])
        soal_files = list((fixtures / "out").rglob("soal.md"))
        check("soal.md ditulis pada mode file", len(soal_files) >= 1)

        print("\n[8] CLI lain")
        PROMPTS.clear()
        main_mod.cmd_status(None)
        main_mod.cmd_scrape(main_mod.argparse.Namespace(course=1))
        check("cmd_status & cmd_scrape tidak error", True)

        print("\n[9] State: perubahan dari proses lain terlihat")
        # Server Flask (server.py) dan pipeline (main.py) adalah dua proses
        # berbeda yang menulis state.json yang sama. Kalau state.py memegang
        # cache di memori selamanya, /api/status dan /api/results terus
        # mengembalikan keadaan lama, sehingga file .docx yang baru selesai tidak
        # pernah muncul di menu Hasil sampai server di-restart.
        cached_state_file = state_mod.STATE_FILE
        tmp_state = fixtures / "out" / "state_external.json"
        state_mod.STATE_FILE = tmp_state
        state_mod._STATE = None
        state_mod._STATE_STAMP = None
        try:
            tmp_state.write_text(json.dumps({"items": {}}), encoding="utf-8")
            check("state kosong terbaca", state_mod._load()["items"] == {})

            # Simulasikan proses anak main.py yang menulis hasil (.docx selesai).
            tmp_state.write_text(
                json.dumps({"items": {"ext:1": {"status": "done"}}}),
                encoding="utf-8",
            )
            check(
                "perubahan file dari proses lain TERBACA (bukan cache basi)",
                "ext:1" in state_mod._load()["items"],
                str(list(state_mod._load()["items"])),
            )

            # set_item setelah load ulang harus menulis ke file dengan isi
            # terbaru, bukan menimpa cache usang.
            state_mod.set_item("ext:2", {"status": "running"})
            on_disk = json.loads(tmp_state.read_text(encoding="utf-8"))["items"]
            check(
                "set_item setelah reload menulis ke disk",
                on_disk.get("ext:1", {}).get("status") == "done"
                and on_disk.get("ext:2", {}).get("status") == "running",
                str(on_disk),
            )

            # File korup / hilang di luar proses: jangan sampai crash.
            tmp_state.write_text("{bukan json", encoding="utf-8")
            check("file korup -> state kosong, tidak crash",
                  state_mod._load()["items"] == {})
            tmp_state.unlink()
            check("file hilang -> state kosong, tidak crash",
                  state_mod._load()["items"] == {})
        finally:
            state_mod.STATE_FILE = cached_state_file
            state_mod._STATE = None
            state_mod._STATE_STAMP = None
            tmp_state.unlink(missing_ok=True)

    finally:
        server.shutdown()
        server.server_close()

    print("\n" + "=" * 66)
    print(f"LULUS: {len(PASS)}   GAGAL: {len(FAIL)}")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
