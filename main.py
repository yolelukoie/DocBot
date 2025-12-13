import os
import json
import io
import logging

import requests
from flask import Flask, request, jsonify

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Конфиг через переменные окружения ---

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT", "")
if not TELEGRAM_TOKEN:
    logger.warning("TELEGRAM_TOKEN is not set. Bot will not work until it's provided.")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Путь к шаблону и суффикс для имени файла на диске
TEMPLATE_PATH = os.environ.get("TEMPLATE_PATH", "Соглашение.pdf")
DOCUMENT_SUFFIX = os.environ.get("DOCUMENT_SUFFIX", "Соглашение")

# ID папки на Google Диске
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "")

# OAuth-конфиг для доступа к Google Drive от имени реального пользователя
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN", "")

drive_service = None


def get_drive_service():
    """Создаём Drive-клиент от имени реального пользователя по OAuth."""
    global drive_service
    if drive_service is not None:
        return drive_service

    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REFRESH_TOKEN):
        raise RuntimeError(
            "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN must be set"
        )

    creds = Credentials(
        token=None,
        refresh_token=GOOGLE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=SCOPES,
    )

    drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
    return drive_service


# --- Вспомогательные функции Telegram ---


def telegram_send_message(chat_id: int, text: str):
    url = f"{TELEGRAM_API_URL}/sendMessage"
    resp = requests.post(url, json={"chat_id": chat_id, "text": text})
    if not resp.ok:
        logger.error("Failed to sendMessage: %s %s", resp.status_code, resp.text)


def telegram_send_document(chat_id: int):
    """Отправляем шаблон документа пользователю."""
    if not os.path.exists(TEMPLATE_PATH):
        telegram_send_message(
            chat_id,
            "Извините, шаблон документа пока не настроен на стороне сервера.",
        )
        return
    url = f"{TELEGRAM_API_URL}/sendDocument"
    with open(TEMPLATE_PATH, "rb") as f:
        files = {"document": (os.path.basename(TEMPLATE_PATH), f)}
        data = {"chat_id": chat_id}
        resp = requests.post(url, data=data, files=files)
    if not resp.ok:
        logger.error("Failed to sendDocument: %s %s", resp.status_code, resp.text)


def get_file_bytes_and_ext(
    file_id: str,
    is_photo: bool = False,
    original_name: str | None = None,
):
    """Скачать файл с серверов Telegram и определить расширение."""
    # getFile
    resp = requests.get(f"{TELEGRAM_API_URL}/getFile", params={"file_id": file_id})
    data = resp.json()
    if not resp.ok or not data.get("ok"):
        logger.error("getFile error: %s", resp.text)
        raise RuntimeError("Failed to get file from Telegram")

    file_path = data["result"]["file_path"]

    # download file
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
    file_resp = requests.get(file_url)
    if not file_resp.ok:
        logger.error("download file error: %s", file_resp.text)
        raise RuntimeError("Failed to download file from Telegram")

    content = file_resp.content

    # Определяем расширение
    ext = ""
    if original_name and "." in original_name:
        ext = "." + original_name.split(".")[-1]
    elif is_photo:
        ext = ".jpg"
    else:
        # пробуем взять из пути
        if "." in file_path:
            ext = "." + file_path.split(".")[-1]
        else:
            ext = ".bin"

    return content, ext


# --- Google Drive ---


def upload_to_drive(name: str, content: bytes):
    if not DRIVE_FOLDER_ID:
        raise RuntimeError("DRIVE_FOLDER_ID is not set")

    service = get_drive_service()

    media = MediaIoBaseUpload(
        io.BytesIO(content),
        mimetype="application/octet-stream",
        resumable=False,
    )
    file_metadata = {
        "name": name,
        "parents": [DRIVE_FOLDER_ID],
    }

    created = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id",
    ).execute()
    logger.info("Uploaded file to Drive: id=%s name=%s", created.get("id"), name)


def sanitize_name(raw: str) -> str:
    """Приводим имя из подписи в аккуратный вид для файла."""
    raw = raw.strip()
    # заменяем все пробелы на подчёркивания
    raw = "_".join(raw.split())
    # убираем совсем уж запрещённые символы
    forbidden = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    for ch in forbidden:
        raw = raw.replace(ch, "")
    if not raw:
        raw = "user"
    return raw


# --- Обработка команд и сообщений ---


def handle_start(chat_id: int):
    text = (
        "Привет! Я бот для отправки и приёма подписанных документов.\n\n"
        "1. Я пришлю вам шаблон соглашения.\n"
        "2. Вы скачаете его, подпишете электронно.\n"
        "3. Потом отправите мне обратно подписанный документ в формате PDF.\n\n"
        "Когда будете отправлять подписанный файл, напишите в подписи к файлу "
        "ваше имя и фамилию.\n"
        "Важно: бот принимает только файлы в формате PDF."
    )
    telegram_send_message(chat_id, text)


def handle_send_template(chat_id: int):
    telegram_send_message(
        chat_id,
        "Отправляю соглашение.\n"
        "После подписи пришлите его мне обратно в формате PDF.\n\n"
        "Не забудьте указать ваше имя и фамилию в подписи к файлу.",
    )
    telegram_send_document(chat_id)


PDF_ONLY_MESSAGE = "Соглашение должно быть в формате PDF. Пожалуйста, отправь его ещё раз в формате PDF."


def handle_file_message(message: dict):
    """Обработка входящего файла (только PDF-документ)."""
    chat_id = message["chat"]["id"]
    caption = message.get("caption", "") or ""

    # Без подписи с именем — просим переслать файл с подписью
    if not caption.strip():
        telegram_send_message(
            chat_id,
            "Я получил файл, но не вижу вашего имени в подписи к файлу.\n\n"
            "Пожалуйста, отправьте файл ещё раз и в подписи к файлу укажите ваше имя и фамилию.",
        )
        return

    name_part = sanitize_name(caption)
    logger.info("Using name from caption: %s", name_part)

    # Принимаем только документы, фото и прочее не обрабатываем
    if "document" in message:
        doc = message["document"]
        file_id = doc["file_id"]
        original_name = doc.get("file_name")
        content, ext = get_file_bytes_and_ext(
            file_id,
            is_photo=False,
            original_name=original_name,
        )

        # Проверяем, что это именно PDF
        if ext.lower() != ".pdf":
            telegram_send_message(chat_id, PDF_ONLY_MESSAGE)
            return

    elif "photo" in message:
        # Фото сразу отклоняем
        telegram_send_message(chat_id, PDF_ONLY_MESSAGE)
        return
    else:
        telegram_send_message(
            chat_id,
            PDF_ONLY_MESSAGE,
        )
        return

    filename = f"{name_part}_{DOCUMENT_SUFFIX}{ext}"

    try:
        upload_to_drive(filename, content)
        telegram_send_message(chat_id, "Спасибо! Файл принят и сохранён.")
    except Exception:
        logger.exception("Failed to upload to Drive")
        telegram_send_message(
            chat_id,
            "Произошла ошибка при сохранении файла. Попробуйте, пожалуйста, позже.",
        )


def handle_update(update: dict):
    """Разбираем апдейт от Telegram и решаем, что делать."""
    if "message" not in update:
        return
    message = update["message"]
    chat_id = message["chat"]["id"]

    if "text" in message:
        text = message["text"].strip()
        if text.startswith("/start"):
            handle_start(chat_id)
        elif text.startswith("/document") or text.startswith("/doc"):
            handle_send_template(chat_id)
        else:
            telegram_send_message(
                chat_id,
                "Чтобы получить шаблон соглашения, отправьте /document.\n"
                "Чтобы отправить подписанное соглашение, пришлите его как файл (PDF) и "
                "укажите ваше имя в подписи.",
            )
    elif "document" in message or "photo" in message:
        handle_file_message(message)
    else:
        telegram_send_message(
            chat_id,
            "Я понимаю только команды /start, /document и PDF-файлы с подписанным соглашением.",
        )


# --- Flask-приложение под Cloud Run ---


app = Flask(__name__)


@app.get("/")
def index():
    return "ok", 200


@app.post("/webhook")
def webhook():
    try:
        update = request.get_json(force=True, silent=False)
        logger.info("Incoming update: %s", update)
        handle_update(update)
    except Exception:
        logger.exception("Error handling update")
    return jsonify(ok=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
