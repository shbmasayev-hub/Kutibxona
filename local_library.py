import io
import re
import uuid
from pathlib import Path

BOOKS_DIRECTORY = Path(__file__).resolve().parent / "books" / "uploads"
MAX_UPLOAD_SIZE = 20 * 1024 * 1024
MAX_LIBRARY_SIZE = 49 * 1024 * 1024
BOOK_FILE_PATTERN = re.compile(r"(?P<id>[0-9a-f]{32})__(?P<name>.+\.pdf)\Z", re.IGNORECASE)
BOOK_ID_PATTERN = re.compile(r"[0-9a-f]{32}\Z", re.IGNORECASE)


class LocalLibraryError(Exception):
    """A safe, user-facing local book library error."""


def _safe_filename(file_name):
    name = re.split(r"[\\/]", file_name)[-1]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    if not name.lower().endswith(".pdf"):
        raise LocalLibraryError("Faqat PDF fayllarni yuklash mumkin.")
    if len(name) > 180:
        name = f"{name[:176]}.pdf"
    return name


def list_local_pdfs():
    if not BOOKS_DIRECTORY.is_dir():
        return []

    books = []
    try:
        for path in BOOKS_DIRECTORY.iterdir():
            match = BOOK_FILE_PATTERN.fullmatch(path.name)
            if path.is_file() and match:
                books.append({"id": match.group("id"), "name": match.group("name")})
    except OSError as error:
        raise LocalLibraryError("Mahalliy kitoblar papkasini o‘qib bo‘lmadi.") from error
    return sorted(books, key=lambda book: book["name"].casefold())


def save_pdf(file_name, content):
    if not isinstance(content, bytes):
        raise LocalLibraryError("PDF fayl ma'lumotini o'qib bo'lmadi.")
    if len(content) > MAX_LIBRARY_SIZE:
        raise LocalLibraryError("PDF fayl 49 MB dan kichik bo‘lishi kerak.")
    if not content.startswith(b"%PDF-"):
        raise LocalLibraryError("Yuborilgan fayl haqiqiy PDF emas.")

    safe_name = _safe_filename(file_name)
    BOOKS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    book_id = uuid.uuid4().hex
    destination = BOOKS_DIRECTORY / f"{book_id}__{safe_name}"
    temporary = BOOKS_DIRECTORY / f".{book_id}.tmp"
    try:
        temporary.write_bytes(content)
        temporary.replace(destination)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise LocalLibraryError("Kitobni saqlab bo‘lmadi.") from error
    return {"id": book_id, "name": safe_name}


def download_local_pdf(book_id):
    if not isinstance(book_id, str) or not BOOK_ID_PATTERN.fullmatch(book_id):
        raise LocalLibraryError("Kitob identifikatori noto‘g‘ri.")

    matches = [
        path
        for path in BOOKS_DIRECTORY.glob(f"{book_id}__*.pdf")
        if path.is_file() and BOOK_FILE_PATTERN.fullmatch(path.name)
    ]
    if len(matches) != 1:
        raise LocalLibraryError("Kitob mahalliy kutubxonada topilmadi.")

    path = matches[0]
    try:
        content = path.read_bytes()
    except OSError as error:
        raise LocalLibraryError("Kitob faylini o‘qib bo‘lmadi.") from error
    if len(content) > MAX_LIBRARY_SIZE or not content.startswith(b"%PDF-"):
        raise LocalLibraryError("Saqlangan fayl haqiqiy PDF emas yoki hajmi katta.")

    document = io.BytesIO(content)
    document.name = path.name.split("__", 1)[1]
    return document
