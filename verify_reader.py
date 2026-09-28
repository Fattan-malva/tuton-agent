"""Verifikasi lokal: render Markdown, guard keamanan, dan Reader endpoint.

Tidak menyentuh Moodle sungguhan. Mengembalikan exit code non-nol kalau ada
yang gagal, jadi bisa dipakai sebagai pagar regresi.
"""

import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

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
check("butir soal terbaca", "1NF, 2NF, dan 3NF" in md)
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
from pathlib import Path  # noqa: E402

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
print("\n" + "=" * 62)
print(f"LULUS: {len(PASS)}   GAGAL: {len(FAIL)}")
for name, detail in FAIL:
    print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
