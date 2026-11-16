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


class TestTemplateDefault(unittest.TestCase):
    """Default boleh template bawaan dan tidak menimpa isi template kustom."""

    def test_bawaan_boleh_jadi_default(self):
        from server import app
        with mock.patch.object(app.templates, "resolve", return_value={"id": "ringkas"}), \
                mock.patch.object(app.supabase, "template_set_default") as simpan, \
                mock.patch.object(app.supabase, "template_save") as tulis:
            app._template_default({"id": "ringkas"})
        simpan.assert_called_once_with("", "ringkas")
        tulis.assert_not_called()

    def test_id_asing_ditolak(self):
        from server import app
        with mock.patch.object(app.templates, "resolve", side_effect=ValueError("Template tidak ditemukan.")), \
                mock.patch.object(app.supabase, "template_set_default") as simpan:
            with self.assertRaises(ValueError):
                app._template_default({"id": "tidak-ada"})
        simpan.assert_not_called()


if __name__ == "__main__":
    unittest.main()
