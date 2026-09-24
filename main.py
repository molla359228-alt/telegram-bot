import os
import re
import random
import asyncio
import logging
import threading
from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telethon import TelegramClient, functions, types
from telethon.sessions import StringSession
from dotenv import load_dotenv
from apify_client import ApifyClient

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0") or "0")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_SESSION_STRING = os.getenv("TELEGRAM_SESSION_STRING", "")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------- Render health check ----------
health_app = Flask(__name__)


@health_app.route("/")
def health():
    return "Bot is running", 200


def run_health_server():
    port = int(os.getenv("PORT", 10000))
    health_app.run(host="0.0.0.0", port=port, use_reloader=False)


# ---------- Helpers ----------

def normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone)


# ---------- WhatsApp check (Apify) ----------

def check_whatsapp(phone: str) -> bool:
    """Apify Actor দিয়ে WhatsApp নম্বর চেক করে"""
    try:
        if not APIFY_API_TOKEN:
            logger.warning("APIFY_API_TOKEN সেট করা হয়নি")
            return False

        client = ApifyClient(APIFY_API_TOKEN)

        # Actor input - নম্বরটি ফরম্যাট করা
        run_input = {"phone_numbers": [phone]}

        # Actor চালান এবং ফলাফল নিন
        run = client.actor("maged120/whatsapp-number-checker").call(
            run_input=run_input
        )

        # ডেটাসেট থেকে ফলাফল পড়ুন
        items = client.dataset(run.default_dataset_id).list_items().items

        if items and len(items) > 0:
            return items[0].get("exists", False)

        return False

    except Exception as e:
        logger.error(f"WhatsApp check failed: {e}")
        return False


# ---------- Telegram check ----------

async def check_telegram(phone: str) -> dict:
    """Telethon দিয়ে Telegram-এ নম্বরটি আছে কিনা চেক করে"""
    if not TELEGRAM_SESSION_STRING or not TELEGRAM_API_HASH:
        return {"registered": False, "error": "not_configured"}

    client = None
    try:
        client = TelegramClient(
            StringSession(TELEGRAM_SESSION_STRING),
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH,
        )
        await client.connect()

        if not await client.is_user_authorized():
            await client.disconnect()
            return {"registered": False, "error": "session_invalid"}

        contact = types.InputPhoneContact(
            client_id=random.randrange(-2**63, 2**63),
            phone=phone,
            first_name="Check",
            last_name="User",
        )
        result = await client(functions.contacts.ImportContactsRequest([contact]))
        await client.disconnect()
        client = None

        if result.users:
            u = result.users[0]
            return {
                "registered": True,
                "user_id": u.id,
                "username": u.username or "",
                "first_name": u.first_name or "",
                "last_name": u.last_name or "",
            }
        return {"registered": False}

    except Exception as e:
        logger.error(f"Telegram check failed: {e}")
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass
        return {"registered": False, "error": str(e)}


# ---------- Telegram Bot handlers ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 হ্যালো! আমাকে যেকোনো দেশের একটি ফোন নম্বর পাঠান।\n"
        "আমি চেক করে জানাবো:\n"
        "• WhatsApp আছে কিনা\n"
        "• Telegram আছে কিনা\n\n"
        "উদাহরণ: +855067272668"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    phone = normalize_phone(text)

    if len(phone) < 6 or len(phone) > 15:
        await update.message.reply_text(
            "❌ দয়া করে সঠিক ফোন নম্বর পাঠান (দেশের কোড সহ)।\n"
            "উদাহরণ: +855067272668"
        )
        return

    await update.message.reply_text("🔍 চেক করা হচ্ছে, অপেক্ষা করুন...")

    formatted = f"+{phone}"

    # WhatsApp চেক (Apify)
    has_whatsapp = check_whatsapp(formatted)

    # Telegram চেক (Telethon)
    tg = await check_telegram(formatted)

    lines = [f"📞 নম্বর: `{formatted}`\n"]

    # WhatsApp
    if has_whatsapp:
        lines.append("✅ **WhatsApp**: আছে")
    else:
        lines.append("❌ **WhatsApp**: নেই")

    # Telegram
    if tg.get("registered"):
        lines.append("✅ **Telegram**: আছে")
        if tg.get("username"):
            lines.append(f"👤 ইউজারনেম: @{tg['username']}")
        name = f"{tg.get('first_name','')} {tg.get('last_name','')}".strip()
        if name:
            lines.append(f"📝 নাম: {name}")
        if tg.get("user_id"):
            lines.append(f"🆔 ID: `{tg['user_id']}`")
    else:
        err = tg.get("error", "")
        if err == "not_configured":
            lines.append("⚠️ **Telegram**: চেক কনফিগার করা হয়নি")
        elif err == "session_invalid":
            lines.append("⚠️ **Telegram**: Session অবৈধ, আবার তৈরি করুন")
        else:
            lines.append("❌ **Telegram**: নেই")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ---------- Main ----------

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN সেট করা হয়নি!")

    threading.Thread(target=run_health_server, daemon=True).start()
    logger.info("Health server started")

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info("Bot starting...")
    application.run_polling()


if __name__ == "__main__":
    main()
