import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audio_library


class AudioLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp_dir.name)
        self.directory_patch = patch.object(audio_library, "AUDIO_DIRECTORY", self.directory)
        self.directory_patch.start()

    def tearDown(self):
        self.directory_patch.stop()
        self.temp_dir.cleanup()

    def test_saved_audio_is_listed_and_downloadable(self):
        saved = audio_library.save_audio_book("Ertak.mp3", b"audio-data")

        self.assertEqual(
            audio_library.list_audio_books(),
            [{"id": saved["id"], "name": "Ertak.mp3"}],
        )
        downloaded = audio_library.download_audio_book(saved["id"])
        self.assertEqual(downloaded.name, "Ertak.mp3")
        self.assertEqual(downloaded.read(), b"audio-data")

    def test_audio_files_placed_directly_in_folder_are_available(self):
        direct_file = self.directory / "Qissa.m4a"
        direct_file.write_bytes(b"audio-data")

        book = audio_library.list_audio_books()[0]
        downloaded = audio_library.download_audio_book(book["id"])

        self.assertEqual(book["name"], "Qissa.m4a")
        self.assertEqual(downloaded.read(), b"audio-data")

    def test_rejects_unsupported_audio_format(self):
        with self.assertRaises(audio_library.AudioLibraryError):
            audio_library.save_audio_book("Audio.wav", b"audio-data")

    def test_rejects_audio_over_library_limit(self):
        with patch.object(audio_library, "MAX_AUDIO_SIZE", 4):
            with self.assertRaises(audio_library.AudioLibraryError):
                audio_library.save_audio_book("large.mp3", b"audio-data")


if __name__ == "__main__":
    unittest.main()
