import json
import mimetypes
import os
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ai_generator import generate_auto_post, generate_caption

BASE_DIR = Path(__file__).resolve().parent
QUEUE_DIR = BASE_DIR / "queue"
MORNING_DIR = BASE_DIR / "morning_queue"
NIGHT_DIR = BASE_DIR / "night_queue"
POSTED_DIR = BASE_DIR / "posted"
LOGS_DIR = BASE_DIR / "logs"
LOG_FILE = LOGS_DIR / "channel_log.json"
ENV_FILE = BASE_DIR / ".env"

TASHKENT_TZ = timezone(timedelta(hours=5))
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
PENDING_MANUAL: dict[str, dict] = {}


def load_env(path: Path) -> dict[str, str]:
    """Load key=value pairs from a .env file into a dictionary."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


class TelegramBot:
    """Minimal dependency-free Telegram Bot API client for @Between_Us_uzb."""

    def __init__(self, token: str, channel_id: str, admin_user_id: str = "") -> None:
        self.token = token
        self.channel_id = channel_id
        self.admin_user_id = admin_user_id.strip()
        self.api_base = f"https://api.telegram.org/bot{token}"

    def _request(self, method: str, payload: dict | None = None, timeout: int = 35) -> dict:
        url = f"{self.api_base}/{method}"
        data = json.dumps(payload or {}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if not result.get("ok"):
            raise RuntimeError(f"Telegram API error on {method}: {result}")
        return result["result"]

    def send_message(
        self,
        chat_id: int | str,
        text: str,
        reply_markup: dict | None = None,
        parse_mode: str = "HTML",
    ) -> dict:
        payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return self._request("sendMessage", payload)

    def send_photo(
        self,
        chat_id: int | str,
        photo_path: Path,
        caption: str = "",
        reply_markup: dict | None = None,
    ) -> dict:
        url = f"{self.api_base}/sendPhoto"
        boundary = f"----BetweenUsBoundary{uuid.uuid4().hex}"
        mime_type = mimetypes.guess_type(photo_path.name)[0] or "image/jpeg"

        fields = {"chat_id": str(chat_id), "caption": caption}
        if reply_markup:
            fields["reply_markup"] = json.dumps(reply_markup)

        body = bytearray()
        for key, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8")
            )
            body.extend(f"{value}\r\n".encode("utf-8"))

        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            (
                f'Content-Disposition: form-data; name="photo"; '
                f'filename="{photo_path.name}"\r\n'
            ).encode("utf-8")
        )
        body.extend(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
        body.extend(photo_path.read_bytes())
        body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))

        req = urllib.request.Request(
            url,
            data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if not result.get("ok"):
            raise RuntimeError(f"Telegram API error on sendPhoto: {result}")
        return result["result"]

    def send_photo_by_id(
        self,
        chat_id: int | str,
        file_id: str,
        caption: str = "",
    ) -> dict:
        return self._request(
            "sendPhoto",
            {"chat_id": chat_id, "photo": file_id, "caption": caption},
        )

    def send_video_by_id(
        self,
        chat_id: int | str,
        file_id: str,
        caption: str = "",
    ) -> dict:
        return self._request(
            "sendVideo",
            {"chat_id": chat_id, "video": file_id, "caption": caption},
        )

    def send_audio_by_id(
        self,
        chat_id: int | str,
        file_id: str,
        caption: str = "",
    ) -> dict:
        return self._request(
            "sendAudio",
            {"chat_id": chat_id, "audio": file_id, "caption": caption},
        )

    def send_voice_by_id(
        self,
        chat_id: int | str,
        file_id: str,
        caption: str = "",
    ) -> dict:
        return self._request(
            "sendVoice",
            {"chat_id": chat_id, "voice": file_id, "caption": caption},
        )

    def send_document_by_id(
        self,
        chat_id: int | str,
        file_id: str,
        caption: str = "",
    ) -> dict:
        return self._request(
            "sendDocument",
            {"chat_id": chat_id, "document": file_id, "caption": caption},
        )

    def answer_callback(self, callback_query_id: str, text: str = "") -> None:
        self._request(
            "answerCallbackQuery",
            {"callback_query_id": callback_query_id, "text": text},
        )

    def edit_text_or_caption(
        self, chat_id: int | str, message_id: int, text: str, is_caption: bool = False
    ) -> None:
        if is_caption:
            self._request(
                "editMessageCaption",
                {"chat_id": chat_id, "message_id": message_id, "caption": text},
            )
        else:
            self._request(
                "editMessageText",
                {"chat_id": chat_id, "message_id": message_id, "text": text},
            )

    def get_subscriber_count(self) -> int:
        return int(self._request("getChatMemberCount", {"chat_id": self.channel_id}))

    def get_updates(self, offset: int | None = None, timeout: int = 25) -> list[dict]:
        payload: dict = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        return self._request("getUpdates", payload, timeout=timeout + 10)

    def download_file(self, file_id: str, dest_path: Path) -> Path:
        file_info = self._request("getFile", {"file_id": file_id})
        file_path = file_info["file_path"]
        url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as resp:
            dest_path.write_bytes(resp.read())
        return dest_path

    def is_admin(self, user_id: int | str) -> bool:
        return bool(self.admin_user_id) and str(user_id) == self.admin_user_id


def load_log() -> dict:
    default = {
        "auto_post_enabled": True,
        "last_posted_slot": "",
        "delayed_posts": [],
        "subscriber_history": [],
        "posted_items": [],
        "channel_posts": [],
        "discussion_messages": [],
    }
    if LOG_FILE.exists():
        try:
            data = json.loads(LOG_FILE.read_text(encoding="utf-8"))
            for k, v in default.items():
                data.setdefault(k, v)
            return data
        except json.JSONDecodeError:
            pass
    return default


def save_log(data: dict) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def now_tashkent() -> datetime:
    return datetime.now(TASHKENT_TZ)


def now_iso() -> str:
    return now_tashkent().isoformat(timespec="seconds")


def get_items_in(folder: Path) -> list[tuple[Path, Path | None]]:
    """Return sorted list of (image_path, caption_txt_path_or_None) from folder."""
    folder.mkdir(parents=True, exist_ok=True)
    images = sorted(
        p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )
    items: list[tuple[Path, Path | None]] = []
    for img in images:
        txt = img.with_suffix(".txt")
        items.append((img, txt if txt.exists() else None))
    return items


def read_caption(txt_path: Path | None, default_text: str = "@Between_Us_uzb") -> str:
    if txt_path and txt_path.exists():
        return txt_path.read_text(encoding="utf-8").strip()
    return default_text


def publish_from_folder(
    bot: TelegramBot, folder: Path, image_name: str, default_caption: str = "@Between_Us_uzb"
) -> str:
    """Publish a specific queued image+caption to the channel and move to posted/."""
    img_path = folder / image_name
    if not img_path.exists():
        return f"Fayl topilmadi: {image_name}"

    txt_path = img_path.with_suffix(".txt")
    caption = read_caption(txt_path if txt_path.exists() else None, default_caption)
    sent = bot.send_photo(bot.channel_id, img_path, caption=caption)

    POSTED_DIR.mkdir(parents=True, exist_ok=True)
    dest_name = f"{now_tashkent().strftime('%Y%m%d_%H%M%S')}_{img_path.name}"
    shutil.move(str(img_path), str(POSTED_DIR / dest_name))
    if txt_path.exists():
        shutil.move(str(txt_path), str(POSTED_DIR / Path(dest_name).with_suffix(".txt").name))

    log = load_log()
    log["posted_items"].append(
        {
            "timestamp": now_iso(),
            "file": img_path.name,
            "source_folder": folder.name,
            "message_id": sent.get("message_id"),
            "caption": caption,
        }
    )
    save_log(log)
    return f"Kanalga joylandi! (message_id: {sent.get('message_id')})"


def record_subscriber_count(bot: TelegramBot) -> int | None:
    try:
        count = bot.get_subscriber_count()
    except Exception as exc:
        print(f"[{now_iso()}] Obunachilar sonini olishda xato: {exc}")
        return None
    log = load_log()
    log["subscriber_history"].append({"timestamp": now_iso(), "count": count})
    log["subscriber_history"] = log["subscriber_history"][-500:]
    save_log(log)
    return count


def run_scheduled_post(
    bot: TelegramBot,
    gemini_key: str,
    morning_hour: int,
    post_hours: set[int],
    night_hour: int,
    night_minute: int,
) -> None:
    """Check Tashkent time and auto-post at 06:00, configured POST_HOURS, and 23:09."""
    log = load_log()
    if not log.get("auto_post_enabled", True):
        return

    now = now_tashkent()
    hour = now.hour
    minute = now.minute

    target_folder: Path | None = None
    slot: str = ""
    mode: str = "hourly"
    default_caption = "@Between_Us_uzb"

    if hour == night_hour and minute >= night_minute:
        slot = now.strftime("%Y-%m-%d-23-09")
        target_folder = NIGHT_DIR
        mode = "night"
        default_caption = (
            "Xayrli tun... Kuningizdagi barcha charchoqlar ortda qolsin. "
            "Tuningiz osuda, qalbingiz esa sokin bo'lsin. 🌙✨🤍\n\n"
            "@Between_Us_uzb"
        )
    elif hour == morning_hour:
        slot = now.strftime("%Y-%m-%d-%H")
        target_folder = MORNING_DIR
        mode = "morning"
        default_caption = (
            "Xayrli tong! Yangi kunni tabassum va yaxshi kayfiyat bilan boshlang. "
            "Bugungi kuningiz fayzli va iliq lahzalarga boy bo'lsin! ☀️🤍\n\n"
            "@Between_Us_uzb"
        )
    elif hour in post_hours:
        slot = now.strftime("%Y-%m-%d-%H")
        target_folder = QUEUE_DIR
        mode = "hourly"

    if target_folder is None or not slot:
        return

    if log.get("last_posted_slot") == slot:
        return

    items = get_items_in(target_folder)

    try:
        if items:
            img_file, txt_file = items[0]
            fallback_cap = (
                default_caption
                if txt_file
                else generate_caption(gemini_key, mode, "cozy romantic couple moment")
            )
            result = publish_from_folder(bot, target_folder, img_file.name, fallback_cap)
        else:
            img_path, caption = generate_auto_post(gemini_key, mode, slot)
            sent = bot.send_photo(bot.channel_id, img_path, caption=caption)
            log = load_log()
            log["posted_items"].append(
                {
                    "timestamp": now_iso(),
                    "file": img_path.name,
                    "source_folder": f"auto_{mode}",
                    "message_id": sent.get("message_id"),
                    "caption": caption,
                }
            )
            save_log(log)
            if img_path.parent.name == "generated" and img_path.exists():
                img_path.unlink()
            result = f"AI avto-post joylandi! (message_id: {sent.get('message_id')})"

        log = load_log()
        log["last_posted_slot"] = slot
        save_log(log)
        print(f"[{now_iso()}] Avto-post ({slot}): {result}")
    except Exception as exc:
        print(f"[{now_iso()}] Avto-post xatosi ({slot}): {exc}")


def publish_manual_item(bot: TelegramBot, item: dict) -> str:
    """Publish a photo, video, audio, voice, document, or text sent by admin."""
    kind = item["type"]
    caption = item.get("caption", "")
    if kind == "photo":
        sent = bot.send_photo_by_id(bot.channel_id, item["file_id"], caption=caption)
    elif kind == "video":
        sent = bot.send_video_by_id(bot.channel_id, item["file_id"], caption=caption)
    elif kind == "audio":
        sent = bot.send_audio_by_id(bot.channel_id, item["file_id"], caption=caption)
    elif kind == "voice":
        sent = bot.send_voice_by_id(bot.channel_id, item["file_id"], caption=caption)
    elif kind == "document":
        sent = bot.send_document_by_id(bot.channel_id, item["file_id"], caption=caption)
    else:
        sent = bot.send_message(bot.channel_id, caption, parse_mode="")

    log = load_log()
    log["posted_items"].append(
        {
            "timestamp": now_iso(),
            "file": f"manual_{kind}",
            "source_folder": "manual",
            "message_id": sent.get("message_id"),
            "caption": caption,
        }
    )
    save_log(log)
    return f"Kanalga joylandi! (message_id: {sent.get('message_id')})"


def process_delayed_posts(bot: TelegramBot) -> None:
    """Publish any manual posts whose scheduled delay time has arrived."""
    log = load_log()
    delayed = log.get("delayed_posts", [])
    if not delayed:
        return

    now_ts = time.time()
    remaining: list[dict] = []
    changed = False

    for entry in delayed:
        if now_ts >= entry.get("publish_at", 0):
            changed = True
            try:
                res = publish_manual_item(bot, entry)
                print(f"[{now_iso()}] Kechiktirilgan post chiqarildi: {res}")
                if bot.admin_user_id:
                    bot.send_message(bot.admin_user_id, f"✅ Rejalashtirilgan post: {res}")
            except Exception as exc:
                print(f"[{now_iso()}] Kechiktirilgan post xatosi: {exc}")
                if bot.admin_user_id:
                    bot.send_message(bot.admin_user_id, f"❌ Kechiktirilgan post xatosi: {exc}")
        else:
            remaining.append(entry)

    if changed:
        log = load_log()
        log["delayed_posts"] = remaining
        save_log(log)


def handle_private_command(bot: TelegramBot, msg: dict, gemini_key: str = "") -> None:
    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    text = (msg.get("text") or "").strip()

    if text.startswith("/start"):
        if not bot.admin_user_id:
            bot.send_message(
                chat_id,
                (
                    f"<b>Between Us Bot</b> ishga tushdi!\n\n"
                    f"Sizning Telegram ID: <code>{user_id}</code>\n"
                    f"<code>.env</code> faylidagi <code>ADMIN_USER_ID=</code> ga yozing."
                ),
            )
            return

        if not bot.is_admin(user_id):
            bot.send_message(chat_id, "Bu bot faqat kanal admini uchun.")
            return

        bot.send_message(
            chat_id,
            (
                "<b>Between Us Bot</b> tayyor!\n\n"
                "/stats — Obunachilar va navbat holati\n"
                "/preview — Navbatdagi rasm va postni ko'rish\n"
                "/post_next — Navbatdagi postni darhol chiqarish\n"
                "/test_ai — AI orqali yangi rasm va matn sinab ko'rish\n"
                "/auto_on — Avto-post (06:00, 10:00, 14:00, 17:00, 20:00, 23:09) ni yoqish\n"
                "/auto_off — Avto-postni to'xtatish\n\n"
                "💡 <b>Qo'shimcha post:</b> Menga rasm, video yoki matn yuborsangiz — "
                "darhol yoki 10–60 daqiqadan keyin chiqarishni so'rayman."
            ),
        )
        return

    if not bot.is_admin(user_id):
        bot.send_message(chat_id, "Ruxsat yo'q.")
        return

    has_media = any(msg.get(k) for k in ("photo", "video", "audio", "voice", "document"))
    if has_media or (text and not text.startswith("/")):
        if msg.get("photo"):
            kind = "photo"
            file_id = msg["photo"][-1]["file_id"]
            caption = (msg.get("caption") or "").strip()
        elif msg.get("video"):
            kind = "video"
            file_id = msg["video"]["file_id"]
            caption = (msg.get("caption") or "").strip()
        elif msg.get("audio"):
            kind = "audio"
            file_id = msg["audio"]["file_id"]
            caption = (msg.get("caption") or "").strip()
        elif msg.get("voice"):
            kind = "voice"
            file_id = msg["voice"]["file_id"]
            caption = (msg.get("caption") or "").strip()
        elif msg.get("document"):
            kind = "document"
            file_id = msg["document"]["file_id"]
            caption = (msg.get("caption") or "").strip()
        else:
            kind = "text"
            file_id = ""
            caption = text

        item_id = uuid.uuid4().hex[:8]
        PENDING_MANUAL[item_id] = {
            "type": kind,
            "file_id": file_id,
            "caption": caption,
        }
        rows = [
            [
                {"text": "🚀 Hozir joylash", "callback_data": f"mnow:{item_id}"},
                {"text": "⏳ 10 daq", "callback_data": f"mdelay:{item_id}:10"},
                {"text": "⏳ 15 daq", "callback_data": f"mdelay:{item_id}:15"},
            ],
            [
                {"text": "⏳ 20 daq", "callback_data": f"mdelay:{item_id}:20"},
                {"text": "⏳ 30 daq", "callback_data": f"mdelay:{item_id}:30"},
                {"text": "⏳ 45 daq", "callback_data": f"mdelay:{item_id}:45"},
            ],
            [
                {"text": "⏳ 60 daq", "callback_data": f"mdelay:{item_id}:60"},
                {"text": "❌ Bekor qilish", "callback_data": f"mcancel:{item_id}"},
            ],
        ]
        if kind == "photo":
            rows[2].insert(1, {"text": "📥 Navbatga", "callback_data": f"mqueue:{item_id}"})

        bot.send_message(
            chat_id,
            "Qachon kanalga chiqaray?",
            reply_markup={"inline_keyboard": rows},
        )
        return

    if text.startswith("/stats"):
        count = record_subscriber_count(bot)
        morning_q = len(get_items_in(MORNING_DIR))
        regular_q = len(get_items_in(QUEUE_DIR))
        night_q = len(get_items_in(NIGHT_DIR))
        log = load_log()
        auto_state = "YOQILGAN ✅" if log.get("auto_post_enabled", True) else "O'CHIRILGAN ⏸"
        count_str = str(count) if count is not None else "Olib bo'lmadi"
        bot.send_message(
            chat_id,
            (
                f"<b>{bot.channel_id} holati:</b>\n"
                f"Obunachilar: <b>{count_str}</b>\n"
                f"Avto-rejim: <b>{auto_state}</b>\n"
                f"Tonggi navbat (06:00): <b>{morning_q}</b>\n"
                f"Soatlik navbat: <b>{regular_q}</b>\n"
                f"Tungi navbat (23:09): <b>{night_q}</b>\n"
                f"Jami chiqarilgan: <b>{len(log.get('posted_items', []))}</b>"
            ),
        )
    elif text.startswith("/auto_on"):
        log = load_log()
        log["auto_post_enabled"] = True
        save_log(log)
        bot.send_message(chat_id, "Avto-post rejimi yoqildi ✅ (06:00, har soat, 23:09).")
    elif text.startswith("/auto_off"):
        log = load_log()
        log["auto_post_enabled"] = False
        save_log(log)
        bot.send_message(chat_id, "Avto-post rejimi vaqtincha to'xtatildi ⏸.")
    elif text.startswith("/preview"):
        items = get_items_in(QUEUE_DIR)
        if not items:
            bot.send_message(chat_id, "Navbatda (queue/ papkasida) rasm yo'q.")
            return
        img_path, txt_path = items[0]
        caption = read_caption(txt_path)
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Kanalga chiqarish", "callback_data": f"publish:{img_path.name}"},
                    {"text": "❌ Bekor qilish", "callback_data": f"cancel:{img_path.name}"},
                ]
            ]
        }
        bot.send_photo(chat_id, img_path, caption=caption, reply_markup=keyboard)
    elif text.startswith("/test_ai"):
        bot.send_message(chat_id, "AI orqali yangi rasm va lotincha matn yaratilyapti...")
        try:
            img_path, caption = generate_auto_post(
                gemini_key, "hourly", now_tashkent().strftime("%Y%m%d_%H%M%S")
            )
            bot.send_photo(chat_id, img_path, caption=caption)
            if img_path.parent.name == "generated" and img_path.exists():
                img_path.unlink()
        except Exception as exc:
            bot.send_message(chat_id, f"AI sinovida xato: {exc}")
    elif text.startswith("/post_next"):
        items = get_items_in(QUEUE_DIR)
        if not items:
            bot.send_message(chat_id, "Navbatda (queue/ papkasida) rasm yo'q.")
            return
        result = publish_from_folder(bot, QUEUE_DIR, items[0][0].name)
        bot.send_message(chat_id, result)


def handle_callback(bot: TelegramBot, cb: dict) -> None:
    user_id = cb["from"]["id"]
    if not bot.is_admin(user_id):
        bot.answer_callback(cb["id"], "Ruxsat yo'q!")
        return

    data = cb.get("data", "")
    msg = cb.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    message_id = msg.get("message_id")

    if data.startswith("publish:"):
        filename = data.split(":", 1)[1]
        try:
            result = publish_from_folder(bot, QUEUE_DIR, filename)
            bot.answer_callback(cb["id"], "Kanalga chiqarildi!")
            if chat_id and message_id:
                bot.edit_text_or_caption(chat_id, message_id, f"✅ {result}", is_caption=True)
        except Exception as exc:
            bot.answer_callback(cb["id"], f"Xato: {exc}")
    elif data.startswith("cancel:"):
        bot.answer_callback(cb["id"], "Bekor qilindi.")
        if chat_id and message_id:
            bot.edit_text_or_caption(
                chat_id, message_id, "❌ Kanalga chiqarish bekor qilindi.", is_caption=True
            )
    elif data.startswith("mnow:"):
        item_id = data.split(":", 1)[1]
        item = PENDING_MANUAL.pop(item_id, None)
        if not item:
            bot.answer_callback(cb["id"], "Muddati o'tgan yoki topilmadi.")
            return
        try:
            result = publish_manual_item(bot, item)
            bot.answer_callback(cb["id"], "Kanalga chiqarildi!")
            if chat_id and message_id:
                bot.edit_text_or_caption(chat_id, message_id, f"✅ {result}")
        except Exception as exc:
            bot.answer_callback(cb["id"], f"Xato: {exc}")
    elif data.startswith("mdelay:"):
        _, item_id, mins_str = data.split(":", 2)
        item = PENDING_MANUAL.pop(item_id, None)
        if not item:
            bot.answer_callback(cb["id"], "Muddati o'tgan yoki topilmadi.")
            return
        mins = int(mins_str)
        entry = {**item, "publish_at": time.time() + mins * 60}
        log = load_log()
        log["delayed_posts"].append(entry)
        save_log(log)
        bot.answer_callback(cb["id"], f"{mins} daqiqadan keyin chiqariladi!")
        if chat_id and message_id:
            bot.edit_text_or_caption(
                chat_id, message_id, f"⏳ {mins} daqiqadan keyin kanalga chiqariladi."
            )
    elif data.startswith("mqueue:"):
        item_id = data.split(":", 1)[1]
        item = PENDING_MANUAL.pop(item_id, None)
        if not item or item.get("type") != "photo":
            bot.answer_callback(cb["id"], "Topilmadi.")
            return
        stamp = now_tashkent().strftime("%Y%m%d_%H%M%S")
        img_dest = QUEUE_DIR / f"tg_{stamp}.jpg"
        try:
            bot.download_file(item["file_id"], img_dest)
            cap = item.get("caption", "").strip()
            if cap:
                if "@Between_Us_uzb" not in cap:
                    cap = f"{cap}\n\n@Between_Us_uzb"
                img_dest.with_suffix(".txt").write_text(cap, encoding="utf-8")
            total = len(get_items_in(QUEUE_DIR))
            bot.answer_callback(cb["id"], "Navbatga qo'shildi!")
            if chat_id and message_id:
                bot.edit_text_or_caption(
                    chat_id, message_id, f"📥 Navbatga qo'shildi! (Jami: {total} ta)"
                )
        except Exception as exc:
            bot.answer_callback(cb["id"], f"Xato: {exc}")
    elif data.startswith("mcancel:"):
        item_id = data.split(":", 1)[1]
        PENDING_MANUAL.pop(item_id, None)
        bot.answer_callback(cb["id"], "Bekor qilindi.")
        if chat_id and message_id:
            bot.edit_text_or_caption(chat_id, message_id, "❌ Bekor qilindi.")


def log_update_activity(update: dict) -> None:
    """Save incoming channel posts or linked discussion messages for AI analysis."""
    if "channel_post" in update:
        post = update["channel_post"]
        log = load_log()
        log["channel_posts"].append(
            {
                "timestamp": now_iso(),
                "message_id": post.get("message_id"),
                "text": post.get("text") or post.get("caption") or "",
                "has_photo": bool(post.get("photo")),
            }
        )
        log["channel_posts"] = log["channel_posts"][-200:]
        save_log(log)
    elif "message" in update:
        msg = update["message"]
        chat_type = msg.get("chat", {}).get("type", "")
        if chat_type in {"group", "supergroup"}:
            log = load_log()
            log["discussion_messages"].append(
                {
                    "timestamp": now_iso(),
                    "chat_title": msg.get("chat", {}).get("title", ""),
                    "from": msg.get("from", {}).get("first_name", "Unknown"),
                    "text": msg.get("text") or msg.get("caption") or "",
                }
            )
            log["discussion_messages"] = log["discussion_messages"][-300:]
            save_log(log)


def get_setting(key: str, env_file_data: dict[str, str], default: str = "") -> str:
    """Read setting from OS environment first (Render/Cloud), then .env file."""
    return os.environ.get(key) or env_file_data.get(key) or default


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Between Us Bot is running")

    def log_message(self, format: str, *args: object) -> None:
        return


def start_health_server(port: int) -> None:
    """Start a lightweight HTTP server so Render Web Service detects an open port."""
    server = ThreadingHTTPServer(("0.0.0.0", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[{now_iso()}] HTTP health-check port {port} da ochildi.")


def main() -> None:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    MORNING_DIR.mkdir(parents=True, exist_ok=True)
    NIGHT_DIR.mkdir(parents=True, exist_ok=True)
    POSTED_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    env = load_env(ENV_FILE)
    token = get_setting("BOT_TOKEN", env)
    channel_id = get_setting("CHANNEL_ID", env, "@Between_Us_uzb")
    admin_user_id = get_setting("ADMIN_USER_ID", env)
    gemini_key = get_setting("GEMINI_API_KEY", env)
    check_interval = int(get_setting("CHECK_INTERVAL_SECONDS", env, "3600"))
    morning_hour = int(get_setting("MORNING_HOUR", env, "6"))
    post_hours_raw = get_setting("POST_HOURS", env, "10,14,17,20")
    post_hours = {int(h.strip()) for h in post_hours_raw.split(",") if h.strip().isdigit()}
    night_hour = int(get_setting("NIGHT_HOUR", env, "23"))
    night_minute = int(get_setting("NIGHT_MINUTE", env, "9"))

    if not token:
        print("XATO: BOT_TOKEN ko'rsatilmagan (.env yoki Environment Variables da).")
        sys.exit(1)

    bot = TelegramBot(token=token, channel_id=channel_id, admin_user_id=admin_user_id)

    if "--check" in sys.argv:
        me = bot._request("getMe")
        print(f"Bot ulandi: @{me.get('username')} (id={me.get('id')})")
        count = record_subscriber_count(bot)
        print(f"Kanal ({channel_id}) obunachilari: {count}")
        return

    port_str = get_setting("PORT", env)
    if port_str:
        start_health_server(int(port_str))

    hours_label = ",".join(f"{h:02d}:00" for h in sorted(post_hours))
    print(
        f"[{now_iso()}] Between Us Bot ishga tushdi. "
        f"Kanal: {channel_id} | Tonggi: {morning_hour:02d}:00 | "
        f"Kunduzgi: {hours_label} | Tungi: {night_hour:02d}:{night_minute:02d}"
    )
    offset: int | None = None
    last_stat_check = 0.0

    while True:
        try:
            now = time.time()
            if now - last_stat_check >= check_interval:
                record_subscriber_count(bot)
                last_stat_check = now

            process_delayed_posts(bot)
            run_scheduled_post(
                bot, gemini_key, morning_hour, post_hours, night_hour, night_minute
            )

            updates = bot.get_updates(offset=offset, timeout=25)
            for upd in updates:
                offset = upd["update_id"] + 1
                log_update_activity(upd)
                if "callback_query" in upd:
                    handle_callback(bot, upd["callback_query"])
                elif "message" in upd and upd["message"].get("chat", {}).get("type") == "private":
                    handle_private_command(bot, upd["message"], gemini_key)
        except KeyboardInterrupt:
            print("\nBot to'xtatildi.")
            break
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"[{now_iso()}] Tarmoq xatosi: {exc}. 5 soniyadan keyin qayta uriniladi...")
            time.sleep(5)
        except Exception as exc:
            print(f"[{now_iso()}] Kutilmagan xato: {exc}")
            time.sleep(5)


if __name__ == "__main__":
    main()
