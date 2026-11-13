# Google Drive book library

The bot lists PDF files from one Google Drive folder and sends the selected
file. Only add books that you are allowed to redistribute.

## Uploading books through Telegram

The bot can also store books locally without Google Cloud. Set the
`TELEGRAM_ADMIN_IDS` user environment variable to the comma-separated Telegram
user IDs allowed to upload, then restart the bot. Send `/myid` to the bot to
find your ID. An admin can then send PDF files to the bot in a private chat;
uploads are stored under `books/uploads/` and appear in the reader menu.
Bot uploads are limited to 20 MB per file; the library can send PDFs up to
49 MB. Uploaded PDFs are ignored by Git so they are not added to commits.

## Audio books

Place `.mp3` or `.m4a` files in `books/audio/`, or send them to the bot as an
admin in a private chat. Audio files appear under the audio-books menu and are
sent using Telegram's audio player. Bot uploads are limited to 20 MB; local
audio files up to 49 MB can be sent. The audio folder is ignored by Git.

## One-time setup

1. In Google Cloud Console, create or select a project and enable the Google
   Drive API.
2. Create a service account and download its JSON key. Keep the key outside the
   repository, for example at
   `%APPDATA%\Kutibxona\drive-service-account.json`.
3. Share only the books folder with the service account email as a Viewer.
4. Copy the folder ID from its Google Drive URL and set these user environment
   variables in PowerShell:

   ```powershell
   [Environment]::SetEnvironmentVariable(
     "GOOGLE_APPLICATION_CREDENTIALS",
     "$env:APPDATA\Kutibxona\drive-service-account.json",
     "User"
   )
   [Environment]::SetEnvironmentVariable(
     "GOOGLE_DRIVE_FOLDER_ID",
     "YOUR_DRIVE_FOLDER_ID",
     "User"
   )
   ```

5. Restart the bot so it receives the new environment settings.

The bot requests read-only Drive access, only lists PDF files directly inside
the configured folder, and limits downloads to 49 MB. Never commit or share the
service account JSON key.
