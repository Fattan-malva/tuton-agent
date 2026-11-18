import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tuton import config, results


class ResultsDeleteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.output = self.base / "output" / "user_1"
        self.work = self.base / "_kerja" / "user_1"
        self.work.mkdir(parents=True)
        self.output.mkdir(parents=True)
        self.scope = config.scope(user_id="user_1")
        self.scope.__enter__()
        self.addCleanup(self.scope.__exit__, None, None, None)
        self.output_patch = patch.object(config, "OUTPUT_DIR", self.base / "output")
        self.work_patch = patch.object(config, "KERJA_DIR", self.base / "_kerja")
        self.output_patch.start()
        self.work_patch.start()
        self.addCleanup(self.output_patch.stop)
        self.addCleanup(self.work_patch.stop)
        self.remote = patch.object(results.supabase, "result_delete")
        self.remote.start()
        self.addCleanup(self.remote.stop)

    def test_delete_result_removes_local_docx_and_allows_regeneration(self):
        for root in (self.output, self.work):
            docx = root / "Course" / "sesi-8" / "result.docx"
            docx.parent.mkdir(parents=True)
            docx.write_bytes(b"docx")

        results.hapus("Course", "sesi-8", "result.docx")

        self.assertFalse((self.output / "Course" / "sesi-8" / "result.docx").exists())
        self.assertFalse((self.work / "Course" / "sesi-8" / "result.docx").exists())
        results.supabase.result_delete.assert_called_once_with("user_1", "Course", "sesi-8", "result.docx")

    def test_delete_course_removes_all_local_results(self):
        for root in (self.output, self.work):
            docx = root / "Course" / "sesi-8" / "result.docx"
            docx.parent.mkdir(parents=True)
            docx.write_bytes(b"docx")

        results.hapus("Course")

        self.assertFalse((self.output / "Course").exists())
        self.assertFalse((self.work / "Course").exists())
        results.supabase.result_delete.assert_called_once_with("user_1", "Course", "", "")

    def test_rejects_traversal(self):
        with self.assertRaises(ValueError):
            results.hapus("../other")
        results.supabase.result_delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
