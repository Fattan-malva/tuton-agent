"""Solver manual: satu teks soal -> jawaban -> .docx.

Dipakai endpoint /api/solve di server.py untuk mengerjakan soal yang
diketik langsung di UI, tanpa harus punya course Moodle.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from pathlib import Path

from . import config
from .pipeline import panggil_agent_bertahap, PipelineGagal


def main() -> int:
    p = argparse.ArgumentParser(prog="backend.solve")
    p.add_argument("--title", default="Jawaban Kustom")
    p.add_argument("--sesi", type=int, default=0)
    p.add_argument("--soal", required=True)
    p.add_argument("--model", default=None)
    args = p.parse_args()

    slug = config.slugify(args.title) or "kustom"
    root = config.OUTPUT_DIR / ".solve" / f"{int(time.time())}"
    jawaban_dir = root / "_jawaban"
    jawaban_dir.mkdir(parents=True, exist_ok=True)
    tujuan = jawaban_dir / "jawaban.md"
    (root / "soal.txt").write_text(args.soal, encoding="utf-8")

    prompt = f"""Tulis jawaban tutorial online untuk soal di bawah.

Judul : {args.title}
Sesi  : {args.sesi or '-'}

## Rumusan soal
{args.soal}

Tulis jawaban ke: {tujuan}

Struktur jawaban yang diminta dokumen akhir:

- `## Jawaban` sebagai heading utama isi jawaban.
- **Soal ditulis ulang lebih dulu, baru dijawab.** Setiap nomor soal memakai
  heading `###` yang memuat nomor dan rumusan soalnya.
- **Setiap butir dalam soal wajib dijawab sendiri.**
- `## Daftar Pustaka` di bagian paling akhir bila perlu.
- Persamaan ditulis dengan LaTeX memakai pemisah dolar: `$...$` untuk
  sebaris dan `$$` di baris sendiri untuk blok.
- Tulis sebagai mahasiswa yang mengerjakan tugas, pakai kata "saya".
- Akhiri dengan baris persis: SELESAI
"""

    hasil = panggil_agent_bertahap(
        nama=config.AGENT_WORKER,
        prompt=prompt,
        model=args.model or config.PRIMARY_MODEL,
        hasil_wajib=tujuan,
        label="solve",
    )
    if not hasil.selesai and not tujuan.is_file():
        raise PipelineGagal(f"Worker gagal menulis jawaban: {hasil.stderr[-500:]}")

    sys.path.insert(0, str(config.BASE_DIR))
    spec = importlib.util.spec_from_file_location("jkt_docx_solve", config.TOOLS_DIR / "docx.py")
    if spec is None or spec.loader is None:
        raise PipelineGagal("docx tool tidak bisa dimuat.")
    docx_tool = importlib.util.module_from_spec(spec)
    sys.modules["jkt_docx_solve"] = docx_tool
    spec.loader.exec_module(docx_tool)

    template = None
    if config.TEMPLATE_DIR.is_dir():
        kandidat = sorted(config.TEMPLATE_DIR.glob("*.docx"))
        template = kandidat[0] if kandidat else None

    ident = config.identitas()
    meta = {
        "file_base": f"{slug}-sesi-{args.sesi or 0}",
        "kind_label": "Kustom",
        "display_index": str(args.sesi or ""),
        "matkul": args.title,
        "matkul_kode": "",
        **ident,
    }
    out = config.output_dir(slug, args.sesi or 0)
    out.mkdir(parents=True, exist_ok=True)
    docx_path, _ = docx_tool.save_doc(
        tujuan.read_text(encoding="utf-8"),
        args.soal,
        meta,
        out,
        template=template,
        include_soal=True,
    )
    print(f"Berkas jawaban: {docx_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PipelineGagal as exc:
        print(f"GAGAL: {exc}", file=sys.stderr)
        raise SystemExit(1)
