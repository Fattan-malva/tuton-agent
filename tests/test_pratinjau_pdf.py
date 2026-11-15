import shutil
import unittest
from pathlib import Path
from unittest import mock

from server import pratinjau_pdf

from tuton import templates

DOCX_BYTES = templates.pratinjau_docx("", template_id="akademik-standar")


@unittest.skipUnless(shutil.which("soffice") or shutil.which("libreoffice"), "LibreOffice tidak terpasang")
class TestPratinjauPdf(unittest.TestCase):
    def tearDown(self):
        for sesi in list(pratinjau_pdf._SESI.values()):
            shutil.rmtree(sesi["folder"], ignore_errors=True)
        pratinjau_pdf._SESI.clear()

    def test_konversi_lalu_hapus_bersih(self):
        id_ = pratinjau_pdf.buat("user-a", DOCX_BYTES)
        folder = pratinjau_pdf._SESI[id_]["folder"]
        self.assertTrue(folder.is_dir())
        self.assertTrue(pratinjau_pdf.ambil_pdf("user-a", id_).startswith(b"%PDF"))
        self.assertTrue(pratinjau_pdf.hapus("user-a", id_))
        self.assertFalse(folder.exists(), "folder PDF sementara harus hilang setelah hapus")
        with self.assertRaises(KeyError):
            pratinjau_pdf.ambil_pdf("user-a", id_)

    def test_sesi_orang_lain_tidak_bisa_dibaca_atau_dihapus(self):
        id_ = pratinjau_pdf.buat("user-a", DOCX_BYTES)
        with self.assertRaises(KeyError):
            pratinjau_pdf.ambil_pdf("user-b", id_)
        self.assertFalse(pratinjau_pdf.hapus("user-b", id_))
        self.assertTrue(pratinjau_pdf.hapus("user-a", id_))

    def test_kadaluarsa_dibersihkan(self):
        id_ = pratinjau_pdf.buat("user-a", DOCX_BYTES)
        folder = pratinjau_pdf._SESI[id_]["folder"]
        with mock.patch.object(pratinjau_pdf, "TTL_DETIK", -1):
            self.assertEqual(pratinjau_pdf.bersihkan_kadaluarsa(), 1)
        self.assertFalse(folder.exists())
        self.assertNotIn(id_, pratinjau_pdf._SESI)

    def test_docx_rusak_ditolak_dan_tidak_meninggalkan_folder(self):
        sebelum = set(Path(pratinjau_pdf.tempfile.gettempdir()).glob("pratinjau-*"))
        with self.assertRaises(pratinjau_pdf.PratinjauGagal):
            pratinjau_pdf.buat("user-a", b"bukan docx")
        sesudah = set(Path(pratinjau_pdf.tempfile.gettempdir()).glob("pratinjau-*"))
        self.assertEqual(sebelum, sesudah)


if __name__ == "__main__":
    unittest.main()
