import io
import os
import re
from pathlib import Path

import google.auth
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
import requests

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
DRIVE_API_URL = "https://www.googleapis.com/drive/v3/files"
MAX_PDF_SIZE = 49 * 1024 * 1024
FILE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,58}\Z")


class DriveLibraryError(Exception):
    """A safe, user-facing Google Drive library error."""


def _drive_access():
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    if not credentials_path or not folder_id:
        raise DriveLibraryError(
            "Google Drive sozlanmagan. GOOGLE_APPLICATION_CREDENTIALS va "
            "GOOGLE_DRIVE_FOLDER_ID muhit o'zgaruvchilarini kiriting."
        )
    if not Path(credentials_path).is_file():
        raise DriveLibraryError(
            "Google service account JSON fayli topilmadi. "
            "GOOGLE_APPLICATION_CREDENTIALS yo'lini tekshiring."
        )
    if not FILE_ID_PATTERN.fullmatch(folder_id):
        raise DriveLibraryError("GOOGLE_DRIVE_FOLDER_ID noto'g'ri formatda.")

    try:
        credentials, _ = google.auth.load_credentials_from_file(
            credentials_path,
            scopes=[DRIVE_SCOPE],
        )
        if not credentials.valid:
            credentials.refresh(Request())
    except (GoogleAuthError, OSError, ValueError) as error:
        raise DriveLibraryError(
            "Google Drive hisob ma'lumotlarini tekshirib bo'lmadi. "
            "Service account JSON faylini va Drive API sozlamasini tekshiring."
        ) from error

    if not credentials.token:
        raise DriveLibraryError("Google Drive uchun kirish tokeni olinmadi.")
    return credentials.token, folder_id


def _get(url, token, params=None, stream=False):
    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=(10, 60),
            stream=stream,
        )
    except requests.RequestException as error:
        raise DriveLibraryError("Google Drive bilan bog'lanib bo'lmadi.") from error

    if response.status_code in (401, 403):
        raise DriveLibraryError(
            "Google Drive ruxsat bermadi. Papka service account emailiga "
            "Viewer sifatida ulashilganini va Drive API yoqilganini tekshiring."
        )
    if response.status_code == 404:
        raise DriveLibraryError(
            "Google Drive papkasi yoki fayli topilmadi. Papka ID sini tekshiring."
        )
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        raise DriveLibraryError(
            f"Google Drive so'roviga javob bermadi (HTTP {response.status_code})."
        ) from error
    return response


def list_pdfs():
    token, folder_id = _drive_access()
    files = []
    page_token = None

    while True:
        params = {
            "q": (
                f"'{folder_id}' in parents and "
                "mimeType = 'application/pdf' and trashed = false"
            ),
            "pageSize": 1000,
            "orderBy": "name",
            "fields": "nextPageToken,files(id,name,mimeType)",
        }
        if page_token:
            params["pageToken"] = page_token
        response = _get(DRIVE_API_URL, token, params=params)
        try:
            page = response.json()
        except ValueError as error:
            raise DriveLibraryError("Google Drive noto'g'ri javob qaytardi.") from error

        for item in page.get("files", []):
            file_id = item.get("id", "")
            name = item.get("name", "")
            if (
                item.get("mimeType") == "application/pdf"
                and isinstance(file_id, str)
                and FILE_ID_PATTERN.fullmatch(file_id)
                and isinstance(name, str)
                and name.strip()
            ):
                files.append({"id": file_id, "name": name})

        page_token = page.get("nextPageToken")
        if not page_token:
            return files


def download_pdf(file_id):
    if not isinstance(file_id, str) or not FILE_ID_PATTERN.fullmatch(file_id):
        raise DriveLibraryError("Kitob identifikatori noto'g'ri.")

    token, folder_id = _drive_access()
    metadata_response = _get(
        f"{DRIVE_API_URL}/{file_id}",
        token,
        params={"fields": "id,name,mimeType,parents,trashed,size"},
    )
    try:
        metadata = metadata_response.json()
    except ValueError as error:
        raise DriveLibraryError("Google Drive noto'g'ri javob qaytardi.") from error

    if (
        metadata.get("id") != file_id
        or metadata.get("mimeType") != "application/pdf"
        or metadata.get("trashed")
        or folder_id not in (metadata.get("parents") or [])
    ):
        raise DriveLibraryError("Bu PDF sozlangan kitoblar papkasida topilmadi.")

    try:
        file_size = int(metadata.get("size", 0))
    except (TypeError, ValueError) as error:
        raise DriveLibraryError("PDF fayl hajmini aniqlab bo'lmadi.") from error
    if file_size > MAX_PDF_SIZE:
        raise DriveLibraryError("PDF Telegram orqali yuborish uchun juda katta (49 MB dan ortiq).")

    response = _get(
        f"{DRIVE_API_URL}/{file_id}",
        token,
        params={"alt": "media"},
        stream=True,
    )
    document = io.BytesIO()
    try:
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            document.write(chunk)
            if document.tell() > MAX_PDF_SIZE:
                raise DriveLibraryError(
                    "PDF Telegram orqali yuborish uchun juda katta (49 MB dan ortiq)."
                )
    except requests.RequestException as error:
        raise DriveLibraryError("Google Drive faylini yuklab bo'lmadi.") from error

    if not document.getvalue().startswith(b"%PDF-"):
        raise DriveLibraryError("Drive fayli haqiqiy PDF formatida emas.")

    name = metadata.get("name", "kitob.pdf")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    document.name = name or "kitob.pdf"
    document.seek(0)
    return document
