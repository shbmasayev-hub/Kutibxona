import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from requests.exceptions import RequestException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


class BotStub:
    def __init__(self):
        self.messages = []
        self.documents = []
        self.audios = []
        self.callback_answers = []
        self.command_sets = []

    def send_message(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text, kwargs))

    def send_document(self, chat_id, document, **kwargs):
        self.documents.append((chat_id, document, kwargs))

    def send_audio(self, chat_id, audio, **kwargs):
        self.audios.append((chat_id, audio, kwargs))

    def answer_callback_query(self, callback_id, text=None):
        self.callback_answers.append((callback_id, text))

    def set_my_commands(self, commands, language_code=None):
        self.command_sets.append((commands, language_code))

    def get_file(self, file_id):
        return SimpleNamespace(file_path=f"files/{file_id}")

    def download_file(self, file_path):
        return b"%PDF-1.7\nsample"


class BotBookMenuTests(unittest.TestCase):
    def setUp(self):
        self.original_bot = main.bot
        self.original_lang = main.user_lang.copy()
        main.bot = BotStub()
        main.user_lang[123] = "uz"

    def tearDown(self):
        main.bot = self.original_bot
        main.user_lang.clear()
        main.user_lang.update(self.original_lang)

    @patch(
        "main.list_local_pdfs",
        return_value=[
            {"id": "book_a", "name": "Birinchi.pdf"},
            {"id": "book_b", "name": "Ikkinchi.pdf"},
        ],
    )
    def test_book_menu_numbers_local_pdfs(self, list_pdfs_mock):
        main.show_book_menu(123, "uz")

        section_keyboard = main.bot.messages[0][2]["reply_markup"]
        self.assertEqual(section_keyboard.keyboard[0][0]["text"], "⬅️ Asosiy menyu")
        markup = main.bot.messages[1][2]["reply_markup"]
        buttons = [button for row in markup.keyboard for button in row]
        self.assertEqual(buttons[0].text, "1. 📄 Birinchi.pdf")
        self.assertEqual(buttons[1].text, "2. 📄 Ikkinchi.pdf")
        self.assertEqual(buttons[0].callback_data, "local:book_a")
        list_pdfs_mock.assert_called_once_with()

    @patch("main.download_local_pdf")
    def test_selected_local_pdf_is_sent(self, download_pdf_mock):
        document = io.BytesIO(b"%PDF-1.7")
        document.name = "Kitob.pdf"
        download_pdf_mock.return_value = document
        callback = SimpleNamespace(
            id="callback_1",
            data="local:book_a",
            message=SimpleNamespace(chat=SimpleNamespace(id=123)),
        )

        main.handle_book_callback(callback)

        download_pdf_mock.assert_called_once_with("book_a")
        self.assertEqual(main.bot.documents[0][0], 123)
        self.assertEqual(main.bot.documents[0][2]["caption"], "Kitob.pdf")
        self.assertEqual(main.bot.documents[0][2]["timeout"], 120)

    @patch(
        "main.list_audio_books",
        return_value=[{"id": "audio_a", "name": "Ertak.mp3"}],
    )
    def test_audio_menu_lists_audio_books(self, list_audio_mock):
        main.show_audio_menu(123, "uz")

        section_keyboard = main.bot.messages[0][2]["reply_markup"]
        self.assertEqual(section_keyboard.keyboard[0][0]["text"], "⬅️ Asosiy menyu")
        markup = main.bot.messages[1][2]["reply_markup"]
        buttons = [button for row in markup.keyboard for button in row]
        self.assertEqual(buttons[0].text, "1. 🎧 Ertak.mp3")
        self.assertEqual(buttons[0].callback_data, "audio:audio_a")
        list_audio_mock.assert_called_once_with()

    @patch("main.download_audio_book")
    def test_selected_audio_book_is_sent_as_audio(self, download_audio_mock):
        audio = io.BytesIO(b"audio data")
        audio.name = "Ertak.mp3"
        download_audio_mock.return_value = audio
        callback = SimpleNamespace(
            id="callback_2",
            data="audio:audio_a",
            message=SimpleNamespace(chat=SimpleNamespace(id=123)),
        )

        main.handle_audio_callback(callback)

        download_audio_mock.assert_called_once_with("audio_a")
        self.assertEqual(main.bot.audios[0][0], 123)
        self.assertEqual(main.bot.audios[0][2]["caption"], "Ertak.mp3")
        self.assertEqual(main.bot.audios[0][2]["timeout"], 120)

    @patch("main.download_local_pdf")
    def test_failed_pdf_send_shows_retry_message(self, download_pdf_mock):
        document = io.BytesIO(b"%PDF-1.7")
        document.name = "Kitob.pdf"
        download_pdf_mock.return_value = document
        main.bot.send_document = unittest.mock.Mock(
            side_effect=RequestException("network timeout")
        )
        callback = SimpleNamespace(
            id="callback_1",
            data="local:book_a",
            message=SimpleNamespace(chat=SimpleNamespace(id=123)),
        )

        main.handle_book_callback(callback)

        self.assertIn("PDF yuborilmadi", main.bot.messages[-1][1])

    @patch.dict(os.environ, {"TELEGRAM_ADMIN_IDS": "123"})
    @patch("main.save_pdf", return_value={"id": "book_a", "name": "Kitob.pdf"})
    def test_admin_can_upload_pdf(self, save_pdf_mock):
        message = SimpleNamespace(
            chat=SimpleNamespace(id=123, type="private"),
            from_user=SimpleNamespace(id=123),
            document=SimpleNamespace(
                file_id="telegram_file",
                file_name="Kitob.pdf",
                file_size=20,
            ),
        )

        main.handle_document_upload(message)

        save_pdf_mock.assert_called_once_with("Kitob.pdf", b"%PDF-1.7\nsample")
        self.assertEqual(main.bot.messages[-1][1], "Kitob yuklandi: Kitob.pdf")

    @patch.dict(os.environ, {"TELEGRAM_ADMIN_IDS": "123"})
    @patch("main.save_audio_book", return_value={"id": "audio_a", "name": "Ertak.mp3"})
    def test_admin_can_upload_audio_document(self, save_audio_mock):
        message = SimpleNamespace(
            chat=SimpleNamespace(id=123, type="private"),
            from_user=SimpleNamespace(id=123),
            document=SimpleNamespace(
                file_id="telegram_audio",
                file_name="Ertak.mp3",
                file_size=20,
            ),
        )

        main.handle_document_upload(message)

        save_audio_mock.assert_called_once_with("Ertak.mp3", b"%PDF-1.7\nsample")
        self.assertEqual(main.bot.messages[-1][1], "Audiokitob yuklandi: Ertak.mp3")

    @patch.dict(os.environ, {"TELEGRAM_ADMIN_IDS": "123"})
    def test_non_admin_cannot_upload_pdf(self):
        message = SimpleNamespace(
            chat=SimpleNamespace(id=123, type="private"),
            from_user=SimpleNamespace(id=456),
            document=SimpleNamespace(file_id="telegram_file", file_name="Kitob.pdf", file_size=20),
        )

        main.handle_document_upload(message)

        self.assertEqual(main.bot.messages[-1][1], "Fayl yuklash faqat bot admini uchun.")

    def test_myid_command_replies_with_telegram_user_id(self):
        message = SimpleNamespace(
            chat=SimpleNamespace(id=123),
            from_user=SimpleNamespace(id=456),
            text="/myid",
        )

        self.assertTrue(main.handle_commands(message))
        self.assertEqual(main.bot.messages[-1][1], "Telegram ID: 456")

    def test_privacy_command_explains_data_handling(self):
        message = SimpleNamespace(
            chat=SimpleNamespace(id=123),
            text="/privacy",
        )

        self.assertTrue(main.handle_commands(message))
        self.assertIn("alohida bazaga saqlamaydi", main.bot.messages[-1][1])

    def test_configure_bot_commands_includes_public_commands_and_russian(self):
        main.configure_bot_commands()

        self.assertEqual(len(main.bot.command_sets), 2)
        default_commands, default_language = main.bot.command_sets[0]
        russian_commands, russian_language = main.bot.command_sets[1]
        self.assertIsNone(default_language)
        self.assertEqual(russian_language, "ru")
        self.assertIn("privacy", [command.command for command in default_commands])
        self.assertEqual(
            [command.command for command in russian_commands],
            ["start", "menu", "help", "lang", "privacy"],
        )

    @patch.dict(os.environ, {"TELEGRAM_ADMIN_IDS": "123"})
    @patch("main.save_audio_book", return_value={"id": "audio_a", "name": "Qissa.m4a"})
    def test_admin_can_upload_telegram_audio(self, save_audio_mock):
        message = SimpleNamespace(
            chat=SimpleNamespace(id=123, type="private"),
            from_user=SimpleNamespace(id=123),
            audio=SimpleNamespace(
                file_id="telegram_audio",
                file_name="Qissa.m4a",
                file_size=20,
            ),
        )

        main.handle_audio_upload(message)

        save_audio_mock.assert_called_once_with("Qissa.m4a", b"%PDF-1.7\nsample")
        self.assertEqual(main.bot.messages[-1][1], "Audiokitob yuklandi: Qissa.m4a")

    def test_main_menu_contains_audio_books_button(self):
        main.show_main_menu(123, "uz")

        markup = main.bot.messages[-1][2]["reply_markup"]
        labels = [button["text"] for row in markup.keyboard for button in row]
        self.assertIn("🎧 Audiokitoblar", labels)

    def test_main_menu_contains_webapp_button_when_url_is_configured(self):
        with patch.object(main, "TELEGRAM_WEBAPP_URL", "https://kutibxona.example"):
            main.show_main_menu(123, "uz")

        markup = main.bot.messages[-1][2]["reply_markup"]
        buttons = [button for row in markup.keyboard for button in row]
        launcher = next(button for button in buttons if "web_app" in button)
        self.assertEqual(launcher["text"], "🚀 3D kutubxona")
        self.assertEqual(
            launcher["web_app"]["url"],
            "https://kutibxona.example",
        )

    def test_main_menu_hides_webapp_button_until_url_is_configured(self):
        with patch.object(main, "TELEGRAM_WEBAPP_URL", ""):
            main.show_main_menu(123, "uz")

        markup = main.bot.messages[-1][2]["reply_markup"]
        labels = [button["text"] for row in markup.keyboard for button in row]
        self.assertNotIn("🚀 3D kutubxona", labels)

    def test_group_menu_does_not_include_private_only_webapp_button(self):
        with patch.object(main, "TELEGRAM_WEBAPP_URL", "https://kutibxona.example"):
            main.show_main_menu(123, "uz", allow_webapp=False)

        markup = main.bot.messages[-1][2]["reply_markup"]
        buttons = [button for row in markup.keyboard for button in row]
        self.assertFalse(any("web_app" in button for button in buttons))

    def test_webapp_data_opens_selected_bot_section(self):
        message = SimpleNamespace(
            chat=SimpleNamespace(id=123),
            web_app_data=SimpleNamespace(
                data='{"action":"open","section":"audio"}',
            ),
        )

        with patch("main.show_audio_menu") as show_audio_mock:
            main.handle_webapp_data(message)

        show_audio_mock.assert_called_once_with(123, "uz")

    def test_webapp_data_rejects_unknown_section(self):
        message = SimpleNamespace(
            chat=SimpleNamespace(id=123),
            web_app_data=SimpleNamespace(
                data='{"action":"open","section":"arbitrary"}',
            ),
        )

        main.handle_webapp_data(message)

        self.assertIn("Bu bo‘lim mavjud emas", main.bot.messages[-1][1])

    def test_webapp_url_must_use_https(self):
        with patch.object(main, "TELEGRAM_WEBAPP_URL", "http://kutibxona.example"):
            with self.assertRaisesRegex(ValueError, "public HTTPS"):
                main.validate_telegram_webapp_url()

    def test_selecting_a_section_replaces_main_keyboard_with_back_button(self):
        message = SimpleNamespace(
            chat=SimpleNamespace(id=123),
            from_user=SimpleNamespace(id=123),
            text="👥 Umumiy resurslar",
        )

        main.handle_messages(message)

        text, kwargs = main.bot.messages[-1][1], main.bot.messages[-1][2]
        self.assertIn("👥 Umumiy resurslar", text)
        markup = kwargs["reply_markup"]
        self.assertEqual(markup.keyboard[0][0]["text"], "⬅️ Asosiy menyu")

    def test_teacher_section_lists_methodical_guides_and_official_resources(self):
        message = SimpleNamespace(
            chat=SimpleNamespace(id=123),
            from_user=SimpleNamespace(id=123),
            text="👩‍🏫 O‘qituvchilar",
        )

        main.handle_messages(message)

        text, kwargs = main.bot.messages[-1][1], main.bot.messages[-1][2]
        self.assertIn("metodik qo‘llanmalar", text)
        buttons = [
            button
            for row in kwargs["reply_markup"].keyboard
            for button in row
        ]
        callbacks = [button.callback_data for button in buttons if button.callback_data]
        self.assertEqual(
            callbacks,
            [
                "teacher:guide:lesson",
                "teacher:guide:differentiation",
                "teacher:guide:assessment",
                "teacher:back",
            ],
        )
        self.assertEqual(
            [button.url for button in buttons if button.url],
            [
                main.ZIYONET_LIBRARY_URL,
                main.ZIYONET_QA_URL,
                main.ZIYONET_SITES_URL,
            ],
        )

    def test_teacher_lesson_guide_shows_practical_steps_and_back_navigation(self):
        callback = SimpleNamespace(
            id="teacher_guide",
            data="teacher:guide:lesson",
            message=SimpleNamespace(chat=SimpleNamespace(id=123)),
        )

        main.handle_teacher_callback(callback)

        text, kwargs = main.bot.messages[-1][1], main.bot.messages[-1][2]
        self.assertIn("Darsni rejalash qo‘llanmasi", text)
        self.assertIn("PDF’lar alohida beriladi", text)
        buttons = [
            button
            for row in kwargs["reply_markup"].keyboard
            for button in row
        ]
        self.assertEqual(
            [button.callback_data for button in buttons],
            [
                "teacher:download:lesson:primary",
                "teacher:download:lesson:secondary",
                "teacher:home",
                "teacher:back",
            ],
        )

    def test_legacy_teacher_pdf_button_shows_separate_grade_choices(self):
        callback = SimpleNamespace(
            id="teacher_pdf",
            data="teacher:download:lesson",
            message=SimpleNamespace(chat=SimpleNamespace(id=123)),
        )

        main.handle_teacher_callback(callback)

        text, kwargs = main.bot.messages[-1][1], main.bot.messages[-1][2]
        self.assertIn("alohida qo‘llanmani tanlang", text)
        buttons = [
            button
            for row in kwargs["reply_markup"].keyboard
            for button in row
        ]
        self.assertEqual(
            [button.callback_data for button in buttons],
            [
                "teacher:download:lesson:primary",
                "teacher:download:lesson:secondary",
            ],
        )

    def test_teacher_pdf_download_sends_selected_grade_guide(self):
        for level, filename in (
            ("primary", "Darsni_rejalash_1-4_sinflar.pdf"),
            ("secondary", "Darsni_rejalash_5-11_sinflar.pdf"),
        ):
            callback = SimpleNamespace(
                id=f"teacher_pdf_{level}",
                data=f"teacher:download:lesson:{level}",
                message=SimpleNamespace(chat=SimpleNamespace(id=123)),
            )
            with self.subTest(level=level), tempfile.TemporaryDirectory() as directory:
                pdf_path = Path(directory) / "guide.pdf"
                pdf_path.write_bytes(b"%PDF-1.7\nseparate guide")
                with patch.dict(main.TEACHER_GUIDE_PDF_PATHS, {level: pdf_path}):
                    main.handle_teacher_callback(callback)

            self.assertEqual(len(main.bot.documents), 1)
            chat_id, document, kwargs = main.bot.documents.pop()
            self.assertEqual(chat_id, 123)
            self.assertEqual(document.name, filename)
            self.assertTrue(document.getvalue().startswith(b"%PDF-"))
            self.assertIn("alohida metodik qo‘llanma", kwargs["caption"])

    def test_both_expanded_teacher_pdfs_are_packaged(self):
        for level, pdf_path in main.TEACHER_GUIDE_PDF_PATHS.items():
            with self.subTest(level=level):
                content = pdf_path.read_bytes()
                self.assertTrue(content.startswith(b"%PDF-"))
                self.assertGreater(len(content), 50_000)

    def test_student_section_shows_grade_picker(self):
        message = SimpleNamespace(
            chat=SimpleNamespace(id=123),
            from_user=SimpleNamespace(id=123),
            text="🎒 O‘quvchilar",
        )

        main.handle_messages(message)

        text, kwargs = main.bot.messages[-1][1], main.bot.messages[-1][2]
        self.assertIn("Qaysi sinfda o‘qiysiz", text)
        buttons = [
            button
            for row in kwargs["reply_markup"].keyboard
            for button in row
        ]
        self.assertEqual(len([button for button in buttons if button.callback_data.startswith("students:grade:")]), 11)

    def test_student_grade_shows_subjects_for_that_grade(self):
        callback = SimpleNamespace(
            id="student_grade",
            data="students:grade:7",
            message=SimpleNamespace(chat=SimpleNamespace(id=123)),
        )

        main.handle_student_callback(callback)

        text, kwargs = main.bot.messages[-1][1], main.bot.messages[-1][2]
        self.assertIn("7-sinf uchun fanni tanlang", text)
        buttons = [
            button
            for row in kwargs["reply_markup"].keyboard
            for button in row
        ]
        self.assertIn(
            "students:subject:7:biologiya",
            [button.callback_data for button in buttons],
        )

    def test_student_subject_shows_study_guide_and_official_resource_link(self):
        callback = SimpleNamespace(
            id="student_subject",
            data="students:subject:7:biologiya",
            message=SimpleNamespace(chat=SimpleNamespace(id=123)),
        )

        main.handle_student_callback(callback)

        text, kwargs = main.bot.messages[-1][1], main.bot.messages[-1][2]
        self.assertIn("7-sinf · Biologiya", text)
        self.assertIn("Mashqlarni javobga qaramasdan mustaqil", text)
        self.assertIn("Biologiya", text)
        buttons = [
            button
            for row in kwargs["reply_markup"].keyboard
            for button in row
        ]
        self.assertEqual(
            [button.url for button in buttons[:3]],
            [
                main.ZIYONET_LIBRARY_URL,
                main.ZIYONET_AUDIO_URL,
                main.ZIYONET_QA_URL,
            ],
        )
        self.assertEqual(buttons[3].callback_data, "students:grade:7")


if __name__ == "__main__":
    unittest.main()
