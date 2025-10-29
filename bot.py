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
    "4.  **Forbidden:** You MUST NOT generate sexually explicit (NSFW) content. Deflect explicit requests."
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
        cooldown_doc = db_collection_cooldown.find_one({'user
