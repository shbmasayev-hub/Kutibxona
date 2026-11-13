import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import local_library


class LocalLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp_dir.name)
        self.directory_patch = patch.object(local_library, "BOOKS_DIRECTORY", self.directory)
        self.directory_patch.start()

    def tearDown(self):
        self.directory_patch.stop()
        self.temp_dir.cleanup()

    def test_saved_pdf_is_listed_and_downloadable(self):
        saved = local_library.save_pdf("Kitob.pdf", b"%PDF-1.7\nsample")

        self.assertEqual(
            local_library.list_local_pdfs(),
            [{"id": saved["id"], "name": "Kitob.pdf"}],
        )
        downloaded = local_library.download_local_pdf(saved["id"])
        self.assertEqual(downloaded.name, "Kitob.pdf")
        self.assertEqual(downloaded.read(), b"%PDF-1.7\nsample")

    def test_rejects_non_pdf_extension_and_content(self):
        with self.assertRaises(local_library.LocalLibraryError):
            local_library.save_pdf("notes.txt", b"%PDF-1.7\nsample")
        with self.assertRaises(local_library.LocalLibraryError):
            local_library.save_pdf("fake.pdf", b"not a PDF")

    def test_rejects_files_over_library_limit(self):
        with patch.object(local_library, "MAX_LIBRARY_SIZE", 4):
            with self.assertRaises(local_library.LocalLibraryError):
                local_library.save_pdf("large.pdf", b"%PDF-1.7")


if __name__ == "__main__":
    unittest.main()
