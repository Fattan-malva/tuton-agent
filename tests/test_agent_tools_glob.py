"""Pola glob absolut dari model harus dinormalisasi, bukan menggagalkan job."""

import tempfile
import unittest
from pathlib import Path

from tuton import agent_tools


class UjiGlobAbsolut(unittest.TestCase):
    def test_pola_absolut_di_dalam_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp).resolve()
            (cwd / "_kerja" / "x").mkdir(parents=True)
            berkas = cwd / "_kerja" / "x" / "peta.md"
            berkas.write_text("# peta\n", encoding="utf-8")

            hasil = agent_tools.jalankan(
                "glob", {"pattern": str(cwd / "_kerja" / "**" / "*.md")}, cwd
            )
            self.assertIn("_kerja/x/peta.md", hasil)

    def test_pola_absolut_di_luar_cwd_ditolak(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp).resolve()
            hasil = agent_tools.jalankan("glob", {"pattern": "/etc/**/*.conf"}, cwd)
            self.assertTrue(hasil.startswith("GALAT:"))


if __name__ == "__main__":
    unittest.main()