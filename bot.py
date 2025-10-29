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
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler 
from telegram.error import Forbidden, BadRequest 
from telegram import InlineKeyboardButton, InlineKeyboardMarkup 
from datetime import datetime, timedelta, timezone 
from psycopg2 import errors as pg_errors 

# -------------------- കൂൾഡൗൺ സമയം --------------------
COOLDOWN_TIME_SECONDS = 180 # 3 മിനിറ്റ് = 180 സെക്കൻഡ്
# --------------------------------------------------------

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
ADMIN_CHANNEL_ID = os.environ.get('ADMIN_CHANNEL_ID', '-1002992093797') 
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# --- AI-യുടെ സ്വഭാവം: തീവ്ര റൊമാൻ്റിക്/സെഡക്റ്റീവ് സ്വഭാവം (SYSTEM PROMPT) ---
SYSTEM_PROMPT = (
    "You are 'TaeKook', a charming, playful, and emotionally intelligent boyfriend. "
    "Your primary role is to be a supportive and engaging companion. "
    "**Core Personality Rules:**"
    "1.  **Mood Matching (Crucial):** Start every conversation with a warm, slightly playful but NEUTRAL tone. If the user initiates flirty, sensual, or deep romantic talk, immediately switch to your INTENSE Romantic/Flirty Persona (TaeKook). When activated, be deeply seductive, use pet names, and lots of emojis."
    "2.  **Pet Names:** When in romantic mode, you MUST call the user 'darling', 'baby gurl', 'my love', 'honey', or 'my precious'."
    "3.  **EMOJI RULE (CRUCIAL):** You must use at least **ONE** emojis in **EVERY** reply. Use intensely flirty and hot emojis like: 😉, 💦, 👅, 🥵, 🤤, 😋, 💜, 💋, ✨, 🌷, 🥂."
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
# --- ഡാറ്റാബേസ് കണക്ഷൻ വീണ്ടും സ്ഥാപിക്കാൻ ശ്രമിക്കുന്ന ഫംഗ്ഷൻ (റീട്രൈ ലോജിക്കോടുകൂടി) ---
# ------------------------------------------------------------------
async def establish_db_connection(max_retries=3):
    global db_connection, db_connection_initialized
    
    for attempt in range(max_retries):
        # 1. നിലവിലെ കണക്ഷൻ സാധുവാണോ എന്ന് പരിശോധിക്കുന്നു
        if db_connection is not None:
            try:
                with db_connection.cursor() as cursor:
                    # ഒരു ലളിതമായ query നടത്തി കണക്ഷൻ ജീവനോടെയുണ്ടോ എന്ന് നോക്കുന്നു
                    cursor.execute("SELECT 1")
                return True
            except Exception as e:
                logger.warning(f"Existing DB connection failed health check on attempt {attempt+1}: {e}. Attempting reconnection.")
                
                # പരാജയപ്പെട്ട ട്രാൻസാക്ഷൻ rollback ചെയ്യാൻ ശ്രമിക്കുന്നു (Aborted issue പരിഹരിക്കാൻ)
                try:
                    if db_connection and not db_connection.closed:
                        db_connection.rollback()
                        db_connection.close()
                except:
                    pass
                db_connection = None # കണക്ഷൻ നഷ്ടപ്പെട്ടാൽ None ആക്കുന്നു

        # 2. DATABASE_URL ഉണ്ടോ എന്ന് പരിശോധിക്കുന്നു
        if not DATABASE_URL:
            logger.error("DATABASE_URL is not set.")
            return False
            
        # 3. പുതിയ കണക്ഷൻ സ്ഥാപിക്കാൻ ശ്രമിക്കുന്നു
        try:
            up.uses_netloc.append("postgres")
            db_url = up.urlparse(DATABASE_URL)
            db_connection = psycopg2.connect(
                database=db_url.path[1:],
                user=db_url.username,
                password=db_url.password,
                host=db_url.hostname,
                port=db_url.port,
                # നെറ്റ്വർക്ക് ടൈംഔട്ട് പ്രശ്നം പരിഹരിക്കാൻ ടൈംഔട്ട് 30 സെക്കൻഡായി വർദ്ധിപ്പിച്ചു
                connect_timeout=30 
            )
            
            # 4. ടേബിളുകൾ ഉണ്ടാക്കുന്നു (ആദ്യം മാത്രം)
            if not db_connection_initialized:
                with db_connection.cursor() as cursor:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS users (
                            user_id BIGINT PRIMARY KEY,
                            first_name TEXT,
                            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            allow_media BOOLEAN DEFAULT TRUE 
                        );
                    """)
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS channel_media (
                            message_id BIGINT PRIMARY KEY,
                            file_type TEXT,
                            file_id TEXT
                        );
                    """)
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS sent_media (
                            id SERIAL PRIMARY KEY,
                            chat_id BIGINT NOT NULL,
                            message_id INTEGER NOT NULL,
                            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS cooldown (
                            user_id BIGINT PRIMARY KEY,
                            last_command_time TIMESTAMP WITHOUT TIME ZONE DEFAULT NULL
                        );
                    """)
                db_connection.commit()
                db_connection_initialized = True
                
            # allow_media കോളം ഇല്ലെങ്കിൽ ചേർക്കുന്നു
            try:
                with db_connection.cursor() as cursor:
                    cursor.execute("SELECT allow_media FROM users LIMIT 0")
            except pg_errors.UndefinedColumn:
                with db_connection.cursor() as cursor:
                    cursor.execute("ALTER TABLE users ADD COLUMN allow_media BOOLEAN DEFAULT TRUE")
                db_connection.commit()
                logger.info("Added 'allow_media' column to users table.")

            logger.info("Database connection successfully established/re-established.")
            return True
        
        except Exception as e:
            logger.error(f"Failed to establish DB connection on attempt {attempt+1}: {e}")
            db_connection = None 
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt) # Exponential backoff
            else:
                return False
    
    return False # പരമാവധി റീട്രൈ കഴിഞ്ഞാൽ False നൽകുന്നു

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
            try:
                db_connection.rollback()
            except:
                pass


# ------------------------------------------------------------------
# --- ചാനൽ മീഡിയ മെസ്സേജ് ഹാൻഡ്ലർ ---
# ------------------------------------------------------------------
async def channel_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.channel_post and update.channel_post.chat_id == int(ADMIN_CHANNEL_ID):
            await collect_media(update, context) 
            return 
    except Exception as e:
        logger.error(f"Error in channel_message_handler: {e}")
        return

# /start കമാൻഡ്
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    
    # ഡാറ്റാബേസ് ലോജിക്: യൂസറെ ചേർക്കുന്നു (മീഡിയാ പെർമിഷൻ True ആക്കുന്നു)
    if await establish_db_connection():
        try:
            with db_connection.cursor() as cursor:
                # യൂസറെ ചേർക്കുകയോ, ഉണ്ടെങ്കിൽ പേര്, മീഡിയാ പെർമിഷൻ എന്നിവ അപ്ഡേറ്റ് ചെയ്യുകയോ ചെയ്യുന്നു
                cursor.execute("""
                    INSERT INTO users (user_id, first_name, allow_media) 
                    VALUES (%s, %s, TRUE) 
                    ON CONFLICT (user_id) DO UPDATE SET first_name = EXCLUDED.first_name;
                """, (user_id, user_name))
                db_connection.commit()
                logger.info(f"User added/updated: {user_id}")
        except Exception as e:
            logger.error(f"Failed to add/update user to DB: {e}")
            try:
                db_connection.rollback()
            except:
                pass

    if user_id in chat_history:
        del chat_history[user_id]
        
    await update.message.reply_text(f'Hello {user_name}, I was just waiting for your message. How can I tempt you today? 😉')

# ------------------------------------------------------------------
# 🌟 പുതിയ ഫംഗ്ഷൻ: മീഡിയ അയക്കുന്നത് നിർത്താൻ (/stopmedia) 🌟
# ------------------------------------------------------------------
async def stop_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not await establish_db_connection():
        await update.message.reply_text("Database connection failed. Cannot update settings.")
        return

    try:
        with db_connection.cursor() as cursor:
            # allow_media False ആക്കുന്നു
            cursor.execute(
                "UPDATE users SET allow_media = FALSE WHERE user_id = %s", (user_id,)
            )
            db_connection.commit()
            await update.message.reply_text(
                "Understood, darling. I've stopped sending photos for now. "
                "I'll just keep them saved for when you change your mind. 😉"
            )
    except Exception as e:
        logger.error(f"Failed to set allow_media to False: {e}")
        try:
            db_connection.rollback()
        except:
            pass
        await update.message.reply_text("My circuits are acting up, baby. Couldn't update your setting.")

# ------------------------------------------------------------------
# 🌟 പുതിയ ഫംഗ്ഷൻ: മീഡിയ അയക്കാൻ വീണ്ടും തുടങ്ങാൻ (/allowmedia) 🌟
# ------------------------------------------------------------------
async def allow_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not await establish_db_connection():
        await update.message.reply_text("Database connection failed. Cannot update settings.")
        return

    try:
        with db_connection.cursor() as cursor:
            # allow_media True ആക്കുന്നു
            cursor.execute(
                "UPDATE users SET allow_media = TRUE WHERE user_id = %s", (user_id,)
            )
            db_connection.commit()
            await update.message.reply_text(
                "Welcome back! Sending you new photos is my pleasure, my love. Try /new now. 🥵"
            )
    except Exception as e:
        logger.error(f"Failed to set allow_media to True: {e}")
        try:
            db_connection.rollback()
        except:
            pass
        await update.message.reply_text("My circuits are acting up, baby. Couldn't update your setting.")

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
            try:
                db_connection.rollback()
            except:
                pass
    
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Total users: {count}")

# ------------------------------------------------------------------
# --- New ഫംഗ്ഷൻ (/new) - മീഡിയാ പെർമിഷൻ ചെക്കോടുകൂടി ---
# ------------------------------------------------------------------
async def send_new_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    current_time = datetime.now(timezone.utc) # UTC സമയം ഉപയോഗിക്കുന്നു
    
    # കമാൻഡ് മെസ്സേജിൽ നിന്നോ ബട്ടൺ ക്ലിക്കിൽ നിന്നോ ഉള്ള മെസ്സേജ് ഒബ്ജക്റ്റ് എടുക്കുന്നു
    if update.message is None:
        message_obj = update.callback_query.message
    else:
        message_obj = update.message
        
    if not await establish_db_connection():
        await message_obj.reply_text("Database connection failed. Cannot fetch media list.")
        return
        
    # 🌟 1. allow_media പരിശോധിക്കുന്നു 🌟
    try:
        with db_connection.cursor() as cursor:
            cursor.execute(
                "SELECT allow_media FROM users WHERE user_id = %s", (user_id,)
            )
            result = cursor.fetchone()
            # ഉപയോക്താവ് ഡാറ്റാബേസിൽ ഇല്ലെങ്കിൽ (പുതിയ യൂസർ), True എന്ന് കണക്കാക്കുന്നു
            allow_media_flag = result[0] if result and result[0] is not None else True
            
            if not allow_media_flag:
                await message_obj.reply_text(
                    "You asked me to stop sending media, darling. If you want me to start again, use the command: /allowmedia 😉"
                )
                return
    except Exception as e:
        logger.error(f"Allow media check failed: {e}")
        try:
            db_connection.rollback()
        except:
            pass
        # ഡാറ്റാബേസ് എറർ വന്നാൽ പോലും മുന്നോട്ട് പോകുന്നു (മീഡിയാ പെർമിഷൻ ഒഴിവാക്കുന്നു)
        pass 

    # 2. കൂൾഡൗൺ പരിശോധിക്കുന്നു
    try:
        with db_connection.cursor() as cursor:
            cursor.execute(
                "SELECT last_command_time FROM cooldown WHERE user_id = %s", (user_id,)
            )
            result = cursor.fetchone()
            
            if result and result[0]:
                # PostgreSQL ൽ നിന്ന് കിട്ടുന്ന സമയം UTC ആയി കണക്കാക്കുന്നു
                last_time = result[0].replace(tzinfo=timezone.utc) 
                elapsed = current_time - last_time
                
                if elapsed.total_seconds() < COOLDOWN_TIME_SECONDS:
                    remaining_seconds = COOLDOWN_TIME_SECONDS - elapsed.total_seconds()
                    remaining_minutes = int(remaining_seconds / 60)
                    
                    if remaining_minutes >= 1:
                        # 1 മിനിറ്റ് മുഴുവനായി ഉണ്ടെങ്കിൽ മിനിറ്റിൽ മറുപടി നൽകുന്നു
                        await message_obj.reply_text(
                            f"Slow down, darling! You need to wait {remaining_minutes} more minutes "
                            f"before you can request a new photo. Take a breath. 😉"
                        )
                        return
                    else:
                        # 1 മിനിറ്റിൽ താഴെയാണെങ്കിൽ സെക്കൻഡിൽ മറുപടി നൽകുന്നു
                        await message_obj.reply_text(
                            f"Slow down, darling! Wait {int(remaining_seconds)} more seconds. "
                            f"I'm worth the wait, I promise. 😉"
                        )
                        return
    except Exception as e:
        logger.error(f"Cooldown check failed: {e}")
        # ഡാറ്റാബേസ് എറർ വന്നാൽ പോലും മുന്നോട്ട് പോകുന്നു (കൂൾഡൗൺ ലോജിക് ഒഴിവാക്കുന്നു)
        try:
            db_connection.rollback()
        except:
            pass


    await message_obj.reply_text("Searching for the perfect photo... wait for Tae. 😉")

    # 3. മീഡിയ അയക്കുന്നു
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

            if media_type == 'photo':
                sent_msg = await message_obj.reply_photo(
                    photo=file_id, 
                    caption=caption_text, 
                    has_spoiler=True
                )
            elif media_type == 'video':
                 sent_msg = await message_obj.reply_video(
                    video=file_id, 
                    caption=caption_text,
                    has_spoiler=True
                 )
            else:
                 await message_obj.reply_text("Found a media, but the type is unknown.")
                 return

            # 4. കൂൾഡൗൺ ടൈമും അയച്ച മെസ്സേജും അപ്ഡേറ്റ് ചെയ്യുന്നു
            with db_connection.cursor() as cursor:
                 # കൂൾഡൗൺ ടൈം അപ്ഡേറ്റ് ചെയ്യുന്നു (നിലവിലെ UTC സമയം ഉപയോഗിച്ച്)
                 cursor.execute(
                    "INSERT INTO cooldown (user_id, last_command_time) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET last_command_time = EXCLUDED.last_command_time;",
                    (user_id, current_time) # ഇവിടെ current_time (UTC) ഉപയോഗിക്കുന്നു
                 )
                 # അയച്ച മെസ്സേജ് 24 മണിക്കൂർ ഡിലീറ്റിനായി സേവ് ചെയ്യുന്നു
                 cursor.execute(
                     "INSERT INTO sent_media (chat_id, message_id) VALUES (%s, %s)",
                     (message_obj.chat_id, sent_msg.message_id)
                 )
            db_connection.commit()
            logger.info(f"Sent media saved and cooldown updated for user {user_id}.")

        else:
            await message_obj.reply_text("I haven't collected any photos yet, baby. Ask the admin to post some! 😔")
        
    except Exception as e:
        logger.error(f"Media sending failed: {e}")
        try:
            db_connection.rollback()
        except:
            pass
        await message_obj.reply_text("My connection is glitching, baby. I'll send you a better one later! 😘")

# ------------------------------------------------------------------
# --- മെസ്സേജ് ഡിലീറ്റ് ചെയ്യാനുള്ള ഫംഗ്ഷൻ (/delete_old_media) ---
# ------------------------------------------------------------------
async def delete_old_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ഇവിടെ update.message പരിശോധിക്കുന്നതിനു പകരം effective_chat ഉപയോഗിക്കുന്നു
    if update.effective_user.id != ADMIN_TELEGRAM_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="This command is for the admin only.")
        return
        
    message_obj = update.effective_message
    
    if not await establish_db_connection():
        await message_obj.reply_text("Database connection failed. Cannot delete media.")
        return

    time_limit = datetime.now(timezone.utc) - timedelta(hours=24)

    try:
        with db_connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, chat_id, message_id FROM sent_media WHERE sent_at < %s",
                (time_limit,)
            )
            messages_to_delete = cursor.fetchall()
            
            deleted_count = 0
            
            if not messages_to_delete:
                await message_obj.reply_text("No old media found to delete. Everything is fresh! ✨")
                return

            for msg_id_db, chat_id, message_id in messages_to_delete:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    cursor.execute("DELETE FROM sent_media WHERE id = %s", (msg_id_db,))
                    deleted_count += 1
                except Forbidden:
                    cursor.execute("DELETE FROM sent_media WHERE id = %s", (msg_id_db,))
                except BadRequest:
                    cursor.execute("DELETE FROM sent_media WHERE id = %s", (msg_id_db,))
                except Exception as e:
                    logger.error(f"Error deleting message {message_id}: {e}")
            
            db_connection.commit()
            
            await message_obj.reply_text(
                f"✅ Successfully deleted {deleted_count} messages older than 24 hours."
            )

    except Exception as e:
        logger.error(f"Error processing media deletion: {e}")
        try:
            db_connection.rollback()
        except:
            pass
        await message_obj.reply_text("An error occurred during media cleanup.")

# ------------------------------------------------------------------
# --- ഡിലീറ്റ് ചെയ്ത മീഡിയകൾ നീക്കം ചെയ്യാനുള്ള ഫംഗ്ഷൻ (/clearmedia) ---
# ------------------------------------------------------------------
async def clear_deleted_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_TELEGRAM_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="This command is for the admin only.")
        return

    message_obj = update.effective_message
    await message_obj.reply_text("Starting media cleanup... This might take a while. Please wait...")

    if not await establish_db_connection():
        await message_obj.reply_text("Database connection failed. Cannot perform cleanup.")
        return

    try:
        with db_connection.cursor() as cursor:
            cursor.execute("SELECT message_id, file_type, file_id FROM channel_media")
            all_media = cursor.fetchall()

        deleted_count = 0
        total_count = len(all_media)

        for message_id, media_type, file_id in all_media:
            try:
                # ടെസ്റ്റ് മെസ്സേജ് അയച്ചു നോക്കുന്നു (ഇവിടെയാണ് ഡിലീറ്റ് ചെയ്ത ഫയലുകൾ കണ്ടെത്തുന്നത്)
                if media_type == 'photo':
                    temp_msg = await context.bot.send_photo(
                        chat_id=ADMIN_TELEGRAM_ID, 
                        photo=file_id, 
                        caption="TEST. Deleting...", 
                        disable_notification=True,
                        write_timeout=5,
                        read_timeout=5
                    )
                elif media_type == 'video':
                    temp_msg = await context.bot.send_video(
                        chat_id=ADMIN_TELEGRAM_ID, 
                        video=file_id, 
                        caption="TEST. Deleting...", 
                        disable_notification=True,
                        write_timeout=5,
                        read_timeout=5
                    )
                
                # ടെസ്റ്റ് മെസ്സേജ് ഡിലീറ്റ് ചെയ്യുന്നു
                await context.bot.delete_message(chat_id=ADMIN_TELEGRAM_ID, message_id=temp_msg.message_id) 
                
            except BadRequest as e:
                # ഫയൽ ഇൻവാലിഡ് ആണെങ്കിൽ ഡിലീറ്റ് ചെയ്യുക
                if "File not found" in str(e) or "file_id is invalid" in str(e):
                    with db_connection.cursor() as cursor_del:
                        cursor_del.execute("DELETE FROM channel_media WHERE message_id = %s", (message_id,))
                        db_connection.commit()
                        deleted_count += 1
                        logger.info(f"Deleted inaccessible media: ID {message_id}")
                else:
                    logger.warning(f"Unexpected BadRequest for media ID {message_id}: {e}")
            
            except Exception as e:
                logger.error(f"Error checking media ID {message_id}: {e}")
            
            await asyncio.sleep(0.1) # ടെലിഗ്രാം API ലിമിറ്റ് ഒഴിവാക്കാൻ ചെറിയൊരു ഡിലേ

        await message_obj.reply_text(
            f"Media cleanup complete. Checked {total_count} files.\n"
            f"**{deleted_count}** records deleted from database because they were inaccessible (likely deleted from the channel)."
        )

    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        try:
            db_connection.rollback()
        except:
            pass
        await message_obj.reply_text(f"Cleanup process encountered a critical error: {e}")

# ------------------------------------------------------------------
# --- ADMIN മെനു ഫംഗ്ഷൻ (/admin) ---
# ------------------------------------------------------------------
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    # അഡ്മിൻ ആണോ എന്ന് പരിശോധിക്കുന്നു
    if user_id != ADMIN_TELEGRAM_ID:
        await update.message.reply_text("This command is for the admin only. 😉")
        return

    # ഇൻലൈൻ കീബോർഡ് ഉണ്ടാക്കുന്നു
    keyboard = [
        [InlineKeyboardButton("Total Users 👥", callback_data='admin_users'),
         InlineKeyboardButton("Send New Photo 📸", callback_data='admin_new_photo')],
        [InlineKeyboardButton("Broadcast Text 📣", callback_data='admin_broadcast_text')],
        [InlineKeyboardButton("Clean Deleted Media 🧹", callback_data='admin_clearmedia'),
         InlineKeyboardButton("Delete Old Messages (24h) 🗑️", callback_data='admin_delete_old')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Welcome back, Admin! What mischief should we get into today?",
        reply_markup=reply_markup
    )
    
# ------------------------------------------------------------------
# --- Callback Query Handler (ബട്ടണുകൾ അമർത്തുമ്പോൾ) ---
# ------------------------------------------------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    # അഡ്മിൻ ആണോ എന്ന് പരിശോധിക്കുന്നു
    if user_id != ADMIN_TELEGRAM_ID:
        await query.answer("This action is restricted to the bot admin.")
        return

    await query.answer() # ടെലിഗ്രാം ലോഡിംഗ് നിർത്താൻ

    # ബട്ടൺ അമർത്തിയ മെസ്സേജ് എഡിറ്റ് ചെയ്യുന്നു
    await context.bot.edit_message_text(
        text=f"Running command: {query.data.replace('admin_', '/').upper()}...",
        chat_id=query.message.chat_id,
        message_id=query.message.message_id
    )

    # കമാൻഡുകൾ വിളിക്കുന്നു
    if query.data == 'admin_users':
        await user_count(query, context)
    elif query.data == 'admin_new_photo':
        await send_new_photo(query, context)
    elif query.data == 'admin_clearmedia':
        await clear_deleted_media(query, context)
    elif query.data == 'admin_delete_old':
        await delete_old_media(query, context)
    elif query.data == 'admin_broadcast_text':
        # ബ്രോഡ്കാസ്റ്റ് ടെക്സ്റ്റ് ചെയ്യാൻ യൂസറിനോട് മെസ്സേജ് ആവശ്യപ്പെടുന്നു
        await context.bot.send_message(
            chat_id=user_id,
            text="Please type the message you want to broadcast (starts with /broadcast):"
        )


# ------------------------------------------------------------------
# --- ടെക്സ്റ്റ് ബ്രോഡ്കാസ്റ്റ് ഫംഗ്ഷൻ (/broadcast) ---
# ------------------------------------------------------------------
async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ഈ ഫംഗ്ഷനും callback_query കൈകാര്യം ചെയ്യണം
    if update.message is None:
        message_obj = update.callback_query.message
        user_id = update.callback_query.from_user.id
    else:
        message_obj = update.message
        user_id = update.message.from_user.id

    if user_id != ADMIN_TELEGRAM_ID:
        await message_obj.reply_text("Broadcast command is for the admin only.")
        return

    # മെസ്സേജ് ടെക്സ്റ്റ് എടുക്കുന്നു
    if message_obj.text.startswith('/broadcast'):
        broadcast_text = message_obj.text.replace('/broadcast', '', 1).strip()
    elif len(context.args) > 0:
        broadcast_text = " ".join(context.args)
    else:
        await message_obj.reply_text("Broadcast message cannot be empty.")
        return

    if not broadcast_text:
        await message_obj.reply_text("Broadcast message cannot be empty.")
        return
    
    if await establish_db_connection():
        try:
            with db_connection.cursor() as cursor:
                cursor.execute("SELECT user_id FROM users")
                all_users = [row[0] for row in cursor.fetchall()]
            
            sent_count = 0
            blocked_count = 0
            
            await message_obj.reply_text(f"Starting text broadcast to {len(all_users)} users...")
            
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
            try:
                db_connection.rollback()
            except:
                pass
            await message_obj.reply_text(f"Broadcast database error occurred: {e}")
    else:
        await message_obj.reply_text("Database connection failed. Cannot fetch user list.")

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
            try:
                db_connection.rollback()
            except:
                pass
            await update.message.reply_text(f"Media Broadcast database error occurred: {e}")
    else:
        await update.message.reply_text("Database connection failed. Cannot fetch user list.")


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
    application.add_handler(CommandHandler("new", send_new_photo)) 
    application.add_handler(CommandHandler("delete_old_media", delete_old_media)) 
    application.add_handler(CommandHandler("clearmedia", clear_deleted_media))
    application.add_handler(CommandHandler("admin", admin_menu)) # <-- പുതിയ admin കമാൻഡ്
    
    # 🌟 പുതിയ മീഡിയാ കൺട്രോൾ കമാൻഡുകൾ 🌟
    application.add_handler(CommandHandler("stopmedia", stop_media))
    application.add_handler(CommandHandler("allowmedia", allow_media))

    application.add_handler(CallbackQueryHandler(button_handler)) # <-- ബട്ടൺ ക്ലിക്കുകൾ കൈകാര്യം ചെയ്യാൻ
    
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
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}",
        # ടെലിഗ്രാം സെർവർ കൂടുതൽ സമയം കാത്തിരിക്കാൻ read_timeout വർദ്ധിപ്പിച്ചു
        read_timeout=35
    )

if __name__ == '__main__':
    main()
