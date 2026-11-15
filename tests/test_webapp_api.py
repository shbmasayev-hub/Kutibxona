import hashlib
import hmac
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from time import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


def signed_webapp_data(bot_token, user_id, auth_date):
    values = {
        "auth_date": str(auth_date),
        "user": json.dumps({"id": user_id}, separators=(",", ":")),
    }
    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(values.items())
    )
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    values["hash"] = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return urlencode(values)


class BookCatalogApiTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            main.BookCatalogRequestHandler,
        )
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.catalog = patch(
            "main.list_available_books",
            return_value=(
                [
                    {
                        "id": "book_a",
                        "name": "Kitob.pdf",
                        "source": "local",
                    }
                ],
                None,
            ),
        )
        self.catalog_mock = self.catalog.start()

    def tearDown(self):
        self.catalog.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_books_endpoint_returns_catalog_for_the_mini_app_origin(self):
        request = urllib.request.Request(
            f"{self.url}/api/books",
            headers={"Origin": main.TELEGRAM_WEBAPP_ORIGIN},
        )

        with urllib.request.urlopen(request) as response:
            data = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            self.assertEqual(
                response.headers["Access-Control-Allow-Origin"],
                main.TELEGRAM_WEBAPP_ORIGIN,
            )
            self.assertEqual(response.headers["Cache-Control"], "no-store")

        self.assertEqual(
            data,
            {"books": [{"id": "book_a", "name": "Kitob.pdf", "source": "local"}]},
        )

    def test_books_endpoint_does_not_allow_unconfigured_origins(self):
        request = urllib.request.Request(
            f"{self.url}/api/books",
            headers={"Origin": "https://not-kutibxona.example"},
        )

        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.status, 200)
            self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))

    def test_unknown_api_path_returns_404(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(f"{self.url}/api/unknown")

        self.assertEqual(raised.exception.code, 404)

    def test_library_failure_returns_service_unavailable(self):
        self.catalog_mock.side_effect = main.LocalLibraryError("Library unavailable")

        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(f"{self.url}/api/books")

        self.assertEqual(raised.exception.code, 503)

    def test_assistant_endpoint_rejects_missing_telegram_authentication(self):
        body = json.dumps(
            {"mode": "study", "question": "Savol", "language": "uz"}
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.url}/api/assistant",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Origin": main.TELEGRAM_WEBAPP_ORIGIN,
            },
            method="POST",
        )

        with patch.object(main, "TOKEN", "test-token"):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request)

        self.assertEqual(raised.exception.code, 401)

    def test_assistant_endpoint_accepts_signed_telegram_user(self):
        bot_token = "test-token"
        body = json.dumps(
            {"mode": "study", "question": "Savol", "language": "uz"}
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.url}/api/assistant",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Origin": main.TELEGRAM_WEBAPP_ORIGIN,
                "X-Telegram-Init-Data": signed_webapp_data(
                    bot_token,
                    123,
                    int(time()),
                ),
            },
            method="POST",
        )

        with (
            patch.object(main, "TOKEN", bot_token),
            patch("main._consume_ai_rate_limit", return_value=True),
            patch("main.generate_ai_answer", return_value="Javob") as generate_mock,
        ):
            with urllib.request.urlopen(request) as response:
                result = json.loads(response.read().decode("utf-8"))
                self.assertEqual(response.status, 200)
                self.assertEqual(
                    response.headers["Access-Control-Allow-Origin"],
                    main.TELEGRAM_WEBAPP_ORIGIN,
                )

        self.assertEqual(result, {"answer": "Javob"})
        generate_mock.assert_called_once_with(
            "Savol",
            "study",
            "uz",
            [{"id": "book_a", "name": "Kitob.pdf", "source": "local"}],
            selected_book=None,
        )
