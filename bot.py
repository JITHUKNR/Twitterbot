import os
import logging
# from pymongo import MongoClient
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

# ***********************************
# WARNING: YOU MUST INSTALL pymongo
# ***********************************
try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, OperationFailure
except ImportError:
    # If pymongo is not installed, we use a mock class to prevent errors
    class MockClient:
        def __init__(self, *args, **kwargs):
            pass
        def admin(self):
            return self
        def command(self, *args, **kwargs):
            raise ConnectionFailure("pymongo not imported.")
    MongoClient = MockClient
    ConnectionFailure = Exception
    OperationFailure = Exception
    logger.error("pymongo library not found. Please update requirements.txt")


# -------------------- കൂൾഡൗൺ സമയം --------------------
COOLDOWN_TIME_SECONDS = 180 # 3 മിനിറ്റ് = 180 സെക്കൻഡ്
# --------------------------------------------------------

# 🌟 മീഡിയയുടെ ആയുസ്സ് 1 മണിക്കൂർ (60 മിനിറ്റ്) 🌟
MEDIA_LIFETIME_HOURS = 1 
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
# --- MONGO_URI ആണ് ഉപയോഗിക്കേണ്ടത് ---
MONGO_URI = os.environ.get('MONGO_URI') 
# ------------------------------------

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
    "5.  **Language:** Always respond in English. Keep replies short."
)
# ------------------------------------------------------------------

# --- MongoDB സെറ്റപ്പ് വേരിയബിളുകൾ ---
db_client = None
db_collection_users = None
db_collection_media = None
db_collection_sent = None
db_collection_cooldown = None
DB_NAME = "Taekook_bot" # നിങ്ങളുടെ ഡാറ്റാബേസ് നാമം ഇവിടെ നൽകുക
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
# --- ഡാറ്റാബേസ് കണക്ഷൻ സ്ഥാപിക്കുന്ന ഫംഗ്ഷൻ (MongoDB) ---
# ------------------------------------------------------------------
def establish_db_connection():
    global db_client, db_collection_users, db_collection_media, db_collection_sent, db_collection_cooldown
    
    # കണക്ഷൻ നിലവിലുണ്ടോ എന്നും അത് പ്രവർത്തിക്കുന്നുണ്ടോ എന്നും പരിശോധിക്കുന്നു
    if db_client is not None:
        try:
            db_client.admin.command('ping') 
            return True
        except ConnectionFailure as e:
            logger.warning(f"Existing DB connection failed ping test: {e}")
            db_client = None
        except Exception as e:
             logger.error(f"Unexpected error on DB ping: {e}")
             db_client = None

    try:
        if not MONGO_URI: 
            logger.error("MONGO_URI is not set.")
            return False
            
        # പുതിയ കണക്ഷൻ സ്ഥാപിക്കുന്നു
        db_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db_client.admin.command('ping') # ടെസ്റ്റ് കണക്ഷൻ
        
        db = db_client[DB_NAME]
        
        # Collections സെറ്റ് ചെയ്യുന്നു
        db_collection_users = db['users']
        db_collection_media = db['channel_media']
        db_collection_sent = db['sent_media']
        db_collection_cooldown = db['cooldown']
        
        logger.info("MongoDB connection established successfully.")
        return True
    except ConnectionFailure as e:
        logger.error(f"Failed to establish MongoDB connection (ConnectionFailure): {e}")
        db_client = None
        return False
    except Exception as e:
        logger.error(f"Failed to establish MongoDB connection (General Error): {e}")
        db_client = None
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
    
    if file_id and file_type and establish_db_connection():
        try:
            # MongoDB: upsert ഉപയോഗിച്ച് ഇൻസേർട്ട് ചെയ്യുകയോ അപ്ഡേറ്റ് ചെയ്യുകയോ ചെയ്യുന്നു
            db_collection_media.update_one(
                {'message_id': message_id},
                {'$set': {'file_type': file_type, 'file_id': file_id}},
                upsert=True
            )
            logger.info(f"Media collected: ID {message_id}, Type {file_type}")
        except Exception as e:
            logger.error(f"Failed to save media ID to DB: {e}")

# ------------------------------------------------------------------
# --- ചാനൽ മീഡിയ മെസ്സേജ് ഹാൻഡ്ലർ ---
# ------------------------------------------------------------------
async def channel_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Chat ID പൂർണ്ണമായും integers-ൽ താരതമ്യം ചെയ്യണം
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
    if establish_db_connection():
        try:
            # MongoDB: upsert ഉപയോഗിച്ച് യൂസറെ ചേർക്കുകയോ അപ്ഡേറ്റ് ചെയ്യുകയോ ചെയ്യുന്നു
            db_collection_users.update_one(
                {'user_id': user_id},
                {'$set': {
                    'first_name': user_name,
                    'joined_at': datetime.now(timezone.utc),
                    # allow_media: ഇല്ലാത്ത യൂസർക്ക് True എന്ന് default ആയി നൽകുന്നു
                },
                # യൂസർ ഇല്ലെങ്കിൽ പുതിയ Document ഉണ്ടാക്കുന്നു. allow_media default ആയി True ആയിരിക്കും
                '$setOnInsert': {'allow_media': True}},
                upsert=True
            )
            logger.info(f"User added/updated: {user_id}")
        except Exception as e:
            logger.error(f"Failed to add/update user to DB: {e}")

    if user_id in chat_history:
        del chat_history[user_id]
        
    await update.message.reply_text(f'Hello {user_name}, I was just waiting for your message. How can I tempt you today? 😉')

# ------------------------------------------------------------------
# 🌟 പുതിയ ഫംഗ്ഷൻ: മീഡിയ അയക്കുന്നത് നിർത്താൻ (/stopmedia) 🌟
# ------------------------------------------------------------------
async def stop_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not establish_db_connection():
        await update.message.reply_text("Database connection failed. Cannot update settings.")
        return

    try:
        # MongoDB: allow_media False ആക്കുന്നു
        db_collection_users.update_one(
            {'user_id': user_id},
            {'$set': {'allow_media': False}}
        )
        await update.message.reply_text(
            "Understood, darling. I've stopped sending photos for now. "
            "I'll just keep them saved for when you change your mind. 😉"
        )
    except Exception as e:
        logger.error(f"Failed to set allow_media to False: {e}")
        await update.message.reply_text("My circuits are acting up, baby. Couldn't update your setting.")

# ------------------------------------------------------------------
# 🌟 പുതിയ ഫംഗ്ഷൻ: മീഡിയ അയക്കാൻ വീണ്ടും തുടങ്ങാൻ (/allowmedia) 🌟
# ------------------------------------------------------------------
async def allow_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not establish_db_connection():
        await update.message.reply_text("Database connection failed. Cannot update settings.")
        return

    try:
        # MongoDB: allow_media True ആക്കുന്നു
        db_collection_users.update_one(
            {'user_id': user_id},
            {'$set': {'allow_media': True}}
        )
        await update.message.reply_text(
            "Welcome back! Sending you new photos is my pleasure, my love. Try /new now. 🥵"
        )
    except Exception as e:
        logger.error(f"Failed to set allow_media to True: {e}")
        await update.message.reply_text("My circuits are acting up, baby. Couldn't update your setting.")

# /users കമാൻഡ് (യൂസർ കൗണ്ട്)
async def user_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_TELEGRAM_ID:
        await update.message.reply_text("This command is for the admin only.")
        return
        
    count = 0
    if establish_db_connection():
        try:
            # MongoDB: count_documents ഉപയോഗിച്ച് എണ്ണം എടുക്കുന്നു
            count = db_collection_users.count_documents({})
        except Exception as e:
            logger.error(f"Failed to fetch user count: {e}")
    
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Total users: {count}")

# ------------------------------------------------------------------
# --- New ഫംഗ്ഷൻ (/new) - മീഡിയാ പെർമിഷൻ ചെക്കോടുകൂടി ---
# ------------------------------------------------------------------
async def send_new_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ഇവിടെ update.message പരിശോധിക്കുന്നതിനു പകരം effective_user ഉപയോഗിക്കുന്നു
    user_id = update.effective_user.id 
    current_time = datetime.now(timezone.utc) # UTC സമയം ഉപയോഗിക്കുന്നു
    
    # കമാൻഡ് മെസ്സേജിൽ നിന്നോ ബട്ടൺ ക്ലിക്കിൽ നിന്നോ ഉള്ള മെസ്സേജ് ഒബ്ജക്റ്റ് എടുക്കുന്നു
    if update.message is None:
        message_obj = update.callback_query.message
    else:
        message_obj = update.message
        
    if not establish_db_connection():
        await message_obj.reply_text("Database connection failed. Cannot fetch media list.")
        return
        
    # 🌟 1. allow_media പരിശോധിക്കുന്നു 🌟
    allow_media_flag = True
    try:
        # MongoDB: allow_media flag എടുക്കുന്നു
        user_doc = db_collection_users.find_one({'user_id': user_id})
        
        if user_doc and 'allow_media' in user_doc and user_doc['allow_media'] is False:
            allow_media_flag = False
            
            await message_obj.reply_text(
                "You asked me to stop sending media, darling. If you want me to start again, use the command: /allowmedia 😉"
            )
            return
    except Exception as e:
        logger.error(f"Allow media check failed: {e}")
        pass 

    # 2. കൂൾഡൗൺ പരിശോധിക്കുന്നു
    try:
        cooldown_doc = db_collection_cooldown.find_one({'user_id': user_id})
        
        if cooldown_doc and 'last_command_time' in cooldown_doc:
            last_time = cooldown_doc['last_command_time']
            # MongoDB യിൽ നിന്ന് കിട്ടുന്ന സമയം UTC ആയി കണക്കാക്കുന്നു
            last_time = last_time.replace(tzinfo=timezone.utc) 
            elapsed = current_time - last_time
            
            if elapsed.total_seconds() < COOLDOWN_TIME_SECONDS:
                remaining_seconds = COOLDOWN_TIME_SECONDS - elapsed.total_seconds()
                remaining_minutes = int(remaining_seconds / 60)
                
                if remaining_minutes >= 1:
                    await message_obj.reply_text(
                        f"Slow down, darling! You need to wait {remaining_minutes} more minutes "
                        f"before you can request a new photo. Take a breath. 😉"
                    )
                    return
                else:
                    await message_obj.reply_text(
                        f"Slow down, darling! Wait {int(remaining_seconds)} more seconds. "
                        f"I'm worth the wait, I promise. 😉"
                    )
                    return
    except Exception as e:
        logger.error(f"Cooldown check failed: {e}")

    await message_obj.reply_text("Searching for the perfect photo... wait for Tae. 😉")

    # 3. മീഡിയ അയക്കുന്നു
    try:
        # MongoDB: aggregation pipeline ഉപയോഗിച്ച് റാൻഡം ആയി ഒരു മീഡിയ ID എടുക്കുന്നു
        random_media = db_collection_media.aggregate([
            {'$sample': {'size': 1}}
        ])
        
        result = next(random_media, None)

        if result:
            media_type, file_id = result.get('file_type'), result.get('file_id')
            
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
                    has_spoiler=True,
                    # 🔒 ഇവിടെയാണ് protect_content ചേർത്തിരിക്കുന്നത് 🔒
                    protect_content=True
                )
            elif media_type == 'video':
                 sent_msg = await message_obj.reply_video(
                    video=file_id, 
                    caption=caption_text,
                    has_spoiler=True,
                    # 🔒 ഇവിടെയാണ് protect_content ചേർത്തിരിക്കുന്നത് 🔒
                    protect_content=True
                 )
            else:
                 await message_obj.reply_text("Found a media, but the type is unknown.")
                 return

            # 4. കൂൾഡൗൺ ടൈമും അയച്ച മെസ്സേജും അപ്ഡേറ്റ് ചെയ്യുന്നു
            
            # കൂൾഡൗൺ ടൈം അപ്ഡേറ്റ് ചെയ്യുന്നു
            db_collection_cooldown.update_one(
                {'user_id': user_id},
                {'$set': {'last_command_time': current_time}},
                upsert=True
            )
            
            # അയച്ച മെസ്സേജ് ഡിലീറ്റിനായി സേവ് ചെയ്യുന്നു
            db_collection_sent.insert_one({
                'chat_id': message_obj.chat_id, 
                'message_id': sent_msg.message_id, 
                'sent_at': current_time
            })
            
            logger.info(f"Sent media saved and cooldown updated for user {user_id}.")

        else:
            await message_obj.reply_text("I haven't collected any photos yet, baby. Ask the admin to post some! 😔")
        
    except Exception as e:
        logger.error(f"Media sending failed: {e}")
        await message_obj.reply_text("My connection is glitching, baby. I'll send you a better one later! 😘")

# ------------------------------------------------------------------
# --- ഓട്ടോമാറ്റിക് ക്ലീനപ്പ് ഷെഡ്യൂളർ ഫംഗ്ഷൻ (പുതിയത്) ---
# ------------------------------------------------------------------
async def run_hourly_cleanup(application: Application):
    """ഒരു മണിക്കൂർ ഇടവിട്ട് മെസ്സേജുകൾ ഡിലീറ്റ് ചെയ്യാനുള്ള ബാക്ക്ഗ്രൗണ്ട് ടാസ്ക്."""
    # 5 മിനിറ്റ് കാത്തിരിക്കുന്നു (ആദ്യം ബൂട്ട് അപ്പ് ആവാൻ സമയം കൊടുക്കുന്നു)
    await asyncio.sleep(300) 
    
    while True:
        # 1 മണിക്കൂർ (3600 സെക്കൻഡ്) കാത്തിരിക്കുന്നു
        await asyncio.sleep(3600) 
        
        logger.info("Starting scheduled media cleanup...")
        
        if not establish_db_connection():
            logger.error("Database connection failed during scheduled cleanup.")
            # കണക്ഷൻ കിട്ടിയില്ലെങ്കിൽ അടുത്ത സൈക്കിളിൽ വീണ്ടും ശ്രമിക്കും
            continue
        
        # ⏰ ഡിലീറ്റ് ചെയ്യാനുള്ള സമയം (1 മണിക്കൂറിൽ പഴയത്) 
        time_limit = datetime.now(timezone.utc) - timedelta(hours=MEDIA_LIFETIME_HOURS)

        try:
            # MongoDB: 1 മണിക്കൂറിൽ (അല്ലെങ്കിൽ സെറ്റ് ചെയ്ത സമയത്തിൽ) പഴയ മെസ്സേജുകൾ കണ്ടെത്തുന്നു
            messages_to_delete = db_collection_sent.find({'sent_at': {'$lt': time_limit}})
            deleted_count = 0
            
            all_messages = list(messages_to_delete)

            for doc in all_messages:
                try:
                    # മെസ്സേജ് ഡിലീറ്റ് ചെയ്യുന്നു
                    await application.bot.delete_message(chat_id=doc['chat_id'], message_id=doc['message_id'])
                    # വിജയകരമായി ഡിലീറ്റ് ചെയ്ത ശേഷം ഡോക്യുമെൻ്റ് നീക്കം ചെയ്യുന്നു
                    db_collection_sent.delete_one({'_id': doc['_id']})
                    deleted_count += 1
                except (Forbidden, BadRequest):
                    # പെർമിഷൻ ഇല്ലെങ്കിൽ/മെസ്സേജ് നേരത്തെ ഡിലീറ്റ് ആയെങ്കിൽ, DB-യിൽ നിന്ന് നീക്കം ചെയ്യുന്നു
                    db_collection_sent.delete_one({'_id': doc['_id']})
                except Exception as e:
                    logger.error(f"Error deleting scheduled message {doc['message_id']}: {e}")
            
            logger.info(f"Scheduled cleanup finished. Deleted {deleted_count} messages.")

        except Exception as e:
            logger.error(f"Error processing scheduled media deletion: {e}")
            
# ------------------------------------------------------------------
# --- മെസ്സേജ് ഡിലീറ്റ് ചെയ്യാനുള്ള ഫംഗ്ഷൻ (/delete_old_media) ---
# ------------------------------------------------------------------
async def delete_old_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_TELEGRAM_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="This command is for the admin only.")
        return
        
    message_obj = update.effective_message
    
    if not establish_db_connection():
        await message_obj.reply_text("Database connection failed. Cannot delete media.")
        return
    
    # അഡ്മിൻ കമാൻഡിനായിട്ടുള്ള ഡിലീറ്റ് ലോജിക് (1 മണിക്കൂർ)
    time_limit = datetime.now(timezone.utc) - timedelta(hours=MEDIA_LIFETIME_HOURS)

    try:
        # MongoDB: 1 മണിക്കൂറിൽ പഴയ മെസ്സേജുകൾ കണ്ടെത്തുന്നു
        messages_to_delete = db_collection_sent.find({'sent_at': {'$lt': time_limit}})
        
        deleted_count = 0
        
        # Cursor-ന് പകരം list() ഉപയോഗിക്കുന്നു
        all_messages = list(messages_to_delete)

        if not all_messages:
            await message_obj.reply_text("No old media found to delete. Everything is fresh! ✨")
            return

        for doc in all_messages:
            try:
                await context.bot.delete_message(chat_id=doc['chat_id'], message_id=doc['message_id'])
                # വിജയകരമായി ഡിലീറ്റ് ചെയ്ത ശേഷം ഡോക്യുമെൻ്റ് നീക്കം ചെയ്യുന്നു
                db_collection_sent.delete_one({'_id': doc['_id']})
                deleted_count += 1
            except (Forbidden, BadRequest):
                # ബോട്ടിന് പെർമിഷൻ ഇല്ലെങ്കിൽ അല്ലെങ്കിൽ മെസ്സേജ് ഇല്ലെങ്കിൽ, ഡാറ്റാബേസിൽ നിന്ന് നീക്കം ചെയ്യുന്നു
                db_collection_sent.delete_one({'_id': doc['_id']})
            except Exception as e:
                logger.error(f"Error deleting message {doc['message_id']}: {e}")
        
        await message_obj.reply_text(
            f"✅ Successfully deleted {deleted_count} messages older than {MEDIA_LIFETIME_HOURS} hour(s)."
        )

    except Exception as e:
        logger.error(f"Error processing media deletion: {e}")
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

    if not establish_db_connection():
        await message_obj.reply_text("Database connection failed. Cannot perform cleanup.")
        return

    try:
        # MongoDB: എല്ലാ മീഡിയകളും എടുക്കുന്നു
        all_media = list(db_collection_media.find({}))

        deleted_count = 0
        total_count = len(all_media)

        for doc in all_media:
            message_id, media_type, file_id = doc['message_id'], doc['file_type'], doc['file_id']
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
                    db_collection_media.delete_one({'_id': doc['_id']})
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
         # ⏰ ഇവിടെ 1 മണിക്കൂർ എന്ന് മാറ്റിയിരിക്കുന്നു
         InlineKeyboardButton(f"Delete Old Messages ({MEDIA_LIFETIME_HOURS}h) 🗑️", callback_data='admin_delete_old')]
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
    # ഈ ഫംഗ്ഷൻ CommandHandler-ൽ നിന്നോ MessageHandler-ൽ നിന്നോ വിളിക്കപ്പെടാം
    message_obj = update.effective_message
    user_id = update.effective_user.id

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
    
    if establish_db_connection():
        try:
            # MongoDB: എല്ലാ യൂസർമാരുടെയും ID എടുക്കുന്നു
            all_users = [doc['user_id'] for doc in db_collection_users.find({}, {'user_id': 1})]
            
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

    if establish_db_connection():
        try:
            # MongoDB: എല്ലാ യൂസർമാരുടെയും ID എടുക്കുന്നു
            all_users = [doc['user_id'] for doc in db_collection_users.find({}, {'user_id': 1})]
            
            sent_count = 0
            blocked_count = 0
            
            await update.message.reply_text(f"Starting media broadcast ({media_type}) to {len(all_users)} users...")
            
            for target_id in all_users:
                try:
                    if media_type == 'photo':
                        await context.bot.send_photo(
                            chat_id=target_id, 
                            photo=file_id, 
                            caption=caption,
                            # 🔒 ഇവിടെയാണ് protect_content ചേർത്തിരിക്കുന്നത് 🔒
                            protect_content=True 
                        )
                    else: # video
                        await context.bot.send_video(
                            chat_id=target_id, 
                            video=file_id, 
                            caption=caption,
                            # 🔒 ഇവിടെയാണ് protect_content ചേർത്തിരിക്കുന്നത് 🔒
                            protect_content=True
                        )
                        
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
    # 🚨 Syntax Error പരിഹരിക്കുന്നു
    # Note: 'Import os' എന്നത് 'import os' എന്ന് കോഡിൻ്റെ തുടക്കത്തിൽ നിങ്ങൾ മാറ്റണം.
    
    if not all([TOKEN, WEBHOOK_URL, GROQ_API_KEY]):
        logger.error("Error: Required Environment Variables are not set.")
        return

    application = Application.builder().token(TOKEN).build()
    
    # 🌟 ഓട്ടോമാറ്റിക് ക്ലീനപ്പ് ടാസ്ക് തുടങ്ങുന്നു 🌟
    # ഇത് വെബ്ഹൂക്ക് തുടങ്ങുന്നതിന് മുമ്പ് call ചെയ്യണം
    if ADMIN_TELEGRAM_ID: 
        logger.info("Scheduling hourly media cleanup task.")
        application.create_task(run_hourly_cleanup(application))

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
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
    )

if __name__ == '__main__':
    main()
