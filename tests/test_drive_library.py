import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from drive_library import DriveLibraryError, download_pdf, list_pdfs


class DriveLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.credentials_path = Path(self.temp_dir.name) / "service-account.json"
        self.credentials_path.write_text("{}", encoding="utf-8")
        self.environment = patch.dict(
            os.environ,
            {
                "GOOGLE_APPLICATION_CREDENTIALS": str(self.credentials_path),
                "GOOGLE_DRIVE_FOLDER_ID": "folder_123",
            },
            clear=True,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.addCleanup(self.temp_dir.cleanup)

        self.credentials = Mock(valid=True, token="test-token")
        self.credentials_patcher = patch(
            "drive_library.google.auth.load_credentials_from_file",
            return_value=(self.credentials, None),
        )
        self.credentials_patcher.start()
        self.addCleanup(self.credentials_patcher.stop)

    @staticmethod
    def response(status_code, payload=None, chunks=None):
        response = Mock(status_code=status_code)
        response.raise_for_status.return_value = None
        if payload is not None:
            response.json.return_value = payload
        if chunks is not None:
            response.iter_content.return_value = iter(chunks)
        return response

    @patch("drive_library.requests.get")
    def test_lists_only_pdf_files_from_drive_folder(self, get):
        get.return_value = self.response(
            200,
            {
                "files": [
                    {"id": "book_1", "name": "Kitob.pdf", "mimeType": "application/pdf"},
                    {"id": "folder_2", "name": "Papka", "mimeType": "application/vnd.google-apps.folder"},
                ]
            },
        )

        files = list_pdfs()

        self.assertEqual(files, [{"id": "book_1", "name": "Kitob.pdf"}])
        self.assertIn("'folder_123' in parents", get.call_args.kwargs["params"]["q"])

    @patch("drive_library.requests.get")
    def test_downloads_pdf_only_if_it_is_in_configured_folder(self, get):
        get.side_effect = [
            self.response(
                200,
                {
                    "id": "book_1",
                    "name": "Kitob",
                    "mimeType": "application/pdf",
                    "parents": ["folder_123"],
                    "size": "12",
                },
            ),
            self.response(200, chunks=[b"%PDF-1.7\nbody"]),
        ]

        document = download_pdf("book_1")

        self.assertEqual(document.name, "Kitob.pdf")
        self.assertTrue(document.read().startswith(b"%PDF-"))

    @patch("drive_library.requests.get")
    def test_refuses_file_outside_the_shared_folder(self, get):
        get.return_value = self.response(
            200,
            {
                "id": "book_1",
                "name": "Kitob.pdf",
                "mimeType": "application/pdf",
                "parents": ["another_folder"],
                "size": "12",
            },
        )

        with self.assertRaises(DriveLibraryError):
            download_pdf("book_1")
        get.assert_called_once()

    def test_reports_missing_drive_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(DriveLibraryError):
                list_pdfs()


if __name__ == "__main__":
    unittest.main()
