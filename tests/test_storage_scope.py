"""Uji perilaku baru: enkripsi cookie dan provider per akun.

Tidak ada dependensi uji di `requirements.txt`, jadi berkas ini memakai
`unittest` bawaan dan bisa dijalankan langsung tanpa instalasi apa pun:

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tuton import config, crypto, runtime_config, supabase  # noqa: E402


class UjiCrypto(unittest.TestCase):
    def test_bolak_balik(self):
        token = crypto.enkripsi("MoodleSession-abc")
        self.assertTrue(token.startswith(crypto.AWALAN))
        self.assertNotIn("MoodleSession-abc", token)
        self.assertEqual(crypto.dekripsi(token), "MoodleSession-abc")

    def test_nilai_kosong(self):
        self.assertEqual(crypto.enkripsi(""), "")
        self.assertEqual(crypto.dekripsi(""), "")

    def test_plaintext_lama_dipertahankan(self):
        # Data sebelum enkripsi diaktifkan harus tetap terbaca, bukan hilang.
        self.assertEqual(crypto.dekripsi("cookie-lama"), "cookie-lama")
        self.assertFalse(crypto.terenkripsi("cookie-lama"))

    def test_enkripsi_idempoten(self):
        sekali = crypto.enkripsi("abc")
        self.assertEqual(crypto.enkripsi(sekali), sekali)

    def test_kunci_salah_tidak_melempar(self):
        with mock.patch.object(config, "env", lambda nama, bawaan="": "bukan-kunci"):
            self.assertFalse(crypto.tersedia())
            self.assertEqual(crypto.dekripsi(crypto.AWALAN + "rusak"), "")


class UjiCookieTersimpan(unittest.TestCase):
    def test_simpan_menulis_terenkripsi(self):
        dikirim: dict = {}

        class Respons:
            ok = True
            status_code = 200
            text = ""

        def fake_post(url, **kw):
            dikirim.update(kw.get("json") or {})
            return Respons()

        with mock.patch.object(supabase.requests, "post", fake_post), \
             mock.patch.object(supabase, "aktif", lambda: True):
            supabase.simpan("user_A", {"email": "a@x", "name": "A"}, {"cookie_moodle": "abc123"})

        nilai = dikirim["cookie_moodle"]
        self.assertTrue(crypto.terenkripsi(nilai))
        self.assertEqual(crypto.dekripsi(nilai), "abc123")

    def test_baris_plaintext_dienkripsi_ulang_saat_dibaca(self):
        ditambal: dict = {}

        class Respons:
            ok = True
            status_code = 200
            text = ""
            def __init__(self, isi=None):
                self._isi = isi
            def json(self):
                return self._isi if self._isi is not None else []

        with mock.patch.object(
            supabase.requests, "get",
            lambda *a, **k: Respons([{"cookie_moodle": "plain-lama"}]),
        ), mock.patch.object(
            supabase.requests, "patch",
            lambda *a, **k: (ditambal.update(k.get("json") or {}), Respons())[1],
        ), mock.patch.object(supabase, "aktif", lambda: True):
            row = supabase._get("user_A")

        self.assertEqual(row["cookie_moodle"], "plain-lama")
        self.assertTrue(crypto.terenkripsi(ditambal["cookie_moodle"]))


class UjiProviderPerUser(unittest.TestCase):
    PROVIDER = {
        "providers": [
            {"id": "p1", "name": "P1", "base_url": "https://x/v1",
             "api_key": "sk-rahasia", "models": ["m1"]}
        ],
        "agents": {"worker": "p1/m1"},
    }

    def test_web_memakai_provider_scope_bukan_berkas(self):
        data = {"providers": [], "agents": {}}
        with config.scope(user_id="user_A", provider_data=data):
            self.assertEqual(runtime_config.providers(), [])
            self.assertEqual(runtime_config.semua_model(), [])

    def test_akun_lain_tidak_melihat_isi_akun_pertama(self):
        with config.scope(user_id="user_A", provider_data=self.PROVIDER):
            self.assertEqual(runtime_config.provider("p1")["api_key"], "sk-rahasia")
        with config.scope(user_id="user_B", provider_data={"providers": [], "agents": {}}):
            self.assertIsNone(runtime_config.provider("p1"))

    def test_simpan_web_ke_supabase(self):
        ditulis: dict = {}
        with mock.patch.object(
            supabase, "providers_simpan",
            lambda uid, data: ditulis.update(uid=uid, data=data),
        ):
            with config.scope(user_id="user_A", provider_data={"providers": [], "agents": {}}):
                runtime_config.simpan(self.PROVIDER)
        self.assertEqual(ditulis["uid"], "user_A")
        self.assertEqual(ditulis["data"]["providers"][0]["id"], "p1")

    def test_cli_tetap_memakai_berkas(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime.json"
            path.write_text(json.dumps(self.PROVIDER), encoding="utf-8")
            with mock.patch.object(runtime_config, "RUNTIME_FILE", path):
                self.assertIsNone(config.current_provider_data())
                self.assertEqual(runtime_config.provider("p1")["api_key"], "sk-rahasia")
                self.assertEqual(runtime_config.model_agent("worker"), "p1/m1")

    def test_scope_bawaan_kosong_untuk_cli(self):
        self.assertIsNone(config.current_provider_data())


class UjiPathHasil(unittest.TestCase):
    def test_path_menolak_bagian_liar(self):
        for buruk in ("", ".", "..", "a/b"):
            with self.assertRaises(ValueError):
                supabase._result_path("user_A", buruk, "sesi-1", "x.docx")

    def test_path_benar(self):
        self.assertEqual(
            supabase._result_path("user_A", "Basis-Data-64", "sesi-2", "x.docx"),
            "user_A/Basis-Data-64/sesi-2/x.docx",
        )

    def test_unduh_menolak_path_user_lain(self):
        with mock.patch.object(supabase.requests, "get") as get:
            self.assertIsNone(supabase.result_download("user_A", "user_B/x/sesi-1/y.docx"))
        get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
