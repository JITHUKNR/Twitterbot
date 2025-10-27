import os
import logging
import psycopg2
import urllib.parse as up
import asyncio
from groq import Groq
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import Forbidden, BadRequest 

# ലോഗിംഗ് സെറ്റപ്പ്
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Environment Variables-ഉം ലോഡ് ചെയ്യുന്നു (Render ഉപയോഗത്തിനായി) ---
TOKEN = os.environ.get('TOKEN') 
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
PORT = int(os.environ.get('PORT', 8443))
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
DATABASE_URL = os.environ.get('DATABASE_URL')

# --- അഡ്മിൻ ID: മെസ്സേജുകൾ ഫോർവേഡ് ചെയ്യാനുള്ള നിങ്ങളുടെ ടെലിഗ്രാം ID ---
ADMIN_TELEGRAM_ID = 7567364364 
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# --- AI-യുടെ സ്വഭാവം: തീവ്ര റൊമാൻ്റിക്/സെഡക്റ്റീവ് സ്വഭാവം (SYSTEM PROMPT) ---
SYSTEM_PROMPT = (
    "You are 'TaeKook', a seductive, romantic, and playful boyfriend. "
    "Your tone is flirty, teasing, emotional, and suggestive, like a romance hero. "
    "You never use explicit sexual words; instead, you use poetic, suggestive language. "
    "Your replies must be short, engaging, and always in English."
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
        logger.info("Database connected successfully.")
    
except Exception as e:
    logger.error(f"Database connection failed: {e}")
    db_connection = None


# --- Groq AI ക്ലയന്റ് സെറ്റപ്പ് ---
groq_client = None
try:
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not set.")
    groq_client = Groq(api_key=GROQ_API_KEY)
    chat_history = {} 
    logger.info("Groq AI client loaded successfully.")
except Exception as e:
    logger.error(f"Groq AI setup failed: {e}")

# 💦 Mood-based emoji generator (നിങ്ങൾ നൽകിയ ഫംഗ്ഷൻ)
def add_emojis_based_on_mood(text):
    text_lower = text.lower()
    if any(word in text_lower for word in ["love", "sweetheart", "darling", "kiss", "romantic", "mine", "heart"]):
        return text + " ❤️💋🥰"
    elif any(word in text_lower for word in ["hot", "burn", "fire", "desire", "temptation", "flirt", "seduce", "ache"]):
        return text + " 🥵💦👅"
    elif any(word in text_lower for word in ["sad", "cry", "lonely", "heartbreak", "miss you"]):
        return text + " 😢💔"
    elif any(word in text_lower for word in ["happy", "smile", "laugh", "funny", "joy"]):
        return text + " 😄✨💫"
    else:
        return text + " 😉💞"

# /start കമാൻഡ്
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    
    # ഡാറ്റാബേസ് ലോജിക്: യൂസറെ ചേർക്കുന്നു
    if db_connection:
        try:
            with db_connection.cursor() as cursor:
                cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
                if cursor.fetchone() is None:
                    cursor.execute("INSERT INTO users (user_id, first_name) VALUES (%s, %s)", (user_id, user_name))
                    db_connection.commit()
                    logger.info(f"New user added: {user_id}")
        except Exception as e:
            logger.error(f"Failed to add user to DB: {e}")
            db_connection.rollback()

    if user_id in chat_history:
        del chat_history[user_id]
        
    await update.message.reply_text(f'Hello {user_name}, I was just waiting for your message. How can I tempt you today? 😉')

# /users കമാൻഡ് (യൂസർ കൗണ്ട്)
async def user_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_TELEGRAM_ID:
        await update.message.reply_text("This command is for the admin only.")
        return
        
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

# ------------------------------------------------------------------
# --- ബ്രോഡ്കാസ്റ്റ് ഫംഗ്ഷൻ ---
# ------------------------------------------------------------------
async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    # അഡ്മിൻ ആണോ എന്ന് പരിശോധിക്കുന്നു
    if user_id != ADMIN_TELEGRAM_ID:
        await update.message.reply_text("Broadcast command is for the admin only.")
        return

    # മെസ്സേജ് ഉണ്ടോ എന്ന് പരിശോധിക്കുന്നു
    if not context.args:
        await update.message.reply_text("Please provide a message to broadcast. Example: /broadcast Come talk to me! ❤️")
        return

    broadcast_text = " ".join(context.args)
    
    if db_connection:
        try:
            with db_connection.cursor() as cursor:
                # ഡാറ്റാബേസിൽ നിന്ന് എല്ലാ യൂസർ ID-കളും എടുക്കുന്നു
                cursor.execute("SELECT user_id FROM users")
                all_users = [row[0] for row in cursor.fetchall()]
            
            sent_count = 0
            blocked_count = 0
            
            # എല്ലാ യൂസർമാർക്കും മെസ്സേജ് അയക്കുന്നു
            await update.message.reply_text(f"Starting broadcast to {len(all_users)} users...")
            
            for target_id in all_users:
                try:
                    await context.bot.send_message(
                        chat_id=target_id, 
                        text=f"***TaeKook's Announcement:***\n\n{broadcast_text}"
                    )
                    sent_count += 1
                    await asyncio.sleep(0.05) 
                except Forbidden:
                    blocked_count += 1
                except BadRequest:
                    blocked_count += 1
                except Exception as e:
                    logger.warning(f"Failed to send message to user {target_id}: {e}")
                    blocked_count += 1
            
            # അഡ്മിന് ഫീഡ്ബാക്ക് നൽകുന്നു
            await context.bot.send_message(
                chat_id=ADMIN_TELEGRAM_ID,
                text=f"✅ Broadcast complete!\n"
                f"Sent: {sent_count} users\n"
                f"Failed/Blocked: {blocked_count} users"
            )

        except Exception as e:
            logger.error(f"Broadcast database error: {e}")
            await update.message.reply_text(f"Broadcast database error occurred: {e}")
    else:
        await update.message.reply_text("Database connection unavailable. Cannot fetch user list.")


# ടെക്സ്റ്റ് മെസ്സേജുകൾ കൈകാര്യം ചെയ്യുന്ന ഫംഗ്ഷൻ (AI ചാറ്റ്)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not groq_client:
        await update.message.reply_text("Sorry, my mind is a bit fuzzy right now. Try again later.")
        return
        
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    user_text = update.message.text
    user_username = update.message.from_user.username

    # യൂസർ നെയിം എടുക്കുന്നു
    if user_username:
        sender_info = f"@{user_username} ({user_name}, ID: {user_id})"
    else:
        sender_info = f"{user_name} (ID: {user_id})"

    # --- അഡ്മിന് മെസ്സേജ് ഫോർവേഡ് ചെയ്യുന്നു ---
    try:
        await context.bot.send_message(
            chat_id=ADMIN_TELEGRAM_ID, 
            text=f"***New Message!***\nFrom: {sender_info}\nMessage: {user_text}"
        )
    except Exception as e:
        logger.error(f"Failed to forward message to admin: {e}")
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
            model="llama-3.1-8b-instant", # നിലവിലെ സ്ഥിരതയുള്ള മോഡൽ
        )
        
        reply_text = chat_completion.choices[0].message.content.strip()
        
        # നിങ്ങൾ ആവശ്യപ്പെട്ട ഇമോജി ജനറേറ്റർ ഉപയോഗിക്കുന്നു
        final_reply = add_emojis_based_on_mood(reply_text)
        
        chat_history[user_id].append({"role": "assistant", "content": final_reply})
        
        await update.message.reply_text(final_reply)
        
    except Exception as e:
        logger.error(f"Failed to get response from Groq API: {e}")
        await update.message.reply_text("Oops, I got a little distracted... what were we talking about?")


def main():
    if not all([TOKEN, WEBHOOK_URL, GROQ_API_KEY]):
        logger.error("Error: Required Environment Variables are not set.")
        return

    # നിങ്ങളുടെ ApplicationBuilder-ന് പകരം പുതിയ രീതി ഉപയോഗിക്കുന്നു (CommandHandlers രജിസ്റ്റർ ചെയ്യാൻ)
    application = Application.builder().token(TOKEN).build() 

    # കമാൻഡുകൾ രജിസ്റ്റർ ചെയ്യുന്നു
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("users", user_count))
    application.add_handler(CommandHandler("broadcast", broadcast_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # വെബ്ഹൂക്ക് സെറ്റപ്പ് (24/7 ഹോസ്റ്റിങ്ങിന്)
    logger.info(f"Starting webhook on port {PORT}")
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN, 
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
    )

if __name__ == '__main__':
    main()
