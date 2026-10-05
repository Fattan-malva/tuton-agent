"""Verifikasi lokal: render Markdown, guard keamanan, Reader endpoint, dan stop.

Tidak menyentuh Moodle sungguhan. Mengembalikan exit code non-nol kalau ada
yang gagal, jadi bisa dipakai sebagai pagar regresi.
"""

import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from pathlib import Path  # noqa: E402

from config import Config  # noqa: E402

PASS, FAIL = [], []


def check(name, condition, detail=""):
    if condition:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append((name, detail))
        print(f"  FAIL  {name}  {detail}")


# ---------------------------------------------------------------------------
# 1) Render Markdown dari HTML ala Moodle
# ---------------------------------------------------------------------------
print("\n[1] render_moodle_html")

from moodle.reader import _meaningful_length, render_moodle_html  # noqa: E402

ASSIGN_HTML = """
<html><head><title>Tugas 1 - Basis Data</title></head>
<body>
<nav class="navbar"><a href="/">Dashboard</a><a href="/my/">My courses</a></nav>
<ol class="breadcrumb"><li class="breadcrumb-item">Dashboard</li>
  <li class="breadcrumb-item">Basis Data</li></ol>
<div role="main" class="region-main">
 <div class="region-main-content">
  <h1 class="main">Tugas 1 - Entity Relationship</h1>
  <div class="activity-description" id="intro">
    <p>Kerjakan soal berikut dengan teliti. <b>Jumlah kata minimal 500 kata</b>.</p>
    <ol>
      <li>Jelaskan perbedaan model relasi 1NF, 2NF, dan 3NF beserta contoh skemanya.</li>
      <li>Buat rancangan database untuk sistem informasi absensi mahasiswa,
          lengkap dengan ERD dan daftar tabel.</li>
    </ol>
    <p>Format jawaban: PDF, font Times New Roman 12, spasi 1.5.</p>
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
    <h3>Lampiran</h3>
    <a href="https://elearning.ut.ac.id/pluginfile.php/123/mod_assign/soal.pdf"> soal.pdf</a>
    <img src="https://elearning.ut.ac.id/pluginfile.php/123/img/erd.png" alt="Contoh ERD">
  </div>
  <form class="submitassignment"><button type="submit">Kirim</button></form>
 </div>
</div>
<footer class="footer-container">Copyright</footer>
<script>alert(1)</script>
</body></html>
"""

md = render_moodle_html(
    ASSIGN_HTML,
    "https://elearning.ut.ac.id/mod/assign/view.php?id=999",
    kind="assign",
    url_for=lambda u, kind="page": f"/proxy?u={urllib.parse.quote(u, safe='')}",
)
print(md[:400].replace("\n", "\n    | "))
print("    ...")

check("judul ikut terbaca", "# Tugas 1 - Entity Relationship" in md)
check("soal terbaca", "1NF, 2NF, dan 3NF" in md)
check("instruksi khusus tutor terbaca", "minimal 500 kata" in md)
check("syarat format terbaca", "Times New Roman 12" in md)
check("tabel rubrik jadi markdown", "| Aspek | Bobot |" in md and "|---|---|" in md)
check("isi rubrik utuh", "Ketepatan konsep" in md and "Kerapian" in md)
check("URL sumber ada di header", "URL sumber: https://elearning.ut.ac.id/mod/assign" in md)
check("gambar jadi link markdown", "![Contoh ERD](/proxy?u=" in md)
check("navigasi dibuang", "My courses" not in md)
check("tombol kirim dibuang", "Kirim" not in md)
check("footer dibuang", "Copyright" not in md)
check("script dibuang", "alert(1)" not in md)
check("URL lampiran ditulis ulang", "soal.pdf" in md)
check("tidak ada link absolut bocor", "elearning.ut.ac.id/pluginfile" not in md)

FORUM_HTML = """
<html><body><div role="main">
  <div class="forumdescription"><p>Diskusi 2 - Topik minggu ini. Balas minimal 2 teman.</p></div>
  <article class="forum-post" id="post-1">
    <div id="post-content-1">
      <p>Pertanyaan: bagaimanaANC database bisa autoria proses penilaian otomatis?</p>
      <ul><li>Jelaskan mekanisme.</li><li>Contohkan di industri.</li></ul>
    </div>
  </article>
  <article class="forum-post" id="post-2">
    <div id="post-content-2"><p>Jawaban teman A (jangan dipakai).</p></div>
  </article>
</div></body></html>
""".replace("ANC", "")

md2 = render_moodle_html(
    FORUM_HTML,
    "https://elearning.ut.ac.id/mod/forum/view.php?id=111",
    kind="forum",
)
print("\n[2] forum")
print("    " + md2[:200].replace("\n", "\n    | "))
check("deskripsi forum terbaca", "Balas minimal 2 teman" in md2)
check("post pembuka terbaca", "mekanisme" in md2)
check("post teman lain dibuang", "Jawaban teman A" not in md2)
check("heading 'post pembuka' ada", "Isi Diskusi (post pembuka)" in md2)

print("\n[3] _meaningful_length")
check("header tidak dihitung", _meaningful_length("## Isi\n- URL sumber: x\n- Lokasi: y") == 0)
check("isi dihitung", _meaningful_length("## Isi\nJelaskan 3NF dan 2NF dengan benar") > 10)

# ---------------------------------------------------------------------------
# 4) Guard keamanan
# ---------------------------------------------------------------------------
print("\n[4] guard keamanan")
from moodle import reader_server as rs  # noqa: E402
from moodle.reader import MoodleReader  # noqa: E402

r = MoodleReader()
base = Config.base_url()
check("host Moodle diizinkan", r.allowed(base + "/mod/assign/view.php?id=1"))
check("host asing ditolak", not r.allowed("http://evil.example.com/x"))
check("file lokal ditolak", not r.allowed("file:///C:/Windows/win.ini"))
check("localhost ditolak", not r.allowed("http://127.0.0.1:1/x"))
check("skema ftp ditolak", not r.allowed("ftp://elearning.ut.ac.id/x"))

status, _ctype, body = rs.handle_soal("http://evil.example.com/x", "assign")
check("handle_soal tolak host asing", status == 403, f"status={status}")
status, _ctype, _body = rs.handle_file("http://evil.example.com/x")
check("handle_file tolak host asing", status == 403, f"status={status}")
status, _ctype, body = rs.handle_soal("", "assign")
check("handle_soal tolak url kosong", status == 400, f"status={status}")

# ---------------------------------------------------------------------------
# 5) Server Reader end-to-end (loopback)
# ---------------------------------------------------------------------------
print("\n[5] server Reader end-to-end")
reader_base = rs.ensure_reader()
check("Reader menyala", bool(reader_base), reader_base)
if reader_base:
    with urllib.request.urlopen(f"{reader_base}/healthz", timeout=10) as resp:
        check("healthz 200", resp.status == 200)

    # Tanpa token harus ditolak.
    try:
        urllib.request.urlopen(
            f"{reader_base}/soal?u=" + urllib.parse.quote(base + "/mod/assign/view.php?id=1", safe=""),
            timeout=10,
        )
        check("tanpa token ditolak", False, "server menerima")
    except urllib.error.HTTPError as exc:
        check("tanpa token ditolak", exc.code == 403, f"code={exc.code}")

    # Token salah harus ditolak.
    try:
        urllib.request.urlopen(f"{reader_base}/soal?u=x&t=token-palsu", timeout=10)
        check("token salah ditolak", False, "server menerima")
    except urllib.error.HTTPError as exc:
        check("token salah ditolak", exc.code == 403, f"code={exc.code}")

    # URL host asing dengan token benar harus ditolak.
    try:
        urllib.request.urlopen(
            f"{reader_base}/soal?u=" + urllib.parse.quote("http://evil.example.com/", safe="")
            + f"&t={rs.token()}",
            timeout=10,
        )
        check("token benar tapi host asing ditolak", False, "server menerima")
    except urllib.error.HTTPError as exc:
        check("token benar tapi host asing ditolak", exc.code == 403, f"code={exc.code}")

    check("soalu() menghasilkan URL Reader", rs.soalu(base + "/x", "assign").startswith(reader_base))
    check("fileurl() menghasilkan URL Reader", rs.fileurl(base + "/x").startswith(reader_base))
    rs.stop_reader()

# ---------------------------------------------------------------------------
# 6) Deteksi model vision (Fase 0)
# ---------------------------------------------------------------------------
print("\n[6] deteksi model vision")
import moodle.transcribe as T  # noqa: E402

models = T._fetch_models()
check("daftar model terdeteksi", len(models) > 10, f"{len(models)} model")
cands = T._candidates(pdf=False)
check("kandidat vision tidak kosong", len(cands) > 0, str(cands))
check("kandidat vision dibatasi", len(cands) <= Config.OPENCODE_VISION_TRIES, str(cands))
parsed = T._parse_plain_models("DESCRIPTION\n  List all available models\nopencode/big-pickle\nopencode/mimo-v2.6-flash-free\n")
check("parse output polos", parsed == ["opencode/big-pickle", "opencode/mimo-v2.6-flash-free"], str(parsed))

# ---------------------------------------------------------------------------
# 7) Prompt URL-only
# ---------------------------------------------------------------------------
print("\n[7] prompt URL-only")

from generator.prompt import build_prompt  # noqa: E402

prompt = build_prompt(
    mode="url",
    work_kind="diskusi",
    index=2,
    course_name="Basis Data",
    section_num=3,
    activity_title="Diskusi 2",
    soal_urls=["http://127.0.0.1:8765/soal?u=abc&k=halaman&t=xyz"],
    source_urls=["https://elearning.ut.ac.id/mod/forum/view.php?id=1"],
    attachments=[r"C:\x\lampiran\soal.pdf"],
    lampiran_dir=Path(r"C:\x\lampiran"),
    jawaban_path=Path(r"C:\x\jawaban_diskusi_2.md"),
    agent_can_read_files=True,
)
check("prompt memuat URL Reader", "http://127.0.0.1:8765/soal?u=abc" in prompt)
check("prompt menyuruh webfetch", "webfetch" in prompt)
check("prompt menekankan rubrik", "Rubrik" in prompt or "rubrik" in prompt)
check("prompt menekankan ajakan tak mengarang", "JANGAN mengarang" in prompt)
check("prompt punya Daftar Pustaka", "Daftar Pustaka" in prompt)
check("prompt punya aturan manfaat (diskusi)", "Manfaat dan Relevansi" in prompt)
check("prompt tidak menempel soal.md", "soal.md" not in prompt)
check("prompt menyebut lampiran", "soal.pdf" in prompt)

prompt_tugas = build_prompt(
    mode="url", work_kind="tugas", index=1, course_name="Aljabar", section_num=1,
    activity_title="Tugas 1", soal_urls=["http://127.0.0.1:8765/soal?u=q&t=z"],
    source_urls=[], attachments=[], lampiran_dir=None,
    jawaban_path=Path("j.md"), agent_can_read_files=False,
)
check("tugas tidak dapat bagian manfaat", "Manfaat dan Relevansi" not in prompt_tugas)

# ---------------------------------------------------------------------------
# 8) Mutex state.json untuk thread paralel
# ---------------------------------------------------------------------------
print("\n[8] state")
from generator import state as st  # noqa: E402

st.set_item("test:1", {"status": "done", "outputs": [], "urls": ["u1"]})
check("state tersimpan", st.get_item("test:1")["urls"] == ["u1"])
st._load()["items"].pop("test:1", None)
st.save()

# ---------------------------------------------------------------------------
# 9) Stop: satu klik harus mematikan semua proses, bukan hanya induknya
# ---------------------------------------------------------------------------
# Dua kegagalan yang dilaporkan user:
#
#   1. Log berhenti, tapi `opencode` dan `node` tetap jalan -- tombol stop
#      terasa berhasil padahal tidak. Penyebabnya `Popen.kill()` yang hanya
#      menembak satu PID, sedangkan semua agen adalah proses lain.
#   2. Satu klik Stop mengisi `state.json` dengan `failed` untuk item yang
#      belum sempat selesai, jadi run berikutnya mengulang dari awal.
#
# Yang diuji di sini adalah bagian yang bisa diperiksa tanpa menjalankan pipeline:
# registry proses hidup benar-benar bekerja, stop bersifat idempoten, dan
# `_pasang_handler_stop`/grup proses diaktifkan di kedua OS.
print("\n[9] Stop mematikan seluruh proses")
from generator import opencode_runner as _ocr  # noqa: E402

# Registry hidup harus bisa dipakai tanpa menjalankan apa pun.
_ocr.clear_stop()
check("awal: tidak ada sesi hidup", _ocr.live_processes() == [])
check("clear_stop menghapus tanda stop", not _ocr.stop_requested())
_ocr.request_stop()
check("request_stop menandai stop", _ocr.stop_requested())
_ocr.clear_stop()
check("clear_stop bisa dipakai lagi", not _ocr.stop_requested())

# `request_stop` harus aman dipanggil berulang: user bisa menekan stop dua kali
# tanpa merusak apa pun.
for _ in range(3):
    _ocr.request_stop()
check("request_stop idempoten", _ocr.stop_requested())
_ocr.clear_stop()

# RunStopped harus TERPISAH dari TimeoutError. Kalau tidak, satu klik stop
# akan diperlakukan sebagai "item gagal, coba lagi" oleh pipeline.
check("RunStopped bukan anak TimeoutError",
      not issubclass(_ocr.RunStopped, TimeoutError),
      _ocr.RunStopped.__mro__[1].__name__)

# Proses nyata: pid zombie dipakai supaya kill() benar-benar berhasil tanpa
# menjalankan opencode sungguhan.
_proses = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(30)"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    start_new_session=(os.name != "nt"),
)
_ocr._register(_proses)
check("sesi terdaftar sebagai hidup",
      any(p.pid == _proses.pid for p in _ocr.live_processes()),
      str([p.pid for p in _ocr.live_processes()]))
_mati = _ocr.request_stop()
check("request_stop melaporkan jumlah sesi yang dibunuh", _mati == 1, str(_mati))
try:
    _proses.wait(timeout=10)
except subprocess.TimeoutExpired:
    _proses.kill()
    check("sesi benar-benar berhenti", False, "proses masih hidup setelah 10s")
else:
    check("sesi benar-benar berhenti", True)

# Proses yang sudah selesai harus dibuang dari daftar hidup.
_proses2 = subprocess.Popen([sys.executable, "-c", "pass"])
_ocr._register(_proses2)
_proses2.wait(timeout=10)
check("proses yang sudah selesai tidak dihitung hidup",
      all(p.pid != _proses2.pid for p in _ocr.live_processes()),
      str([p.pid for p in _ocr.live_processes()]))
_ocr.clear_stop()

# source `_spawn_cmd`: grup proses sendiri harus diminta di POSIX. Tanpa itu
# `killpg` akan ikut membunuh server, jadi tidak ada cara berhenti dengan aman.
import inspect as _inspect  # noqa: E402

_spawn_src = _inspect.getsource(_ocr._spawn_cmd)
if os.name != "nt":
    check("_spawn_cmd meminta start_new_session di POSIX",
          "start_new_session" in _spawn_src, "")
else:
    check("_spawn_cmd pakai CREATE_NEW_PROCESS_GROUP di Windows",
          "CREATE_NEW_PROCESS_GROUP" in _spawn_src, "")

# main.py harus memasang handler sinyal, kalau tidak SIGTERM dari server
# membunuh proses di tengah jalan dan anak-anaknya jadi orphan.
_main_src = Path("main.py").read_text(encoding="utf-8")
check("main.py memasang handler SIGTERM/SIGINT",
      "SIGTERM" in _main_src and "_pasang_handler_stop" in _main_src, "")
check("main.py membedakan stop dari timeout",
      "DihentikanUser" in _main_src, "")
check("stop tidak menandai item sebagai failed",
      "except DihentikanUser" in _main_src, "")

# server.py harus membunuh grup proses, bukan satu PID.
_server_src = Path("server.py").read_text(encoding="utf-8")
check("server memakai killpg, bukan proc.kill() saja",
      "killpg" in _server_src, "")
check("server menyapu sesi yang lolos dari grup",
      "_live_agent_sessions" in _server_src, "")
check("server melaporkan jumlah proses yang dibunuh",
      '"killed"' in _server_src, "")
check("server menyiapkan folder keluaran per request",
      "before_request" in _server_src, "")

# ---------------------------------------------------------------------------
# 10) Pratinjau docx: penomoran dan indentasi dibaca dari XML
# ---------------------------------------------------------------------------
# Preview adalah satu-satunya tampilan yang bisa dilihat pengguna sebelum
# mengunduh, jadi kalau ia menebak penomoran dari teks, pengguna akan melihat
# angka yang salah tepat di layar. Dua hal di sini dibaca dari w:numPr dan
# w:ind, bukan dari regex teks.
print("\n[10] Pratinjau docx memakai penomoran native")
from generator.docx import save_doc  # noqa: E402
from generator.preview import docx_to_html  # noqa: E402

_scratch = Path("output") / ".verify_preview"
_scratch.mkdir(parents=True, exist_ok=True)
_md = (
    "## Jawaban Mahasiswa\n\n"
    "### a. Soal Satu\n\n"
    "Paragraf biasa.\n\n"
    "- butir bullet pertama\n"
    "- butir bullet kedua\n\n"
    "### b. Soal Dua\n\n"
    "1. butir satu\n"
    "2. butir dua\n"
    "3. butir tiga\n\n"
    "## Daftar Pustaka\n\n"
    "Suprapto. (2025). Logika Informatika. Universitas Terbuka.\n"
    "Elmasri, R. (2016). Fundamentals of database systems. Pearson.\n"
)
_docx_path, _ = save_doc(
    jawaban_md=_md,
    soal_text="",
    meta={"file_base": "preview", "nama": "Uji", "nim": "1"},
    out_dir=_scratch,
)
_html = docx_to_html(str(_docx_path))

check("bullet jadi <ul>", "<ul>" in _html or "<ul " in _html, _html[:200])
check("daftar angka jadi <ol>", "<ol" in _html, _html[:200])
# Daftar kedua dimulai dari 1, jadi <ol> tidak butuh start. Yang diuji di sini
# justru bahwa penomoran tidak diketik sebagai teks di dalam <li>.
check("angka tidak diketik sebagai teks di dalam <li>",
      not re.search(r"<li[^>]*>\s*\d+[.)]\s", _html),
      (re.search(r"<li[^>]*>.{0,30}", _html) or [""])[0] if re.search(r"<li", _html) else "")
check("isi <li> berisi teks butir, bukan nomor",
      "butir satu" in _html, _html[:300])
check("referensi diurutkan A-Z di pratinjau",
      _html.index("Elmasri") < _html.index("Suprapto"), "urutan salah")
check("referensi pakai baris menggantung",
      "text-indent:-" in _html, _html[-400:])
shutil.rmtree(_scratch, ignore_errors=True)

# ---------------------------------------------------------------------------
print("\n" + "=" * 62)
print(f"LULUS: {len(PASS)}   GAGAL: {len(FAIL)}")
for name, detail in FAIL:
    print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
