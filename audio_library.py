import hashlib
import io
import re
import uuid
from pathlib import Path

AUDIO_DIRECTORY = Path(__file__).resolve().parent / "books" / "audio"
MAX_AUDIO_SIZE = 49 * 1024 * 1024
SUPPORTED_AUDIO_EXTENSIONS = frozenset({".mp3", ".m4a"})
AUDIO_ID_PATTERN = re.compile(r"[0-9a-f]{32}\Z", re.IGNORECASE)
STORED_AUDIO_PATTERN = re.compile(
    r"(?P<id>[0-9a-f]{32})__(?P<name>.+\.(?:mp3|m4a))\Z",
    re.IGNORECASE,
)


class AudioLibraryError(Exception):
    """A safe, user-facing audio library error."""


def _safe_audio_filename(file_name):
    name = re.split(r"[\\/]", file_name)[-1]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    extension = Path(name).suffix.lower()
    if extension not in SUPPORTED_AUDIO_EXTENSIONS:
        raise AudioLibraryError("Faqat MP3 yoki M4A audiokitoblarni yuklash mumkin.")
    if len(name) > 180:
        name = f"{name[:180 - len(extension)]}{extension}"
    return name


def _audio_id(path):
    match = STORED_AUDIO_PATTERN.fullmatch(path.name)
    if match:
        return match.group("id"), match.group("name")
    audio_id = hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:32]
    return audio_id, path.name


def list_audio_books():
    if not AUDIO_DIRECTORY.is_dir():
        return []

    books = []
    try:
        for path in AUDIO_DIRECTORY.iterdir():
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
                continue
            audio_id, name = _audio_id(path)
            books.append({"id": audio_id, "name": name})
    except OSError as error:
        raise AudioLibraryError("Audiokitoblar papkasini o‘qib bo‘lmadi.") from error
    return sorted(books, key=lambda book: book["name"].casefold())


def save_audio_book(file_name, content):
    if not isinstance(content, bytes) or not content:
        raise AudioLibraryError("Audio fayl ma'lumotini o‘qib bo‘lmadi.")
    if len(content) > MAX_AUDIO_SIZE:
        raise AudioLibraryError("Audiokitob 49 MB dan kichik bo‘lishi kerak.")

    safe_name = _safe_audio_filename(file_name)
    AUDIO_DIRECTORY.mkdir(parents=True, exist_ok=True)
    audio_id = uuid.uuid4().hex
    destination = AUDIO_DIRECTORY / f"{audio_id}__{safe_name}"
    temporary = AUDIO_DIRECTORY / f".{audio_id}.tmp"
    try:
        temporary.write_bytes(content)
        temporary.replace(destination)
    except OSError as error:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise AudioLibraryError("Audiokitobni saqlab bo‘lmadi.") from error
    return {"id": audio_id, "name": safe_name}


def download_audio_book(audio_id):
    if not isinstance(audio_id, str) or not AUDIO_ID_PATTERN.fullmatch(audio_id):
        raise AudioLibraryError("Audiokitob identifikatori noto‘g‘ri.")
    if not AUDIO_DIRECTORY.is_dir():
        raise AudioLibraryError("Audiokitob kutubxonasi bo‘sh.")

    matches = []
    try:
        for path in AUDIO_DIRECTORY.iterdir():
            if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
                stored_id, name = _audio_id(path)
                if stored_id == audio_id:
                    matches.append((path, name))
    except OSError as error:
        raise AudioLibraryError("Audiokitoblar papkasini o‘qib bo‘lmadi.") from error

    if len(matches) != 1:
        raise AudioLibraryError("Audiokitob kutubxonada topilmadi.")

    path, name = matches[0]
    try:
        content = path.read_bytes()
    except OSError as error:
        raise AudioLibraryError("Audiokitob faylini o‘qib bo‘lmadi.") from error
    if not content or len(content) > MAX_AUDIO_SIZE:
        raise AudioLibraryError("Audiokitob bo‘sh yoki hajmi 49 MB dan katta.")

    audio = io.BytesIO(content)
    audio.name = name
    return audio
