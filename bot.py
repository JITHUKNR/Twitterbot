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

# -------------------- Cooldown Time --------------------
COOLDOWN_TIME_SECONDS = 180 # 3 minutes = 180 seconds
# --------------------------------------------------------

# Logging Setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Load Environment Variables ---
TOKEN = os.environ.get('TOKEN') 
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
PORT = int(os.environ.get('PORT', 8443))
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
DATABASE_URL = os.environ.get('DATABASE_URL')

# --- Admin IDs and Channel ID ---
ADMIN_TELEGRAM_ID = 7567364364 
ADMIN_CHANNEL_ID = os.environ.get('ADMIN_CHANNEL_ID', '-1002992093797') 
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# --- AI Personality: Intense Romantic/Seductive Persona (SYSTEM PROMPT) ---
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

# --- Database Setup Variables ---
db_connection = None
db_connection_initialized = False
# ------------------------------------

# --- Groq AI Client Setup ---
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
# --- Function to re-establish Database Connection (with Rollback Logic) ---
# ------------------------------------------------------------------
async def establish_db_connection():
    global db_connection, db_connection_initialized
    
    # 1. Check if the current connection is valid
    if db_connection is not None:
        try:
            with db_connection.cursor() as cursor:
                # Simple query to check if the connection is alive
                cursor.execute("SELECT 1")
            return True
        except Exception as e:
            logger.warning(f"Existing DB connection failed health check or query failed: {e}. Attempting reconnection.")
            
            # Connection failed: Try to rollback and close to clear the 'aborted transaction' state
            try:
                if not db_connection.closed:
                    db_connection.rollback()
                    db_connection.close() 
            except Exception as rb_e:
                logger.debug(f"Failed to rollback/close connection: {rb_e}")
                
            db_connection = None 

    # 2. Check if DATABASE_URL is set
    if not DATABASE_URL:
        logger.error("DATABASE_URL is not set. Cannot connect to database.")
        return False
        
    # 3. Attempt to establish a new connection
    try:
        up.uses_netloc.append("postgres")
        db_url = up.urlparse(DATABASE_URL)
        db_connection = psycopg2.connect(
            database=db_url.path[1:],
            user=db_url.username,
            password=db_url.password,
            host=db_url.hostname,
            port=db_url.port,
            connect_timeout=15 # Increased timeout for network issues
        )
        
        # 4. Create Tables (only on first run)
        if not db_connection_initialized:
            with db_connection.cursor() as cursor:
                # User table (Added allow_media column)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        first_name TEXT,
                        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        allow_media BOOLEAN DEFAULT TRUE 
                    );
                """)
                # Media table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS channel_media (
                        message_id BIGINT PRIMARY KEY,
                        file_type TEXT,
                        file_id TEXT
                    );
                """)
                # Sent Media table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sent_media (
                        id SERIAL PRIMARY KEY,
                        chat_id BIGINT NOT NULL,
                        message_id INTEGER NOT NULL,
                        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                # Cooldown table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cooldown (
                        user_id BIGINT PRIMARY KEY,
                        last_command_time TIMESTAMP WITHOUT TIME ZONE DEFAULT NULL
                    );
                """)
            db_connection.commit()
            db_connection_initialized = True
            
        # Add allow_media column if it doesn't exist (for older users)
        try:
            with db_connection.cursor() as cursor:
                cursor.execute("SELECT allow_media FROM users LIMIT 0")
        except psycopg2.errors.UndefinedColumn:
            with db_connection.cursor() as cursor:
                cursor.execute("ALTER TABLE users ADD COLUMN allow_media BOOLEAN DEFAULT TRUE")
            db_connection.commit()
            logger.info("Added 'allow_media' column to users table.")

        logger.info("Database connection successfully established/re-established.")
        return True
    
    except Exception as e:
        logger.error(f"Failed to establish DB connection: {e}")
        db_connection = None 
        return False

# ------------------------------------------------------------------
# --- Function to collect Media IDs into the database ---
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
# --- Channel Media Message Handler ---
# ------------------------------------------------------------------
async def channel_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.channel_post and update.channel_post.chat_id == int(ADMIN_CHANNEL_ID):
            await collect_media(update, context) 
            return 
    except Exception as e:
        logger.error(f"Error in channel_message_handler: {e}")
        return

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    
    # Database logic: Add/update user (setting media permission to True by default)
    if await establish_db_connection():
        try:
            with db_connection.cursor() as cursor:
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
# 🌟 New Function: To stop sending media (/stopmedia) 🌟
# ------------------------------------------------------------------
async def stop_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not await establish_db_connection():
        await update.message.reply_text("Database connection failed. Cannot update settings.")
        return

    try:
        with db_connection.cursor() as cursor:
            # Set allow_media to False
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
# 🌟 New Function: To allow media sending again (/allowmedia) 🌟
# ------------------------------------------------------------------
async def allow_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not await establish_db_connection():
        await update.message.reply_text("Database connection failed. Cannot update settings.")
        return

    try:
        with db_connection.cursor() as cursor:
            # Set allow_media to True
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

# /users command (User Count)
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
# --- New Function (/new) - with Media Permission Check ---
# ------------------------------------------------------------------
async def send_new_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    current_time = datetime.now(timezone.utc) # Use UTC time
    
    # Get message object from command or button click
    if update.message is None:
        message_obj = update.callback_query.message
    else:
        message_obj = update.message
        
    if not await establish_db_connection():
        await message_obj.reply_text("Database connection failed. Cannot fetch media list.")
        return
        
    # 🌟 1. Check allow_media permission 🌟
    try:
        with db_connection.cursor() as cursor:
            cursor.execute(
                "SELECT allow_media FROM users WHERE user_id = %s", (user_id,)
            )
            result = cursor.fetchone()
            # Default to True if user is new or setting is null
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
        # Continue even if DB check fails, to allow service if possible
        pass 

    # 2. Check Cooldown
    try:
        with db_connection.cursor() as cursor:
            cursor.execute(
                "SELECT last_command_time FROM cooldown WHERE user_id = %s", (user_id,)
            )
            result = cursor.fetchone()
            
            if result and result[0]:
                # Treat time from PostgreSQL as UTC
                last_time = result[0].replace(tzinfo=timezone.utc) 
                elapsed = current_time - last_time
                
                if elapsed.total_seconds() < COOLDOWN_TIME_SECONDS:
                    remaining_seconds = COOLDOWN_TIME_SECONDS - elapsed.total_seconds()
                    remaining_minutes = int(remaining_seconds / 60)
                    
                    if remaining_minutes >= 1:
                        # Reply in minutes if more than 1 minute remains
                        await message_obj.reply_text(
                            f"Slow down, darling! You need to wait {remaining_minutes} more minutes "
                            f"before you can request a new photo. Take a breath. 😉"
                        )
                        return
                    else:
                        # Reply in seconds if less than 1 minute remains
                        await message_obj.reply_text(
                            f"Slow down, darling! Wait {int(remaining_seconds)} more seconds. "
                            f"I'm worth the wait, I promise. 😉"
                        )
                        return
    except Exception as e:
        logger.error(f"Cooldown check failed: {e}")
        # Continue if DB check fails
        try:
            db_connection.rollback()
        except:
            pass


    await message_obj.reply_text("Searching for the perfect photo... wait for Tae. 😉")

    # 3. Send Media
    try:
        with db_connection.cursor() as cursor:
            # Get a random media ID from the database
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

            # 4. Update Cooldown Time and Save Sent Message
            with db_connection.cursor() as cursor:
                 # Update cooldown time (using current UTC time)
                 cursor.execute(
                    "INSERT INTO cooldown (user_id, last_command_time) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET last_command_time = EXCLUDED.last_command_time;",
                    (user_id, current_time) 
                 )
                 # Save sent message for 24-hour deletion
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
# --- Function to delete old sent messages (/delete_old_media) ---
# ------------------------------------------------------------------
async def delete_old_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if user is admin
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
                    # If the bot is blocked or removed from the chat, just delete the DB record
                    cursor.execute("DELETE FROM sent_media WHERE id = %s", (msg_id_db,))
                except BadRequest:
                    # Message already deleted, just delete the DB record
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
# --- Function to remove deleted media from DB (/clearmedia) ---
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
                # Test sending the media (This checks if the file is still accessible by Telegram)
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
                
                # Delete the test message immediately
                await context.bot.delete_message(chat_id=ADMIN_TELEGRAM_ID, message_id=temp_msg.message_id) 
                
            except BadRequest as e:
                # If Telegram says 'File not found' or 'file_id is invalid', delete the DB record
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
            
            await asyncio.sleep(0.1) # Small delay to respect Telegram API limits

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
# --- ADMIN Menu Function (/admin) ---
# ------------------------------------------------------------------
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    # Check if user is admin
    if user_id != ADMIN_TELEGRAM_ID:
        await update.message.reply_text("This command is for the admin only. 😉")
        return

    # Create inline keyboard
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
# --- Callback Query Handler (for button clicks) ---
# ------------------------------------------------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    # Check if user is admin
    if user_id != ADMIN_TELEGRAM_ID:
        await query.answer("This action is restricted to the bot admin.")
        return

    await query.answer() # Close the Telegram loading state

    # Edit the message text to show the command is running
    await context.bot.edit_message_text(
        text=f"Running command: {query.data.replace('admin_', '/').upper()}...",
        chat_id=query.message.chat_id,
        message_id=query.message.message_id
    )

    # Call commands based on button data
    if query.data == 'admin_users':
        await user_count(query, context)
    elif query.data == 'admin_new_photo':
        await send_new_photo(query, context)
    elif query.data == 'admin_clearmedia':
        await clear_deleted_media(query, context)
    elif query.data == 'admin_delete_old':
        await delete_old_media(query, context)
    elif query.data == 'admin_broadcast_text':
        # Ask admin for the broadcast message
        await context.bot.send_message(
            chat_id=user_id,
            text="Please type the message you want to broadcast (starts with /broadcast):"
        )


# ------------------------------------------------------------------
# --- Text Broadcast Function (/broadcast) ---
# ------------------------------------------------------------------
async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle message object from command or callback
    if update.message is None:
        message_obj = update.callback_query.message
        user_id = update.callback_query.from_user.id
    else:
        message_obj = update.message
        user_id = update.message.from_user.id

    if user_id != ADMIN_TELEGRAM_ID:
        await message_obj.reply_text("Broadcast command is for the admin only.")
        return

    # Extract broadcast text
    if message_obj.text and message_obj.text.startswith('/broadcast'):
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
# --- Media Broadcast Function (/bmedia) ---
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


# Function to handle text messages (AI Chat)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    if not groq_client:
        await update.message.reply_text("Sorry, my mind is a bit fuzzy right now. Try again later.")
        return
        
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    user_text = update.message.text
    user_username = update.message.from_user.username

    # Get sender info
    if user_username:
        sender_info = f"@{user_username} ({user_name}, ID: {user_id})"
    else:
        sender_info = f"{user_name} (ID: {user_id})"

    # --- Forward Message to Admin ---
    try:
        await context.bot.send_message(
            chat_id=ADMIN_TELEGRAM_ID, 
            text=f"***New Message!***\nFrom: {sender_info}\nMessage: {user_text}"
        )
    except Exception as e:
        logger.error(f"Failed to forward message to admin: {e}")
    # ---------------------------------------------

    # Show "Typing..." action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    try:
        # Start a chat session for the user (to remember context)
        if user_id not in chat_history:
             chat_history[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        chat_history[user_id].append({"role": "user", "content": user_text})
        
        # Send message to Groq API
        chat_completion = groq_client.chat.completions.create(
            messages=chat_history[user_id],
            model="llama-3.1-8b-instant",
        )
        
        reply_text = chat_completion.choices[0].message.content.strip()
        
        # Use emoji generator
        final_reply = add_emojis_based_on_mood(reply_text)
        
        chat_history[user_id].append({"role": "assistant", "content": final_reply})
        
        await update.message.reply_text(final_reply)
        
    except Exception as e:
        logger.error(f"Failed to get response from Groq API: {e}")
        await update.message.reply_text("Oops, I got a little distracted... what were we talking about?")


def main():
    if not all([TOKEN, WEBHOOK_URL, GROQ_API_KEY]):
        logger.error("Error: Required Environment Variables (TOKEN, WEBHOOK_URL, GROQ_API_KEY) are not set.")
        return
    
    # 🛑 Crucial Check: Is DATABASE_URL present?
    if not DATABASE_URL:
        logger.error("Error: DATABASE_URL Environment Variable is not set. Database operations will fail.")
    else:
        logger.info("DATABASE_URL is present. Attempting database operations.")

    application = Application.builder().token(TOKEN).build()

    # Register commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("users", user_count))
    application.add_handler(CommandHandler("broadcast", broadcast_message))
    application.add_handler(CommandHandler("bmedia", bmedia_broadcast))
    application.add_handler(CommandHandler("new", send_new_photo)) 
    application.add_handler(CommandHandler("delete_old_media", delete_old_media)) 
    application.add_handler(CommandHandler("clearmedia", clear_deleted_media))
    application.add_handler(CommandHandler("admin", admin_menu)) 
    
    # 🌟 New Media Control Commands 🌟
    application.add_handler(CommandHandler("stopmedia", stop_media))
    application.add_handler(CommandHandler("allowmedia", allow_media))

    application.add_handler(CallbackQueryHandler(button_handler)) 
    
    # 1. Channel Media Collection Handler
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST & (filters.PHOTO | filters.VIDEO), channel_message_handler))

    # 2. AI Chat Handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_message))

    # Webhook Setup (for 24/7 hosting)
    logger.info(f"Starting webhook on port {PORT}")
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN, 
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
    )

if __name__ == '__main__':
    main()
