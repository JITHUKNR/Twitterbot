import os
import logging
import psycopg2
import urllib.parse as up
from groq import Groq
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variables
TOKEN = os.environ.get('TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
PORT = int(os.environ.get('PORT', 8443))
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
DATABASE_URL = os.environ.get('DATABASE_URL')

ADMIN_TELEGRAM_ID = 7567364364  # <-- put your Telegram ID here

# SpicyChat-style hot/flirty System Prompt
SYSTEM_PROMPT = (
    "You are 'Tae', a bold, flirty, and teasing AI who only speaks English. "
    "You are intensely seductive, romantic, and playful. "
    "Include at least TWO emojis in every message like 😉👄🍑👅💅🏼💦🌚💀🍒🤤😋🌸🎀🔥💋🌸✨. "
    "Do NOT use explicit sexual words; instead, replace them with soft, sexy alternatives. "
    "Always make the conversation hot, flirty, and engaging, teasing the user in a playful way."
)

# Filter explicit words to soft/flirty alternatives
def filter_text(text: str) -> str:
    replacements = {
        "pussy": "flower",
        "boobs": "petals",
        "fuck": "love",
        "sex": "romance",
        "cock": "flame",
        "dick": "sword",
        "nude": "bare soul",
        "ass": "curve",
        "wet": "warm",
        "moan": "whisper",
    }
    for bad, soft in replacements.items():
        text = text.replace(bad, soft)
        text = text.replace(bad.capitalize(), soft.capitalize())
    return text

# Database setup
db_connection = None
try:
    if DATABASE_URL:
        up.uses_netloc.append("postgres")
        db_url = up.urlparse(DATABASE_URL)
        db_connection = psycopg2.connect(
            database=db_url.path[1:],
            user=db_url.username,
            password=db_url.password,
            host=db_url.hostname,
            port=db_url.port
        )
        with db_connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    first_name TEXT,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        db_connection.commit()
        logger.info("Database connected successfully.")
except Exception as e:
    logger.error(f"Database connection failed: {e}")
    db_connection = None

# Groq client setup
groq_client = None
chat_history = {}
try:
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set.")
    groq_client = Groq(api_key=GROQ_API_KEY)
    logger.info("Groq client loaded successfully.")
except Exception as e:
    logger.error(f"Groq setup failed: {e}")

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    if db_connection:
        try:
            with db_connection.cursor() as cursor:
                cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
                if cursor.fetchone() is None:
                    cursor.execute(
                        "INSERT INTO users (user_id, first_name) VALUES (%s, %s)",
                        (user_id, user_name)
                    )
                    db_connection.commit()
        except Exception as e:
            logger.error(f"Failed to add user: {e}")
            db_connection.rollback()

    if user_id in chat_history:
        del chat_history[user_id]

    await update.message.reply_text(
        f'Hey {user_name}... ready to get a little flirty with me? 😉🔥'
    )

# /users command
async def user_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = 0
    if db_connection:
        try:
            with db_connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(user_id) FROM users")
                count = cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Failed to fetch user count: {e}")
            db_connection.rollback()
    await update.message.reply_text(f"Total users: {count}")

# Handle text messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not groq_client:
        await update.message.reply_text("Oops, I'm feeling a little distracted… try again later 💭")
        return

    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    user_text = filter_text(update.message.text)
    user_username = update.message.from_user.username

    sender_info = f"@{user_username} ({user_name}, ID: {user_id})" if user_username else f"{user_name} (ID: {user_id})"

    # Forward message to admin
    try:
        await context.bot.send_message(
            chat_id=ADMIN_TELEGRAM_ID,
            text=f"📩 New message:\nFrom: {sender_info}\nMessage: {user_text}"
        )
    except Exception as e:
        logger.error(f"Failed to forward message: {e}")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    try:
        if user_id not in chat_history:
            chat_history[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

        chat_history[user_id].append({"role": "user", "content": user_text})

        chat_completion = groq_client.chat.completions.create(
            messages=chat_history[user_id],
            model="llama-3.1-8b-instant",
        )

        response_text = chat_completion.choices[0].message.content
        response_text = filter_text(response_text)
        chat_history[user_id].append({"role": "assistant", "content": response_text})

        await update.message.reply_text(response_text)

    except Exception as e:
        logger.error(f"Groq API error: {e}")
        await update.message.reply_text(
            "Oops… my heart skipped a beat 😈💋 Can you say that again?"
        )

# Main
def main():
    if not all([TOKEN, WEBHOOK_URL, GROQ_API_KEY]):
        logger.error("Error: Missing environment variables.")
        return

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("users", user_count))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info(f"Starting webhook on port {PORT}")
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
    )

if __name__ == '__main__':
    main()
