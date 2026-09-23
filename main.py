import os
import re
import logging
import requests
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TWOCHAT_API_KEY = os.getenv("TWOCHAT_API_KEY")
TWOCHAT_YOUR_NUMBER = os.getenv("TWOCHAT_YOUR_NUMBER")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def normalize_phone(phone: str) -> str:
    """নম্বর থেকে সব অক্ষর বাদ দিয়ে শুধু ডিজিট রাখে"""
    return re.sub(r"\D", "", phone)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 হ্যালো! আমাকে যেকোনো দেশের একটি ফোন নম্বর পাঠান।\n"
        "আমি চেক করে জানাবো নম্বরটিতে WhatsApp আছে কিনা।\n\n"
        "উদাহরণ: +8801712345678"
    )


def check_whatsapp(phone: str) -> bool:
    """2Chat API দিয়ে চেক করে নম্বরে WhatsApp আছে কিনা"""
    try:
        url = (
            f"https://api.p.2chat.io/open/whatsapp/check-number/"
            f"{TWOCHAT_YOUR_NUMBER}/{phone}"
        )
        headers = {"X-User-API-Key": TWOCHAT_API_KEY}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data.get("exists", False)
    except Exception as e:
        logger.error(f"WhatsApp check failed: {e}")
        return False


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    phone = normalize_phone(text)

    if len(phone) < 6 or len(phone) > 15:
        await update.message.reply_text(
            "❌ দয়া করে সঠিক ফোন নম্বর পাঠান (দেশের কোড সহ)।\n"
            "উদাহরণ: +8801712345678"
        )
        return

    await update.message.reply_text("🔍 চেক করা হচ্ছে, অপেক্ষা করুন...")

    formatted = f"+{phone}" if not text.startswith("+") else text
    has_whatsapp = check_whatsapp(formatted)

    result_lines = [f"📞 নম্বর: `{formatted}`\n"]

    if has_whatsapp:
        result_lines.append("✅ **WhatsApp**: আছে")
    else:
        result_lines.append("❌ **WhatsApp**: নেই")

    result_lines.append("\n📱 **Telegram**: চেক করার জন্য আলাদা API প্রয়োজন")

    await update.message.reply_text(
        "\n".join(result_lines), parse_mode="Markdown"
    )


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN সেট করা হয়নি!")

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info("বট চালু হচ্ছে...")
    application.run_polling()


if __name__ == "__main__":
    main()