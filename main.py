import os
import re
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
from dotenv import load_dotenv
from apify_client import ApifyClient

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")

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


# ---------- Helper ----------

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
        run_input = {"phone_numbers": [phone]}
        run = client.actor("maged120/whatsapp-number-checker").call(
            run_input=run_input
        )
        items = client.dataset(run.default_dataset_id).list_items().items

        if items and len(items) > 0:
            return items[0].get("exists", False)

        return False

    except Exception as e:
        logger.error(f"WhatsApp check failed: {e}")
        return False


# ---------- Bot handlers ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 হ্যালো! আমাকে যেকোনো দেশের একটি ফোন নম্বর পাঠান।\n"
        "আমি চেক করে জানাবো নম্বরটিতে WhatsApp আছে কিনা।\n\n"
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
    has_whatsapp = check_whatsapp(formatted)

    if has_whatsapp:
        reply = f"📞 নম্বর: `{formatted}`\n\n✅ **WhatsApp**: আছে"
    else:
        reply = f"📞 নম্বর: `{formatted}`\n\n❌ **WhatsApp**: নেই"

    await update.message.reply_text(reply, parse_mode="Markdown")


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
