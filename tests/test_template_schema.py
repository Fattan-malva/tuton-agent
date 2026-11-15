import tempfile
import unittest
import zipfile
from pathlib import Path

from docx import Document

from tools import docx as docx_tool
from tuton import template_schema as ts


def _teks_dokumen(path: Path) -> str:
    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs]
    for tbl in doc.tables:
        for row in tbl.rows:
            parts.extend(c.text for c in row.cells)
    return "\n".join(parts)


def _warna_run(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    import re
    return set(re.findall(r'<w:color w:val="([0-9A-Fa-f]{6}|auto)"', xml))


class TestPreset(unittest.TestCase):
    def test_semua_preset_valid(self):
        for tid in ts.PRESET:
            with self.subTest(tid=tid):
                ts.normalisasi(ts.preset_skema(tid))

    def test_lima_preset_berbeda(self):
        sig = set()
        for tid in ts.PRESET:
            s = ts.normalisasi(ts.preset_skema(tid))
            sig.add((s["font"], s["margin_cm"], s["size_pt"], tuple(b["type"] for b in s["blocks"])))
        self.assertEqual(len(sig), 5)

    def test_font_di_luar_daftar_ditolak(self):
        bad = ts.preset_skema("ringkas")
        bad["font"] = "Comic Sans MS"
        with self.assertRaises(ts.SkemaSalah):
            ts.normalisasi(bad)

    def test_harus_tepat_satu_answer(self):
        bad = ts.preset_skema("ringkas")
        bad["blocks"] = [b for b in bad["blocks"] if b["type"] != "answer"]
        with self.assertRaises(ts.SkemaSalah):
            ts.normalisasi(bad)


class TestRender(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_semua_teks_dan_warna_hitam(self):
        for tid in ts.PRESET:
            for mode in ("pratinjau", "pekerjaan"):
                with self.subTest(tid=tid, mode=mode):
                    out = ts.render(ts.preset_skema(tid), self.dir / f"{tid}-{mode}.docx", mode)
                    self.assertTrue(_warna_run(out) <= {"000000", "auto"})
                    doc = Document(str(out))
                    for nama in ("Normal", "Heading 1", "Heading 2", "Heading 3", "List Number", "List Bullet"):
                        rgb = doc.styles[nama].font.color.rgb
                        self.assertIn(rgb, (None, ts.RGBColor(0, 0, 0)), nama)

    def test_pratinjau_memakai_lorem(self):
        out = ts.render(ts.preset_skema("ringkas"), self.dir / "p.docx", "pratinjau")
        self.assertIn("Lorem", _teks_dokumen(out))

    def test_pekerjaan_tanpa_sampel_dan_berhenti_di_answer(self):
        out = ts.render(ts.preset_skema("akademik-standar"), self.dir / "k.docx", "pekerjaan")
        teks = _teks_dokumen(out)
        self.assertNotIn("Lorem", teks)
        self.assertNotIn("[Jawaban", teks)
        self.assertIn("[Judul]", teks)
        self.assertEqual(len(Document(str(out)).tables), 1)  # hanya identitas

    def test_build_docx_isi_kerangka_tanpa_ubah_layout(self):
        kerangka = ts.render(ts.preset_skema("akademik-standar"), self.dir / "kerangka.docx", "pekerjaan")
        meta = {
            "nama": "Budi", "nim": "123", "semester": "3", "ut_daerah": "Jakarta",
            "matkul": "Biologi", "matkul_kode": "BIOL", "kind_label": "Tugas", "display_index": "1",
            "file_base": "uji",
        }
        out_dir = self.dir / "out"
        out_dir.mkdir()
        hasil, _ = docx_tool.save_doc(
            jawaban_md="## Jawaban\n\nIsi jawaban uji.",
            soal_text="",
            meta=meta,
            out_dir=out_dir,
            template=kerangka,
            include_soal=False,
            gambar_soal=None,
        )
        doc = Document(str(hasil))
        teks = _teks_dokumen(hasil)
        self.assertIn("Isi jawaban uji.", teks)
        self.assertNotIn("Lorem", teks)
        self.assertEqual(len(doc.tables), 1)
        nilai = {r.cells[0].text.strip(): r.cells[1].text.strip() for r in doc.tables[0].rows}
        self.assertEqual(nilai.get("Nama"), "Budi")
        self.assertEqual(nilai.get("NIM"), "123")


if __name__ == "__main__":
    unittest.main()
