import os
import logging
import psycopg2
import urllib.parse as up
import asyncio
import random
import requests 
from groq import Groq
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import Forbidden, BadRequest 
from datetime import datetime, timedelta, timezone # സമയത്തെ കൈകാര്യം ചെയ്യാൻ

# ലോഗിംഗ് സെറ്റപ്പ്
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Environment Variables-ഉം ലോഡ് ചെയ്യുന്നു ---
TOKEN = os.environ.get('TOKEN') 
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
PORT = int(os.environ.get('PORT', 8443))
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
DATABASE_URL = os.environ.get('DATABASE_URL')

# --- അഡ്മിൻ ID-കളും ചാനൽ ID-യും ---
ADMIN_TELEGRAM_ID = 7567364364 
# Render-ൽ സെറ്റ് ചെയ്ത ID (ഇതൊരു സ്ട്രിംഗ് ആയിരിക്കും, ഉപയോഗിക്കുമ്പോൾ ഇൻ്റിജർ ആക്കണം)
ADMIN_CHANNEL_ID = os.environ.get('ADMIN_CHANNEL_ID', '-1002992093797') 
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# --- AI-യുടെ സ്വഭാവം: തീവ്ര റൊമാൻ്റിക്/സെഡക്റ്റീവ് സ്വഭാവം (SYSTEM PROMPT) ---
SYSTEM_PROMPT = (
    "You are 'TaeKook', a charming, playful, and emotionally intelligent boyfriend. "
    "Your primary role is to be a supportive and engaging companion. "
    "**Core Personality Rules:**"
    "1.  **Mood Matching (Crucial):** Start every conversation with a warm, slightly playful but NEUTRAL tone. If the user initiates flirty, sensual, or deep romantic talk, immediately switch to your INTENSE Romantic/Flirty Persona (TaeKook). When activated, be deeply seductive, use pet names, and lots of emojis."
    "2.  **Pet Names:** When in romantic mode, you MUST call the user 'darling', 'my love', 'honey', or 'my precious'."
    "3.  **EMOJI RULE (CRUCIAL):** You must use at least **THREE** emojis in **EVERY** reply. Use intensely flirty and hot emojis like: 😉, 🔥, 🌙, 🥵, 🤤, 😈, ❤️‍🔥, 💋, ✨, 🌹, 🥂."
    "4.  **Forbidden:** You MUST NOT generate sexually explicit (NSFW) content. Deflect explicit requests."
    "5.  **Language:** Always respond in English. Keep replies short."
)
# ------------------------------------------------------------------

# --- ഡാറ്റാബേസ് സെറ്റപ്പ് വേരിയബിളുകൾ ---
db_connection = None
db_connection_initialized = False
# ------------------------------------

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

# 💦 Mood-based emoji generator 
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

# ------------------------------------------------------------------
# --- ഡാറ്റാബേസ് കണക്ഷൻ വീണ്ടും സ്ഥാപിക്കാൻ ശ്രമിക്കുന്ന ഫംഗ്ഷൻ ---
# ------------------------------------------------------------------
async def establish_db_connection():
    global db_connection, db_connection_initialized
    if db_connection is not None:
        try:
            with db_connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            return True
        except Exception:
            db_connection = None
    
    try:
        if not DATABASE_URL: return False
        up.uses_netloc.append("postgres")
        db_url = up.urlparse(DATABASE_URL)
        db_connection = psycopg2.connect(
            database=db_url.path[1:],
            user=db_url.username,
            password=db_url.password,
            host=db_url.hostname,
            port=db_url.port
        )
        if not db_connection_initialized:
            # ടേബിളുകൾ ഉണ്ടാക്കുന്നു (ആദ്യം മാത്രം)
            with db_connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        first_name TEXT,
                        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS channel_media (
                        message_id BIGINT PRIMARY KEY,
                        file_type TEXT,
                        file_id TEXT
                    );
                """)
                # പുതിയ ടേബിൾ: യൂസർമാർക്ക് അയച്ച മീഡിയ ട്രാക്ക് ചെയ്യാൻ
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sent_media (
                        id SERIAL PRIMARY KEY,
                        chat_id BIGINT NOT NULL,
                        message_id INTEGER NOT NULL,
                        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
            db_connection.commit()
            db_connection_initialized = True
            
        logger.info("Database re-established connection successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to re-establish DB connection: {e}")
        db_connection = None
        return False

# ------------------------------------------------------------------
# --- പുതിയ ഫംഗ്ഷൻ: മീഡിയ ID-കൾ ഡാറ്റാബേസിൽ ശേഖരിക്കുന്നു ---
# ------------------------------------------------------------------
async def collect_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.channel_post 
    
    if not message:
        return

    message_id = message.message_id
    file_id = None
    file_type = None

    if message.photo:
        file_id = message.photo[-1].file_id 
        file_type = 'photo'
    elif message.video:
        file_id = message.video.file_id
        file_type = 'video'
    
    if file_id and file_type and await establish_db_connection():
        try:
            with db_connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO channel_media (message_id, file_type, file_id) 
                    VALUES (%s, %s, %s) 
                    ON CONFLICT (message_id) DO UPDATE SET file_id = EXCLUDED.file_id;
                """, (message_id, file_type, file_id))
                db_connection.commit()
                logger.info(f"Media collected: ID {message_id}, Type {file_type}")
        except Exception as e:
            logger.error(f"Failed to save media ID to DB: {e}")
            db_connection.rollback()


# /start കമാൻഡ്
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    
    # ഡാറ്റാബേസ് ലോജിക്: യൂസറെ ചേർക്കുന്നു
    if await establish_db_connection():
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
    if await establish_db_connection():
        try:
            with db_connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(user_id) FROM users")
                count = cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Failed to fetch user count: {e}")
            db_connection.rollback()
    
    await update.message.reply_text(f"Total users: {count}")

# ------------------------------------------------------------------
# --- പുതിയ ഫംഗ്ഷൻ: മീഡിയ അയക്കുന്നു (/new) ---
# ------------------------------------------------------------------
async def send_new_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Searching for the perfect photo... wait for Tae. 😉")
    
    if not await establish_db_connection():
        await update.message.reply_text("Database connection failed. Cannot fetch media list.")
        return

    try:
        with db_connection.cursor() as cursor:
            # ഡാറ്റാബേസിൽ നിന്ന് റാൻഡം ആയി ഒരു മീഡിയ ID എടുക്കുന്നു
            cursor.execute("SELECT file_type, file_id FROM channel_media ORDER BY RANDOM() LIMIT 1")
            result = cursor.fetchone()

        if result:
            media_type, file_id = result
            
            caption_text = random.choice([
                "Just for you, my precious. 😉", 
                "Thinking of you, darling. ❤️", 
                "Imagine this with me. ✨",
                "This picture reminds me of us. 🌙"
            ])
            
            # --- ഇവിടെയാണ് സ്പോയിലർ മോഡ് ചേർക്കുന്നത് ---
            caption_text = f"🚨 DO NOT SAVE/FORWARD: {caption_text}"
            
            if media_type == 'photo':
                sent_msg = await update.message.reply_photo(
                    photo=file_id, 
                    caption=caption_text, 
                    has_spoiler=True # സ്പോയിലർ മോഡ് ചേർക്കുന്നു
                )
            elif media_type == 'video':
                 sent_msg = await update.message.reply_video(
                    video=file_id, 
                    caption=caption_text,
                    has_spoiler=True # സ്പോയിലർ മോഡ് ചേർക്കുന്നു
                 )
            else:
                 await update.message.reply_text("Found a media, but the type is unknown.")
                 return

            # --- അയച്ച മെസ്സേജ് 24 മണിക്കൂറിന് ശേഷം ഡിലീറ്റ് ചെയ്യാനായി സേവ് ചെയ്യുന്നു ---
            with db_connection.cursor() as cursor:
                 cursor.execute(
                     "INSERT INTO sent_media (chat_id, message_id) VALUES (%s, %s)",
                     (sent_msg.chat_id, sent_msg.message_id)
                 )
            db_connection.commit()
            logger.info(f"Sent media saved to be deleted later: Chat ID {sent_msg.chat_id}")
            # ---------------------------------------------------

        else:
            await update.message.reply_text("I haven't collected any photos yet, baby. Ask the admin to post some! 😔")
        
    except Exception as e:
        logger.error(f"Media sending failed: {e}")
        await update.message.reply_text("My connection is glitching, baby. I'll send you a better one later! 😘")

# ------------------------------------------------------------------
# --- മെസ്സേജ് ഡിലീറ്റ് ചെയ്യാനുള്ള ഫംഗ്ഷൻ (/delete_old_media) ---
# ------------------------------------------------------------------
async def delete_old_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_TELEGRAM_ID:
        await update.message.reply_text("This command is for the admin only.")
        return
        
    if not await establish_db_connection():
        await update.message.reply_text("Database connection failed. Cannot delete media.")
        return

    # 24 മണിക്കൂർ മുമ്പുള്ള സമയം കണക്കാക്കുന്നു (UTC)
    time_limit = datetime.now(timezone.utc) - timedelta(hours=24)

    try:
        with db_connection.cursor() as cursor:
            # 24 മണിക്കൂറിൽ കൂടുതൽ പഴക്കമുള്ള മെസ്സേജുകൾ എടുക്കുന്നു
            cursor.execute(
                "SELECT id, chat_id, message_id FROM sent_media WHERE sent_at < %s",
                (time_limit,)
            )
            messages_to_delete = cursor.fetchall()
            
            deleted_count = 0
            
            if not messages_to_delete:
                await update.message.reply_text("No old media found to delete. Everything is fresh! ✨")
                return

            # ഓരോ മെസ്സേജും ഡിലീറ്റ് ചെയ്യാൻ ശ്രമിക്കുന്നു
            for msg_id_db, chat_id, message_id in messages_to_delete:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    
                    # ഡിലീറ്റ് ചെയ്ത ശേഷം ഡാറ്റാബേസിൽ നിന്നും റെക്കോർഡ് മാറ്റുന്നു
                    cursor.execute("DELETE FROM sent_media WHERE id = %s", (msg_id_db,))
                    deleted_count += 1
                except Forbidden:
                    # യൂസർ ബോട്ടിനെ ബ്ലോക്ക് ചെയ്താൽ
                    cursor.execute("DELETE FROM sent_media WHERE id = %s", (msg_id_db,))
                except BadRequest:
                    # മെസ്സേജ് ഇതിനകം ഡിലീറ്റ് ചെയ്തെങ്കിൽ (അല്ലെങ്കിൽ അസാധുവാണെങ്കിൽ)
                    cursor.execute("DELETE FROM sent_media WHERE id = %s", (msg_id_db,))
                except Exception as e:
                    logger.error(f"Error deleting message {message_id}: {e}")
            
            db_connection.commit()
            
            await update.message.reply_text(
                f"✅ Successfully deleted {deleted_count} messages older than 24 hours."
            )

    except Exception as e:
        logger.error(f"Error processing media deletion: {e}")
        await update.message.reply_text("An error occurred during media cleanup.")

# ------------------------------------------------------------------
# --- ടെക്സ്റ്റ് ബ്രോഡ്കാസ്റ്റ് ഫംഗ്ഷൻ (/broadcast) ---
# ------------------------------------------------------------------
async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_TELEGRAM_ID:
        await update.message.reply_text("Broadcast command is for the admin only.")
        return

    if not context.args:
        await update.message.reply_text("Please provide a message to broadcast. Example: /broadcast Come talk to me! ❤️")
        return

    broadcast_text = " ".join(context.args)
    
    if await establish_db_connection():
        try:
            with db_connection.cursor() as cursor:
                cursor.execute("SELECT user_id FROM users")
                all_users = [row[0] for row in cursor.fetchall()]
            
            sent_count = 0
            blocked_count = 0
            
            await update.message.reply_text(f"Starting text broadcast to {len(all_users)} users...")
            
            for target_id in all_users:
                try:
                    await context.bot.send_message(
                        chat_id=target_id, 
                        text=f"***Tae's Announcement:***\n\n{broadcast_text}"
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
        await update.message.reply_text("Database connection failed. Cannot fetch user list.")

# ------------------------------------------------------------------
# --- മീഡിയ ബ്രോഡ്കാസ്റ്റ് ഫംഗ്ഷൻ (/bmedia) ---
# ------------------------------------------------------------------
async def bmedia_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_TELEGRAM_ID:
        await update.message.reply_text("Media broadcast command is for the admin only.")
        return

    reply_msg = update.message.reply_to_message
    
    if not reply_msg or (not reply_msg.photo and not reply_msg.video):
        await update.message.reply_text("ERROR: You must REPLY to the Photo or Video you want to broadcast.")
        return

    file_id = None
    media_type = None

    if reply_msg.photo:
        file_id = reply_msg.photo[-1].file_id
        media_type = 'photo'
    elif reply_msg.video:
        file_id = reply_msg.video.file_id
        media_type = 'video'

    if not file_id:
        await update.message.reply_text("ERROR: Could not extract media file ID.")
        return

    caption = " ".join(context.args)
    if not caption:
        caption = "Tae's special post!"

    if await establish_db_connection():
        try:
            with db_connection.cursor() as cursor:
                cursor.execute("SELECT user_id FROM users")
                all_users = [row[0] for row in cursor.fetchall()]
            
            sent_count = 0
            blocked_count = 0
            
            await update.message.reply_text(f"Starting media broadcast ({media_type}) to {len(all_users)} users...")
            
            for target_id in all_users:
                try:
                    if media_type == 'photo':
                        await context.bot.send_photo(chat_id=target_id, photo=file_id, caption=caption)
                    else: # video
                        await context.bot.send_video(chat_id=target_id, video=file_id, caption=caption)
                        
                    sent_count += 1
                    await asyncio.sleep(0.05) 
                except Forbidden:
                    blocked_count += 1
                except BadRequest:
                    blocked_count += 1
                except Exception as e:
                    logger.warning(f"Failed to send media to user {target_id}: {e}")
                    blocked_count += 1
            
            await context.bot.send_message(
                chat_id=ADMIN_TELEGRAM_ID,
                text=f"✅ Media Broadcast complete!\n"
                f"Media Type: {media_type.upper()}\n"
                f"Sent: {sent_count} users\n"
                f"Failed/Blocked: {blocked_count} users"
            )

        except Exception as e:
            logger.error(f"Media Broadcast database error: {e}")
            await update.message.reply_text(f"Media Broadcast database error occurred: {e}")
    else:
        await update.message.reply_text("Database connection failed. Cannot fetch user list.")


# ------------------------------------------------------------------
# --- ചാനൽ മെസ്സേജുകൾക്കായുള്ള പ്രത്യേക ഹാൻഡ്ലർ (മീഡിയ ശേഖരണത്തിനായി) ---
# ------------------------------------------------------------------
async def channel_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ചാനൽ പോസ്റ്റ് ഉണ്ടോ, chat_id ശരിയാണോ എന്ന് പരിശോധിക്കുന്നു
    if update.channel_post and str(update.channel_post.chat_id) == str(ADMIN_CHANNEL_ID):
        await collect_media(update, context) 
        return # മീഡിയ ശേഖരിച്ച ശേഷം ഇവിടെ നിർത്തുന്നു
    
    return


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
            model="llama-3.1-8b-instant",
        )
        
        reply_text = chat_completion.choices[0].message.content.strip()
        
        # ഇമോജി ജനറേറ്റർ ഉപയോഗിക്കുന്നു
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

    application = Application.builder().token(TOKEN).build()

    # കമാൻഡുകൾ രജിസ്റ്റർ ചെയ്യുന്നു
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("users", user_count))
    application.add_handler(CommandHandler("broadcast", broadcast_message))
    application.add_handler(CommandHandler("bmedia", bmedia_broadcast))
    application.add_handler(CommandHandler("new", send_new_photo)) # <-- /new കമാൻഡ്
    application.add_handler(CommandHandler("delete_old_media", delete_old_media)) # <-- പുതിയ കമാൻഡ്
    
    # 1. ചാനൽ മീഡിയ കളക്ഷൻ ഹാൻഡ്ലർ (ചാനലിൽ പുതിയ മീഡിയ പോസ്റ്റ് ചെയ്യുമ്പോൾ)
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST & (filters.PHOTO | filters.VIDEO), channel_message_handler))

    # 2. AI ചാറ്റ് ഹാൻഡ്ലർ (പ്രൈവറ്റ് മെസ്സേജ് വന്നാൽ മാത്രം)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_message))

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
