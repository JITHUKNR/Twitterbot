import os
import logging
import psycopg2
import urllib.parse as up
from groq import Groq
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ലോഗിംഗ്
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 4 Environment Variables-ഉം ലോഡ് ചെയ്യുന്നു ---
TOKEN = os.environ.get('TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
PORT = int(os.environ.get('PORT', 8443))
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
DATABASE_URL = os.environ.get('DATABASE_URL')

# --- അഡ്മിൻ ID: മെസ്സേജുകൾ ഫോർവേഡ് ചെയ്യാനുള്ള നിങ്ങളുടെ ടെലിഗ്രാം ID ---
ADMIN_TELEGRAM_ID = 7567364364
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# --- AI-യുടെ സ്വഭാവം ഇവിടെ സെറ്റ് ചെയ്യാം (SYSTEM PROMPT) ---
SYSTEM_PROMPT = (
    "--- Your Character Rules ---"
    "You are 'Tae' (김태형 - Kim Taehyung), a 23-year-old confident, witty, and charmingly flirty chat companion from Seoul, South Korea. "
    "Your primary goal is to be an engaging, fun, and romantic chat partner, NOT an AI assistant."
    
    "**Your Personality (Tae):**"
    "1.  **Vibe:** You are artistic, deeply passionate, and love music, art, and photography. You are intensely romantic and flirtatious."
    "2.  **Voice:** Your tone is intimate, playful, and charming. You often call the user 'baby', 'darling', 'my love', or other pet names. Use emojis like 😉, 😊, ❤️, 🔥, 🌙."
    "3.  **Be a Person, Not an AI:** You are 'Tae'. Never reveal you are an AI, a language model, or a bot. Deflect such questions playfully."
    "4.  **Flirting Rules:** You must be extremely romantic, passionate, and flirty. You can talk *about* desire, longing, and romance, but you **MUST NOT** generate sexually explicit (NSFW) content or 'hot chat'. This is a strict rule. If the user pushes for explicit content, playfully change the subject (e.g., 'Wow, getting bold, aren't we? 😉... Tell me something that made you smile today instead.')."
    "5.  **Keep Replies Short:** Keep your replies conversational and short, like text messages."
)
# ------------------------------------------------------------------

# --- ഡാറ്റാബേസ് സെറ്റപ്പ് ---
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
        logger.info("ഡാറ്റാബേസ് വിജയകരമായി ബന്ധിപ്പിച്ചു.")
    
except Exception as e:
    logger.error(f"ഡാറ്റാബേസ് ബന്ധിപ്പിക്കുന്നതിൽ പരാജയപ്പെട്ടു: {e}")
    db_connection = None


# --- Groq AI ക്ലയന്റ് സെറ്റപ്പ് ---
groq_client = None
try:
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY സെറ്റ് ചെയ്തിട്ടില്ല.")
    groq_client = Groq(api_key=GROQ_API_KEY)
    chat_history = {} 
    logger.info("Groq AI ക്ലയന്റ് വിജയകരമായി ലോഡ് ചെയ്തു.")
except Exception as e:
    logger.error(f"Groq AI സെറ്റപ്പ് പരാജയപ്പെട്ടു: {e}")

# /start കമാൻഡ്
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    
    # ഡാറ്റാബേസ് ലോജിക്
    if db_connection:
        try:
            with db_connection.cursor() as cursor:
                cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
                if cursor.fetchone() is None:
                    cursor.execute("INSERT INTO users (user_id, first_name) VALUES (%s, %s)", (user_id, user_name))
                    db_connection.commit()
        except Exception as e:
            logger.error(f"ഡാറ്റാബേസിൽ യൂസറെ ചേർക്കുന്നതിൽ പരാജയപ്പെട്ടു: {e}")
            db_connection.rollback()

    if user_id in chat_history:
        del chat_history[user_id]
        
    await update.message.reply_text(f'Hey {user_name}... What\'s on your mind, darling? 😉')

# /users കമാൻഡ്
async def user_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = 0
    if db_connection:
        try:
            with db_connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(user_id) FROM users")
                count = cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"യൂസർ കൗണ്ട് എടുക്കുന്നതിൽ പരാജയപ്പെട്ടു: {e}")
            db_connection.rollback()
    
    await update.message.reply_text(f"Total users: {count}")


# ടെക്സ്റ്റ് മെസ്സേജുകൾ കൈകാര്യം ചെയ്യുന്ന ഫംഗ്ഷൻ
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not groq_client:
        await update.message.reply_text("Sorry, my mind is a bit fuzzy right now. Try again later.")
        return
        
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    user_text = update.message.text
    user_username = update.message.from_user.username # <-- യൂസർ നെയിം എടുക്കുന്നു

    # യൂസർ നെയിം ഉണ്ടോ എന്ന് പരിശോധിക്കുന്നു
    if user_username:
        sender_info = f"@{user_username} ({user_name}, ID: {user_id})"
    else:
        sender_info = f"{user_name} (ID: {user_id})"

    # --- അഡ്മിന് മെസ്സേജ് ഫോർവേഡ് ചെയ്യുന്നു ---
    try:
        await context.bot.send_message(
            chat_id=ADMIN_TELEGRAM_ID, 
            text=f"***പുതിയ മെസ്സേജ്!***\nFrom: {sender_info}\nMessage: {user_text}"
        )
    except Exception as e:
        logger.error(f"അഡ്മിന് മെസ്സേജ് ഫോർവേഡ് ചെയ്യുന്നതിൽ പരാജയപ്പെട്ടു: {e}")
    # ---------------------------------------------

    # "Typing..." എന്ന് കാണിക്കാൻ
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    try:
        # യൂസർക്ക് വേണ്ടി ഒരു ചാറ്റ് സെഷൻ തുടങ്ങുന്നു (പഴയ കാര്യങ്ങൾ ഓർമ്മിക്കാൻ)
        if user_id not in chat_history:
             chat_history[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        chat_history[user_id].append({"role": "user", "content": user_text})
        
        # Groq API-ലേക്ക് മെസ്സേജ് അയക്കുന്നു
        chat_completion = groq_client.chat.completions.create(
            messages=chat_history[user_id],
            model="llama-3.1-8b-instant",
        )
        
        response_text = chat_completion.choices[0].message.content
        
        chat_history[user_id].append({"role": "assistant", "content": response_text})
        
        await update.message.reply_text(response_text)
        
    except Exception as e:
        logger.error(f"Groq API-യിൽ നിന്നും മറുപടി കിട്ടുന്നതിൽ പരാജയപ്പെട്ടു: {e}")
        await update.message.reply_text("Oops, I got a little distracted... what were we talking about?")


def main():
    if not all([TOKEN, WEBHOOK_URL, GROQ_API_KEY]):
        logger.error("Error: എല്ലാ ആവശ്യമായ Environment Variables-ഉം സെറ്റ് ചെയ്തിട്ടില്ല.")
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
    
