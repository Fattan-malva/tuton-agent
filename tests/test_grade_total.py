import unittest
from unittest.mock import Mock

from tuton.courses import nilai_total_mata_kuliah


class TestNilaiTotal(unittest.TestCase):
    def test_baca_nilai_total_dari_grade_report(self):
        klien = Mock()
        klien.base_url = "https://elearning.ut.ac.id"
        klien.ambil.return_value.html = """
        <table>
          <tr><th>Nilai Total (Tugas+Diskusi+Kehadiran)</th>
              <td class="column-grade">78,50</td></tr>
        </table>
        """
        self.assertEqual(nilai_total_mata_kuliah(klien, "42"), 78.5)
        klien.ambil.assert_called_once_with(
            "https://elearning.ut.ac.id/grade/report/user/index.php?id=42"
        )

    def test_nilai_tidak_ada_tetap_none(self):
        klien = Mock()
        klien.base_url = "https://elearning.ut.ac.id"
        klien.ambil.return_value.html = "<table></table>"
        self.assertIsNone(nilai_total_mata_kuliah(klien, "42"))


if __name__ == "__main__":
    unittest.main()
