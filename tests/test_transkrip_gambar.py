"""Transkripsi vision yang gagal tidak boleh dibaca sebagai sukses."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tuton import config, courses, pipeline


class UjiTranskripGambar(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

        patch = mock.patch.object(config, "KERJA_DIR", self.root)
        patch.start()
        self.addCleanup(patch.stop)

        patch = mock.patch.object(pipeline, "panggil_agent_bertahap")
        self.panggil = patch.start()
        self.addCleanup(patch.stop)

        mk = courses.MataKuliah(id="x", nama="Uji", kode="", kelas="", slug="uji")
        self.pipe = pipeline.Pipeline(mk, 1)
        for patch in (
            mock.patch.object(self.pipe, "_model_agent", return_value="tes/model"),
            mock.patch.object(self.pipe, "_log"),
        ):
            patch.start()
            self.addCleanup(patch.stop)

        for path in self.pipe.dirs.values():
            path.mkdir(parents=True, exist_ok=True)
        self.gambar = self.root / "soal-01.png"
        self.gambar.write_bytes(b"png")

    def _hasil(self, *, selesai=False, ditolak=False):
        return pipeline.HasilAgent(
            perintah=[], selesai=selesai, stdout="", stderr="",
            durasi=0.0, kode=0 if selesai else -1, model="tes/model",
            galat_provider="429" if ditolak else "", model_ditolak=ditolak,
        )

    def test_model_ditolak_mengembalikan_none(self):
        self.panggil.return_value = self._hasil(ditolak=True)
        hasil = self.pipe._transkrip_gambar(
            self.gambar, slug="soal-01", judul="# T", konteks="",
            gabung_pilihan=False,
        )
        self.assertIsNone(hasil)

    def test_berkas_berisi_kop_saja_mengembalikan_none(self):
        self.panggil.return_value = self._hasil()
        hasil = self.pipe._transkrip_gambar(
            self.gambar, slug="soal-02", judul="# T", konteks="",
            gabung_pilihan=False,
        )
        self.assertIsNone(hasil)

    def test_isi_asli_diterima(self):
        def tulis(**kw):
            tujuan = kw["hasil_wajib"]
            tujuan.write_text(
                tujuan.read_text(encoding="utf-8")
                + "\nTentukan matriks peluang transisi rantai Markov berikut.\n",
                encoding="utf-8",
            )
            return self._hasil(selesai=True)

        self.panggil.side_effect = tulis
        hasil = self.pipe._transkrip_gambar(
            self.gambar, slug="soal-03", judul="# T", konteks="",
            gabung_pilihan=False,
        )
        self.assertIsNotNone(hasil)
        self.assertIn("matriks peluang", hasil.read_text(encoding="utf-8"))

    def test_soal_hanya_gambar_gagal_tanpa_transkrip(self):
        with mock.patch.object(self.pipe, "_tahap_transkrip_soal", return_value=None):
            with self.assertRaises(pipeline.PipelineGagal):
                self.pipe._tahap_gambar_soal([self.gambar], "")

    def test_sebagian_gambar_gagal_tidak_menggagalkan_job(self):
        tersedia = self.root / "transkrip-soal-01.md"
        tersedia.write_text("# T\n\nIsi soal yang terbaca.\n", encoding="utf-8")
        with mock.patch.object(
            self.pipe, "_tahap_transkrip_soal", side_effect=[tersedia, None]
        ):
            hasil = self.pipe._tahap_gambar_soal([self.gambar, self.gambar], "")
        self.assertEqual(hasil, [tersedia])
        self.assertTrue(self.pipe.hasil.gagal)


if __name__ == "__main__":
    unittest.main()
