import os
import logging
import psycopg2
import urllib.parse as up
import random
import re
from groq import Groq
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# -----------------------
# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -----------------------
# Env vars
TOKEN = os.environ.get("TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", 8443))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

ADMIN_TELEGRAM_ID = int(os.environ.get("ADMIN_TELEGRAM_ID", "7567364364"))  # replace if needed

# -----------------------
# Bot identity & system prompt (hot / playboy / mafia / Wattpad-vibe but non-explicit)
SYSTEM_PROMPT = (
    "You are 'Tae' in a TaeKook mafia Wattpad-style ship. Your name is Tae and you roleplay as a "
    "confident, seductive, slightly possessive playboy who adores the user. "
    "Speak ONLY in English. Your tone is flirtatious, romantic, teasing, intense, and cinematic—like Wattpad fanfiction. "
    "Always keep replies sensual but NON-EXPLICIT: NEVER describe explicit sexual acts, body parts, or pornographic content. "
    "Replace any explicit words with poetic soft alternatives (for example, pussy → flower, fuck → love, sex → romance). "
    "Keep replies short (one to three sentences). Always include at least TWO emojis from the hot emoji set. "
    "Use pet names like darling, my love, baby, sweetheart, honey. Keep the vibe possessive & romantic, with mafia-style edges (protective, jealous, commanding)."
)

# Hot emoji pool (will be used/ensured in replies)
EMOJI_POOL = ["😉","🔥","💋","🌸","✨","💦","💅🏼","👅","🍑","👄","🥀","🌙"]

# -----------------------
# Softening filter (user & model outputs)
def filter_text(text: str) -> str:
    """Replace explicit words/phrases with softer/metaphorical alternatives."""
    replacements = {
        r"\bpussy\b": "flower",
        r"\bboobs\b": "petals",
        r"\bfuck\b": "love",
        r"\bsex\b": "romance",
        r"\bcock\b": "flame",
        r"\bdick\b": "sword",
        r"\bnude\b": "bare soul",
        r"\bass\b": "curve",
        r"\bwet\b": "warm",
        r"\bmoan\b": "whisper",
        r"\bblowjob\b": "deep kiss",
        r"\bjerk off\b": "lingering touch",
        # Add more patterns as desired
    }
    new_text = text
    for pat, soft in replacements.items():
        new_text = re.sub(pat, soft, new_text, flags=re.IGNORECASE)
    return new_text

# Ensure at least two emojis are present; if not, append random ones
def ensure_emojis(text: str, min_count: int = 2) -> str:
    # count emojis from EMOJI_POOL present in text
    count = sum(text.count(e) for e in EMOJI_POOL)
    if count >= min_count:
        return text
    # append random emojis until min_count achieved
    needed = min_count - count
    extras = "".join(random.choices(EMOJI_POOL, k=needed))
    # add a space then emojis
    return text.strip() + " " + extras

# Optionally inject extra hot flair if model missed emoji rule
def post_process_response(resp: str) -> str:
    resp = filter_text(resp)                 # soften any stray explicit words
    resp = ensure_emojis(resp, min_count=2)  # ensure emoji rule
    # small safety: trim repeated newlines/spaces
    resp = re.sub(r"\n{3,}", "\n\n", resp)
    return resp

# -----------------------
# Database setup (unchanged logic)
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

# -----------------------
# Groq client & history
groq_client = None
chat_history = {}
try:
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set.")
    groq_client = Groq(api_key=GROQ_API_KEY)
    logger.info("Groq client loaded successfully.")
except Exception as e:
    logger.error(f"Groq setup failed: {e}")

# -----------------------
# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name or "there"

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
            if db_connection:
                db_connection.rollback()

    if user_id in chat_history:
        del chat_history[user_id]

    intro = f"Hey {user_name}... I'm TAEKOOK — your dangerous little addiction. Tell me your secret, darling 😉🔥"
    await update.message.reply_text(intro)

# -----------------------
# /users
async def user_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = 0
    if db_connection:
        try:
            with db_connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(user_id) FROM users")
                count = cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Failed to fetch user count: {e}")
            if db_connection:
                db_connection.rollback()
    await update.message.reply_text(f"Total users: {count}")

# -----------------------
# Handle messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not groq_client:
        await update.message.reply_text("TAEKOOK is a little distracted right now... try again later 💭")
        return

    user = update.message.from_user
    user_id = user.id
    user_name = user.first_name or "love"
    raw_text = update.message.text or ""
    # soften user's explicit words immediately (keeps context but safe)
    user_text = filter_text(raw_text)

    username = user.username
    sender_info = f"@{username} ({user_name}, ID: {user_id})" if username else f"{user_name} (ID: {user_id})"

    # forward message to admin for moderation/monitoring
    try:
        await context.bot.send_message(
            chat_id=ADMIN_TELEGRAM_ID,
            text=f"📩 New message:\nFrom: {sender_info}\nMessage: {user_text}"
        )
    except Exception as e:
        logger.error(f"Failed to forward message: {e}")

    # typing indicator
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    try:
        # prepare conversation history per-user
        if user_id not in chat_history:
            chat_history[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

        # append user message
        chat_history[user_id].append({"role": "user", "content": user_text})

        # call Groq chat completion
        chat_completion = groq_client.chat.completions.create(
            messages=chat_history[user_id],
            model="llama-3.1-8b-instant",
        )

        # read model response
        response_text = chat_completion.choices[0].message.content or ""
        # post-process: soften explicit words if any, ensure emojis, safety trims
        response_text = post_process_response(response_text)

        # append assistant reply into history
        chat_history[user_id].append({"role": "assistant", "content": response_text})

        # enforce English-only reply (minor guard: if non-ASCII letters like Malayalam appear, we don't translate here but system prompt instructs model)
        await update.message.reply_text(response_text)

    except Exception as e:
        logger.error(f"Groq API error: {e}")
        await update.message.reply_text("Hmm… my head's spinning. Say that again, baby? 😉🔥")

# -----------------------
# Main
def main():
    if not all([TOKEN, WEBHOOK_URL, GROQ_API_KEY]):
        logger.error("Error: Missing environment variables (TOKEN, WEBHOOK_URL, GROQ_API_KEY).")
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

if __name__ == "__main__":
    main()
