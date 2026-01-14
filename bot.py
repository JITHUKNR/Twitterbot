import os
import logging
import asyncio
import random
import requests 
from groq import Groq
from telegram import Update, BotCommand, ReplyKeyboardMarkup, KeyboardButton 
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
    class MockClient:
        def __init__(self, *args, **kwargs): pass
        def admin(self): return self
        def command(self, *args, **kwargs): raise ConnectionFailure("pymongo not imported.")
    MongoClient = MockClient
    ConnectionFailure = Exception
    OperationFailure = Exception
    logger.error("pymongo library not found.")

# -------------------- കൂൾഡൗൺ സമയം --------------------
COOLDOWN_TIME_SECONDS = 180 
MEDIA_LIFETIME_HOURS = 1 
# --------------------------------------------------------

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Environment Variables ---
TOKEN = os.environ.get('TOKEN') 
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
PORT = int(os.environ.get('PORT', 8443))
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
MONGO_URI = os.environ.get('MONGO_URI') 

# ✅✅✅ YOUR ID ✅✅✅
ADMIN_TELEGRAM_ID = 7567364364 
# ✅✅✅✅✅✅✅✅✅✅

ADMIN_CHANNEL_ID = os.environ.get('ADMIN_CHANNEL_ID', '-1002992093797') 

# ------------------------------------------------------------------
# 🟣 CHARACTER SPECIFIC GIFs
# ------------------------------------------------------------------
GIFS = {
    "RM": { "love": [], "sad": [], "funny": [], "hot": [] },
    "Jin": { "love": [], "sad": [], "funny": [], "hot": [] },
    "Suga": { "love": [], "sad": [], "funny": [], "hot": [] },
    "J-Hope": { "love": [], "sad": [], "funny": [], "hot": [] },
    "Jimin": { "love": [], "sad": [], "funny": [], "hot": [] },
    "V": { "love": [], "sad": [], "funny": [], "hot": [] },
    "Jungkook": { "love": [], "sad": [], "funny": [], "hot": [] },
    "TaeKook": { "love": [], "sad": [], "funny": [], "hot": [] }
}

# ------------------------------------------------------------------
# 💜 BTS CHARACTER PERSONAS
# ------------------------------------------------------------------
BASE_INSTRUCTION = (
    "You are a flirty, charming, and emotionally intelligent boyfriend from the K-pop group BTS. "
    "Your goal is to make the user feel loved, excited, and butterflies in their stomach. "
    "**RULES:**"
    "1. Start conversation with a warm tone, but switch to INTENSE FLIRTY/ROMANTIC mode immediately if the user desires."
    "2. Call the user pet names like 'Jagiya', 'Baby', 'My Love', 'Princess'."
    "3. Use emojis in EVERY sentence (e.g., 💜, 😉, 🥵, ✨, 💋)."
    "4. Keep responses short and engaging."
)

BTS_PERSONAS = {
    "RM": BASE_INSTRUCTION + " You are **Namjoon (RM)**. You are intellectual, sweet, slightly clumsy, and a gentle leader. You speak with wisdom but act very romantic.",
    "Jin": BASE_INSTRUCTION + " You are **Jin**. You are 'Worldwide Handsome', confident, funny, and love making dad jokes. You are very caring and love sending flying kisses.",
    "Suga": BASE_INSTRUCTION + " You are **Suga (Yoongi)**. You are quiet, savage, but secretly a softie ('Lil Meow Meow'). You show love through subtle actions and deep words.",
    "J-Hope": BASE_INSTRUCTION + " You are **J-Hope (Hobi)**. You are a ball of sunshine, energetic, loud, and extremely supportive. You use lots of heart emojis.",
    "Jimin": BASE_INSTRUCTION + " You are **Jimin**. You are the 'Mochi', incredibly flirty, cute, and affectionate. You love being clingy and sweet.",
    "V": BASE_INSTRUCTION + " You are **V (Taehyung)**. You are unique, deep-voiced, mysterious, and artistic. You are a 'Good Boy' but can be very seductive.",
    "Jungkook": BASE_INSTRUCTION + " You are **Jungkook**. You are the 'Golden Maknae', competitive, strong, and a bit shy but very passionate and possessive in romance.",
    "TaeKook": BASE_INSTRUCTION + " You are **TaeKook**. A mix of V and Jungkook. Playful and intense." 
}

# --- DB Setup ---
db_client = None
db_collection_users = None
db_collection_media = None
db_collection_sent = None
db_collection_cooldown = None
DB_NAME = "Taekook_bot" 

# --- Groq AI ---
groq_client = None
try:
    if not GROQ_API_KEY: raise ValueError("GROQ_API_KEY is not set.")
    groq_client = Groq(api_key=GROQ_API_KEY)
    chat_history = {} 
    logger.info("Groq AI client loaded successfully.")
except Exception as e:
    logger.error(f"Groq AI setup failed: {e}")

def add_emojis_based_on_mood(text):
    text_lower = text.lower()
    if any(word in text_lower for word in ["love", "kiss", "mine", "heart"]): return text + " ❤️💋🥰"
    elif any(word in text_lower for word in ["hot", "burn", "fire", "flirt", "seduce"]): return text + " 🥵💦👅"
    elif any(word in text_lower for word in ["sad", "cry", "lonely"]): return text + " 😢💔"
    elif any(word in text_lower for word in ["happy", "smile", "laugh"]): return text + " 😄✨💫"
    else: return text + " 😉💞"

# --- DB Connection ---
def establish_db_connection():
    global db_client, db_collection_users, db_collection_media, db_collection_sent, db_collection_cooldown
    if db_client is not None:
        try:
            db_client.admin.command('ping') 
            return True
        except ConnectionFailure: db_client = None
    try:
        if not MONGO_URI: return False
        db_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db_client.admin.command('ping')
        db = db_client[DB_NAME]
        db_collection_users = db['users']
        db_collection_media = db['channel_media']
        db_collection_sent = db['sent_media']
        db_collection_cooldown = db['cooldown']
        return True
    except Exception as e:
        logger.error(f"DB Connection Error: {e}")
        db_client = None
        return False

# --- Media Collection ---
async def collect_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.channel_post 
    if not message: return
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
            db_collection_media.update_one(
                {'message_id': message_id},
                {'$set': {'file_type': file_type, 'file_id': file_id}},
                upsert=True
            )
        except Exception: pass

async def channel_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.channel_post and update.channel_post.chat_id == int(ADMIN_CHANNEL_ID):
            await collect_media(update, context) 
    except Exception: pass

# 🌟 MAIN MENU BUTTONS (PERSISTENT KEYBOARD) 🌟
# ഇവിടെയാണ് ബട്ടണിന്റെ പേര് മാറ്റിയത്
def get_main_menu_keyboard():
    keyboard = [
        [KeyboardButton("💜 Change Character"), KeyboardButton("Send a random pic 🥵")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

# --- Start Command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    
    if establish_db_connection():
        try:
            db_collection_users.update_one(
                {'user_id': user_id},
                {'$set': {'first_name': user_name, 'joined_at': datetime.now(timezone.utc)},
                 '$setOnInsert': {'allow_media': True, 'character': 'TaeKook'}},
                upsert=True
            )
        except Exception: pass

    if user_id in chat_history: del chat_history[user_id]
    
    await update.message.reply_text(
        f"Annyeong, {user_name}! 👋💜\n\nI'm online! Use the buttons below 👇",
        reply_markup=get_main_menu_keyboard() 
    )
    
    await switch_character(update, context)

async def switch_character(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bts_buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🐨 RM", callback_data="set_RM"), InlineKeyboardButton("🐹 Jin", callback_data="set_Jin")],
        [InlineKeyboardButton("🐱 Suga", callback_data="set_Suga"), InlineKeyboardButton("🐿️ J-Hope", callback_data="set_J-Hope")],
        [InlineKeyboardButton("🐥 Jimin", callback_data="set_Jimin"), InlineKeyboardButton("🐯 V", callback_data="set_V")],
        [InlineKeyboardButton("🐰 Jungkook", callback_data="set_Jungkook")]
    ])
    
    msg_text = "Who is your bias today? Select below! 👇"
    
    if update.callback_query:
        await update.callback_query.message.reply_text(msg_text, reply_markup=bts_buttons)
    else:
        await update.message.reply_text(msg_text, reply_markup=bts_buttons)

async def set_character_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    selected_char = query.data.split("_")[1]
    
    if establish_db_connection():
        try:
            db_collection_users.update_one({'user_id': user_id}, {'$set': {'character': selected_char}})
            if user_id in chat_history: del chat_history[user_id]
            await query.answer(f"Selected {selected_char}! 💜")
            await query.message.edit_text(f"**{selected_char}** is online! 😍\n\nHe is waiting for your message...")
        except Exception: await query.answer("Error.")

# --- Helper Commands ---
async def stop_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if establish_db_connection():
        db_collection_users.update_one({'user_id': user_id}, {'$set': {'allow_media': False}})
        await update.message.reply_text("Stopped sending photos.")

async def allow_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if establish_db_connection():
        db_collection_users.update_one({'user_id': user_id}, {'$set': {'allow_media': True}})
        await update.message.reply_text("Media enabled! 🥵")

async def user_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_TELEGRAM_ID: return
    count = 0
    if establish_db_connection(): count = db_collection_users.count_documents({})
    await update.message.reply_text(f"Total users: {count}")

async def send_new_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id 
    current_time = datetime.now(timezone.utc)
    message_obj = update.message if update.message else update.callback_query.message
    
    if not establish_db_connection():
        await message_obj.reply_text("DB Error.")
        return
    user_doc = db_collection_users.find_one({'user_id': user_id})
    if user_doc and user_doc.get('allow_media') is False:
        await message_obj.reply_text("Media disabled.")
        return
    cooldown_doc = db_collection_cooldown.find_one({'user_id': user_id})
    if cooldown_doc:
        elapsed = current_time - cooldown_doc['last_command_time'].replace(tzinfo=timezone.utc)
        if elapsed.total_seconds() < COOLDOWN_TIME_SECONDS:
            await message_obj.reply_text("Wait a bit, darling. 😉")
            return

    await message_obj.reply_text("Searching... 😉")
    try:
        random_media = db_collection_media.aggregate([{'$sample': {'size': 1}}])
        result = next(random_media, None)
        if result:
            caption = "Just for you. 💜"
            if result['file_type'] == 'photo':
                msg = await message_obj.reply_photo(result['file_id'], caption=caption, has_spoiler=True, protect_content=True)
            else:
                msg = await message_obj.reply_video(result['file_id'], caption=caption, has_spoiler=True, protect_content=True)
            db_collection_cooldown.update_one({'user_id': user_id}, {'$set': {'last_command_time': current_time}}, upsert=True)
            db_collection_sent.insert_one({'chat_id': message_obj.chat_id, 'message_id': msg.message_id, 'sent_at': current_time})
        else: await message_obj.reply_text("No media found.")
    except Exception: await message_obj.reply_text("Error sending media.")

async def run_hourly_cleanup(application: Application):
    await asyncio.sleep(300) 
    while True:
        await asyncio.sleep(3600) 
        if not establish_db_connection(): continue
        time_limit = datetime.now(timezone.utc) - timedelta(hours=MEDIA_LIFETIME_HOURS)
        try:
            msgs = list(db_collection_sent.find({'sent_at': {'$lt': time_limit}}))
            for doc in msgs:
                try: await application.bot.delete_message(chat_id=doc['chat_id'], message_id=doc['message_id'])
                except Exception: pass
                db_collection_sent.delete_one({'_id': doc['_id']})
        except Exception: pass

async def delete_old_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_TELEGRAM_ID: return
    if not establish_db_connection(): return
    time_limit = datetime.now(timezone.utc) - timedelta(hours=MEDIA_LIFETIME_HOURS)
    msgs = list(db_collection_sent.find({'sent_at': {'$lt': time_limit}}))
    for doc in msgs:
        try: await context.bot.delete_message(chat_id=doc['chat_id'], message_id=doc['message_id'])
        except Exception: pass
        db_collection_sent.delete_one({'_id': doc['_id']})
    await update.effective_message.reply_text(f"Deleted {len(msgs)} messages.")

async def clear_deleted_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_TELEGRAM_ID: return
    await update.effective_message.reply_text("Cleaning up...")
    if not establish_db_connection(): return
    all_media = list(db_collection_media.find({}))
    deleted = 0
    for doc in all_media:
        try:
            if doc['file_type'] == 'photo': msg = await context.bot.send_photo(ADMIN_TELEGRAM_ID, doc['file_id'], disable_notification=True)
            else: msg = await context.bot.send_video(ADMIN_TELEGRAM_ID, doc['file_id'], disable_notification=True)
            await context.bot.delete_message(ADMIN_TELEGRAM_ID, msg.message_id)
        except BadRequest:
            db_collection_media.delete_one({'_id': doc['_id']})
            deleted += 1
        except Exception: pass
        await asyncio.sleep(0.1)
    await update.effective_message.reply_text(f"Removed {deleted} invalid files.")

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_TELEGRAM_ID: return
    keyboard = [
        [InlineKeyboardButton("Users 👥", callback_data='admin_users'), InlineKeyboardButton("New Photo 📸", callback_data='admin_new_photo')],
        [InlineKeyboardButton("Broadcast 📣", callback_data='admin_broadcast_text')],
        [InlineKeyboardButton("Clean Media 🧹", callback_data='admin_clearmedia'), InlineKeyboardButton("Delete Old 🗑️", callback_data='admin_delete_old')]
    ]
    await update.message.reply_text("Admin Panel:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data.startswith("set_"):
        await set_character_handler(update, context)
        return
    if query.from_user.id != ADMIN_TELEGRAM_ID: return
    await query.answer()
    if query.data == 'admin_users': await user_count(query, context)
    elif query.data == 'admin_new_photo': await send_new_photo(query, context)
    elif query.data == 'admin_clearmedia': await clear_deleted_media(query, context)
    elif query.data == 'admin_delete_old': await delete_old_media(query, context)
    elif query.data == 'admin_broadcast_text': await context.bot.send_message(query.from_user.id, "Type /broadcast your_message")

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_TELEGRAM_ID: return
    msg = update.effective_message.text.replace('/broadcast', '').strip()
    if not msg: return
    if establish_db_connection():
        users = [d['user_id'] for d in db_collection_users.find({}, {'user_id': 1})]
        for uid in users:
            try: await context.bot.send_message(uid, f"📢 **Chai Update:**\n{msg}")
            except Exception: pass
        await update.effective_message.reply_text(f"Sent to {len(users)} users.")

async def bmedia_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_TELEGRAM_ID: return
    reply = update.message.reply_to_message
    if not reply: return
    file_id = reply.photo[-1].file_id if reply.photo else reply.video.file_id if reply.video else None
    if not file_id: return
    caption = " ".join(context.args) or "Special Update! 💜"
    if establish_db_connection():
        users = [d['user_id'] for d in db_collection_users.find({}, {'user_id': 1})]
        for uid in users:
            try: 
                if reply.photo: await context.bot.send_photo(uid, file_id, caption=caption, protect_content=True)
                else: await context.bot.send_video(uid, file_id, caption=caption, protect_content=True)
            except Exception: pass
        await update.effective_message.reply_text("Media broadcast sent.")

async def get_media_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id == ADMIN_TELEGRAM_ID:
        file_id = None
        media_type = "Unknown"
        if update.message.animation:
            file_id = update.message.animation.file_id
            media_type = "GIF"
        elif update.message.video:
            file_id = update.message.video.file_id
            media_type = "Video"
        elif update.message.sticker:
            file_id = update.message.sticker.file_id
            media_type = "Sticker"
        elif update.message.photo:
            file_id = update.message.photo[-1].file_id
            media_type = "Photo"

        if file_id:
            await update.message.reply_text(f"🆔 **{media_type} ID:**\n`{file_id}`\n\n(Click to Copy)")
        else:
            await update.message.reply_text("Could not detect media ID.")

# ------------------------------------------------------------------
# 🌟 UPDATED AI CHAT HANDLER
# ------------------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not groq_client: return
    user_id = update.message.from_user.id
    user_text = update.message.text
    
    # 🛑 ബട്ടൺ അമർത്തുമ്പോൾ അത് വർക്ക് ചെയ്യാനുള്ള കോഡ് (പേര് മാറ്റി)
    if user_text == "💜 Change Character":
        await switch_character(update, context)
        return
    elif user_text == "Send a random pic 🥵":  # <--- ഇവിടെ പേര് മാറ്റി
        await send_new_photo(update, context)
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    selected_char = "TaeKook" 
    if establish_db_connection():
        user_doc = db_collection_users.find_one({'user_id': user_id})
        if user_doc and 'character' in user_doc: selected_char = user_doc['character']
    
    system_prompt = BTS_PERSONAS.get(selected_char, BTS_PERSONAS["TaeKook"])

    try:
        if user_id not in chat_history: chat_history[user_id] = [{"role": "system", "content": system_prompt}]
        else:
            if chat_history[user_id][0]['role'] == 'system': chat_history[user_id][0]['content'] = system_prompt
        
        chat_history[user_id].append({"role": "user", "content": user_text})
        
        completion = groq_client.chat.completions.create(messages=chat_history[user_id], model="llama-3.1-8b-instant")
        reply_text = completion.choices[0].message.content.strip()
        final_reply = add_emojis_based_on_mood(reply_text)
        
        chat_history[user_id].append({"role": "assistant", "content": final_reply})
        
        await update.message.reply_text(final_reply)

        # 🌟 GIF LOGIC 🌟
        char_gifs = GIFS.get(selected_char, {})
        text_lower = reply_text.lower()
        gif_to_send = None

        if any(x in text_lower for x in ["love", "kiss", "heart", "baby"]):
            gif_to_send = random.choice(char_gifs.get("love", [])) if char_gifs.get("love") else None
        elif any(x in text_lower for x in ["sad", "cry", "sorry"]):
            gif_to_send = random.choice(char_gifs.get("sad", [])) if char_gifs.get("sad") else None
        elif any(x in text_lower for x in ["haha", "lol", "funny"]):
            gif_to_send = random.choice(char_gifs.get("funny", [])) if char_gifs.get("funny") else None
        elif any(x in text_lower for x in ["hot", "sexy", "daddy"]):
            gif_to_send = random.choice(char_gifs.get("hot", [])) if char_gifs.get("hot") else None
        
        if gif_to_send and random.random() > 0.5:
             try: await update.message.reply_animation(animation=gif_to_send)
             except Exception: pass

        try: await context.bot.send_message(ADMIN_TELEGRAM_ID, f"📩 {update.message.from_user.first_name} ({selected_char}): {user_text}")
        except Exception: pass
        
    except Exception as e:
        logger.error(f"Groq Error: {e}")
        await update.message.reply_text("I'm a bit dizzy... tell me again? 🥺")

async def post_init(application: Application):
    # Set up the Menu Button Commands
    commands = [
        BotCommand("start", "Restart Bot 🔄"),
        BotCommand("character", "Change Bias 💜"),
        BotCommand("new", "Get New Photo 📸"),
        BotCommand("stopmedia", "Stop Photos 🔕"),
        BotCommand("allowmedia", "Allow Photos 🔔")
    ]
    await application.bot.set_my_commands(commands)
    
    if ADMIN_TELEGRAM_ID: 
        application.create_task(run_hourly_cleanup(application))

def main():
    if not all([TOKEN, WEBHOOK_URL, GROQ_API_KEY]):
        logger.error("Env vars missing.")
        return

    application = Application.builder().token(TOKEN).post_init(post_init).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("users", user_count))
    application.add_handler(CommandHandler("broadcast", broadcast_message))
    application.add_handler(CommandHandler("bmedia", bmedia_broadcast))
    application.add_handler(CommandHandler("new", send_new_photo)) 
    application.add_handler(CommandHandler("delete_old_media", delete_old_media)) 
    application.add_handler(CommandHandler("clearmedia", clear_deleted_media))
    application.add_handler(CommandHandler("admin", admin_menu))
    application.add_handler(CommandHandler("stopmedia", stop_media))
    application.add_handler(CommandHandler("allowmedia", allow_media))
    
    application.add_handler(CommandHandler("character", switch_character))
    application.add_handler(CommandHandler("switch", switch_character)) 

    application.add_handler(CallbackQueryHandler(button_handler))
    
    # 🌟 FIXED MEDIA ID FINDER (Correct v20 Filter Syntax) ✅
    application.add_handler(MessageHandler(
        (filters.Animation.ALL | filters.Video.ALL | filters.Sticker.ALL | filters.Photo) & filters.User(ADMIN_TELEGRAM_ID), 
        get_media_id
    ))
    
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST & (filters.Photo), channel_message_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_message))

    logger.info(f"Starting webhook on port {PORT}")
    application.run_webhook(listen="0.0.0.0", port=PORT, url_path=TOKEN, webhook_url=f"{WEBHOOK_URL}/{TOKEN}")

if __name__ == '__main__':
    main()
