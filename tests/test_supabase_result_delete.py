import unittest
from unittest import mock

from tuton import supabase


class Response:
    def __init__(self, data=None, ok=True, status_code=200, text=""):
        self.data = data
        self.ok = ok
        self.status_code = status_code
        self.text = text

    def json(self):
        return self.data


def _row(sesi, nama):
    return {
        "user_id": "u1", "slug": "course", "sesi": sesi,
        "nama": nama, "storage_path": f"u1/course/{sesi}/{nama}",
    }


class TestResultDelete(unittest.TestCase):
    def setUp(self):
        self.calls = []

    def fake_get(self, page_by_offset):
        def get(url, **kw):
            assert kw["params"]["user_id"] == "eq.u1"
            self.calls.append(("metadata", kw["params"]))
            return Response(page_by_offset.get(kw["params"]["offset"], []))
        return get

    def fake_post(self, items_by_prefix):
        def post(url, **kw):
            body = kw["json"]
            self.calls.append(("storage", body["prefix"], body["offset"]))
            if body["offset"]:
                return Response([])
            return Response(items_by_prefix.get(body["prefix"], []))
        return post

    def test_paginates_metadata_and_deletes_session_objects_including_orphans(self):
        get = self.fake_get({
            "0": [_row("sesi-1", "a.docx")] * 1000,
            "1000": [_row("sesi-2", "b.docx")],
        })
        post = self.fake_post({
            "u1/course": [
                {"name": "sesi-1", "id": None},
                {"name": "sesi-2", "id": None},
            ],
            "u1/course/sesi-1": [
                {"name": "a.docx", "id": "obj-a"},
                {"name": "orphan.docx", "id": "obj-o"},
            ],
            "u1/course/sesi-2": [{"name": "b.docx", "id": "obj-b"}],
        })
        with mock.patch.object(supabase, "aktif", return_value=True), \
                mock.patch.object(supabase.requests, "get", side_effect=get), \
                mock.patch.object(supabase.requests, "post", side_effect=post), \
                mock.patch.object(supabase.requests, "delete", return_value=Response()) as delete:
            supabase.result_delete("u1", "course", "sesi-1")

        self.assertEqual(
            [c[1]["offset"] for c in self.calls if c[0] == "metadata"],
            ["0", "1000", "1001"],
        )
        self.assertEqual(
            sorted({c[1] for c in self.calls if c[0] == "storage"}),
            ["u1/course", "u1/course/sesi-1", "u1/course/sesi-2"],
        )
        storage_delete, metadata_delete = delete.call_args_list
        self.assertEqual(storage_delete.kwargs["json"]["prefixes"], [
            "u1/course/sesi-1/a.docx", "u1/course/sesi-1/orphan.docx",
        ])
        self.assertEqual(metadata_delete.kwargs["params"], {
            "user_id": "eq.u1", "slug": "eq.course", "sesi": "eq.sesi-1",
        })

    def test_storage_read_failure_keeps_metadata(self):
        post = mock.Mock(return_value=Response(ok=False, status_code=500))
        with mock.patch.object(supabase, "aktif", return_value=True), \
                mock.patch.object(supabase.requests, "get", return_value=Response([])), \
                mock.patch.object(supabase.requests, "post", post), \
                mock.patch.object(supabase.requests, "delete") as delete:
            with self.assertRaisesRegex(ValueError, "pembacaan objek"):
                supabase.result_delete("u1", "course")
        delete.assert_not_called()

    def test_metadata_failure_is_reported(self):
        def delete(url, **kw):
            if url.endswith("/user_results"):
                return Response(ok=False, status_code=500, text="failed")
            return Response()

        # Tanpa objek, tak ada hapus Storage: kegagalan metadata tidak boleh
        # tertukar dengan "tidak ditemukan".
        with mock.patch.object(supabase, "aktif", return_value=True), \
                mock.patch.object(supabase.requests, "get", return_value=Response([])), \
                mock.patch.object(supabase.requests, "post", return_value=Response([])), \
                mock.patch.object(supabase.requests, "delete", side_effect=delete):
            with self.assertRaisesRegex(ValueError, "metadata"):
                supabase.result_delete("u1", "course")

    def test_result_exists_exact_and_remote_errors_raise(self):
        get = self.fake_get({"0": [_row("sesi-1", "a.docx"), _row("sesi-1", "other.docx")]})
        with mock.patch.object(supabase, "aktif", return_value=True), \
                mock.patch.object(supabase.requests, "get", side_effect=get):
            self.assertTrue(supabase.result_exists("u1", "course", "sesi-1", "a.docx"))
            self.assertFalse(supabase.result_exists("u1", "course", "sesi-1", "missing.docx"))

        with mock.patch.object(supabase, "aktif", return_value=True), \
                mock.patch.object(supabase.requests, "get",
                                  return_value=Response(ok=False, status_code=503)):
            with self.assertRaisesRegex(ValueError, "pembacaan hasil"):
                supabase.result_exists("u1", "course", "sesi-1", "a.docx")

    def test_result_exists_rejects_invalid_path(self):
        with mock.patch.object(supabase, "aktif", return_value=True):
            with self.assertRaises(ValueError):
                supabase.result_exists("u1", "../other", "sesi-1", "a.docx")


if __name__ == "__main__":
    unittest.main()
