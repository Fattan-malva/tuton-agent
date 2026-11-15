import unittest
from unittest import mock

from tuton import templates


class TestTemplatesMemakaiIdPengguna(unittest.TestCase):
    """Template selalu dipanggil dengan user-id string, bukan dict user.

    Bug lama: `_pengguna_sekarang()` (dict) dilewatkan sebagai user_id, sehingga
    template kustom tidak termuat dan "Jadikan default" menulis dict ke Supabase.
    """

    def test_daftar_meneruskan_string_ke_supabase(self):
        with mock.patch.object(templates.supabase, "template_list", return_value=[]) as lst:
            templates.daftar("user-1")
        lst.assert_called_once_with("user-1")

    def test_resolve_meneruskan_string_ke_supabase(self):
        with mock.patch.object(templates.supabase, "template_default", return_value="") as dflt:
            templates.resolve("user-1")
        dflt.assert_called_once_with("user-1")

    def test_id_pengguna_dari_konteks_login(self):
        from server import app
        token = app._PENGGUNA.set({"id": "user-1", "email": "x@y"})
        try:
            self.assertEqual(app._id_pengguna(), "user-1")
        finally:
            app._PENGGUNA.reset(token)

    def test_id_pengguna_kosong_tanpa_login(self):
        from server import app
        self.assertEqual(app._id_pengguna(), "")


if __name__ == "__main__":
    unittest.main()
