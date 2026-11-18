"""Skill bawaan dipakai bersama, suntingan hanya milik akun yang mengedit."""

import unittest
from unittest import mock

from tuton import skills


def _akun(rows_by_user: dict[str, list[dict]], default: dict[str, str]):
    def _list(user_id):
        return rows_by_user.get(user_id, [])

    def _get(user_id, nama):
        return next((x for x in _list(user_id) if x["name"] == nama), None)

    def _save(user_id, nama, content):
        rows_by_user.setdefault(user_id, [])
        rows = [x for x in rows_by_user[user_id] if x["name"] != nama]
        rows.append({"name": nama, "content": content})
        rows_by_user[user_id] = rows

    def _delete(user_id, nama):
        rows_by_user[user_id] = [x for x in _list(user_id) if x["name"] != nama]

    return (
        mock.patch.object(skills.supabase, "skill_list", side_effect=_list),
        mock.patch.object(skills.supabase, "skill_get", side_effect=_get),
        mock.patch.object(skills.supabase, "skill_save", side_effect=_save),
        mock.patch.object(skills.supabase, "skill_delete", side_effect=_delete),
        mock.patch.object(
            skills.supabase, "skill_default", side_effect=lambda u: default.get(u, "")
        ),
        mock.patch.object(
            skills.supabase,
            "skill_set_default",
            side_effect=lambda u, n: default.__setitem__(u, n),
        ),
    )


class TestSkillPerAkun(unittest.TestCase):
    def test_bawaan_naskah_id_ada_dan_jadi_default(self):
        with mock.patch.object(skills.supabase, "skill_list", return_value=[]), \
                mock.patch.object(skills.supabase, "skill_default", return_value=""):
            daftar = skills.daftar("user-a")
            self.assertEqual(skills.default_id("user-a"), "naskah-id")
        entri = next(x for x in daftar if x["name"] == "naskah-id")
        self.assertTrue(entri["bawaan"])
        self.assertTrue(entri["default"])

    def test_suntingan_user_a_tidak_mengubah_user_b(self):
        rows: dict[str, list[dict]] = {}
        default: dict[str, str] = {}
        patches = _akun(rows, default)
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        skills.simpan("user-a", "naskah-id", "# versi A")
        self.assertEqual(skills.isi("user-a", "naskah-id"), "# versi A")
        self.assertNotEqual(skills.isi("user-b", "naskah-id"), "# versi A")
        self.assertIn("naskah-id", skills.isi("user-b", "naskah-id"))

        skills.hapus("user-a", "naskah-id")
        self.assertNotEqual(skills.isi("user-a", "naskah-id"), "# versi A")

    def test_skill_baru_bisa_jadi_default(self):
        rows: dict[str, list[dict]] = {}
        default: dict[str, str] = {}
        patches = _akun(rows, default)
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        skills.simpan("user-a", "gaya-kampus", "# ikuti pedoman kampus")
        skills.set_default("user-a", "gaya-kampus")
        self.assertEqual(skills.default_id("user-a"), "gaya-kampus")
        self.assertIn("gaya-kampus", skills.prompt("user-a"))
        # Akun lain tetap memakai bawaan.
        self.assertEqual(skills.default_id("user-b"), "naskah-id")

    def test_default_asing_ditolak(self):
        rows: dict[str, list[dict]] = {}
        default: dict[str, str] = {}
        patches = _akun(rows, default)
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        with self.assertRaises(ValueError):
            skills.set_default("user-a", "tidak-ada")
        self.assertEqual(default.get("user-a", ""), "")


if __name__ == "__main__":
    unittest.main()