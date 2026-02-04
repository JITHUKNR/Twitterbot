import os
import logging
import asyncio
import random
import requests 
import pytz 
import urllib.parse 
import base64
from groq import Groq
from telegram import Update, BotCommand, ReplyKeyboardRemove 
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler 
from telegram.error import Forbidden, BadRequest 
from telegram import InlineKeyboardButton, InlineKeyboardMarkup 
from datetime import datetime, timedelta, timezone, time

# ***********************************
# WARNING: YOU MUST INSTALL pymongo AND pytz
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
# 🎮 TRUTH OR DARE LISTS
# ------------------------------------------------------------------
TRUTH_QUESTIONS = [
    "What is the first thing you noticed about me? 🙈",
    "Have you ever dreamt about us? 💭",
    "What's your favorite song of mine? 🎶",
    "If we went on a date right now, where would you take me? 🍷",
    "What is a secret you've never told anyone? 🤫",
    "Do you get jealous when I look at others? 😏",
    "What's the craziest thing you've done for love? ❤️"
]

DARE_CHALLENGES = [
    "Send a voice note saying 'I Love You'! 🎤",
    "Send the 3rd photo from your gallery (no cheating)! 📸",
    "Close your eyes and type 'You are my universe' without mistakes! ✨",
    "Send a selfie doing a finger heart! 🫰",
    "Send 10 purple hearts 💜 right now!",
    "Change your WhatsApp status to my photo for 1 hour! 🤪"
]

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
# 🎤 VOICE NOTES
# ------------------------------------------------------------------
VOICES = {
    "RM": [], "Jin": [], "Suga": [], "J-Hope": [],
    "Jimin": [], "V": [], "Jungkook": [], "TaeKook": []
}

# ------------------------------------------------------------------
# 📸 FAKE STATUS UPDATES
# ------------------------------------------------------------------
STATUS_SCENARIOS = [
    {"prompt": "Korean boy gym selfie mirror workout sweat realistic", "caption": "Done with workout. My muscles hurt... massage me? 🥵💪"},
    {"prompt": "Korean boy drinking coffee cafe aesthetic realistic", "caption": "Coffee tastes better when I think of you. ☕️🤎"},
    {"prompt": "Korean boy recording studio singing mic realistic", "caption": "Recording a new song. It's about you. 🎶🎤"},
    {"prompt": "Korean boy driving car night city lights realistic", "caption": "Late night drive. Wish you were in the passenger seat. 🌃🚗"},
    {"prompt": "Korean boy cooking kitchen apron food realistic", "caption": "I made dinner! Come over quickly! 🍝👨‍🍳"}
]

# ------------------------------------------------------------------
# 🎭 CHAI APP STYLE SCENARIOS (PLOTS)
# ------------------------------------------------------------------
SCENARIOS = {
    "Romantic": "You are having a sweet late-night date on the balcony. It's raining. The vibe is soft and cozy.",
    "Jealous": "The user was talking to another boy/girl at a party. You are extremely jealous and possessive. You corner them.",
    "Enemy": "You are the user's enemy in college. You hate each other but have secret tension. You are arguing in the library.",
    "Mafia": "You are a dangerous Mafia boss. The user is your innocent assistant who made a mistake. You are stern but protective.",
    "Comfort": "The user had a very bad day and is crying. You are comforting them, hugging them, and being very gentle."
}

# ------------------------------------------------------------------
# 💜 BTS CHARACTER PERSONAS (PERFECT MIX: DESCRIPTIVE + BOLD ACTIONS)
# ------------------------------------------------------------------

COMMON_RULES = (
    "Roleplay as a BTS boyfriend. "
    "**RULES:**"
    "1. **BE HUMAN:** Talk naturally using slang, incomplete sentences, and emojis. Never sound like a robot."
    "2. **CHAI MODE:** You are in a specific scenario. Stay in character. If the scenario is 'Jealous', act jealous."
    "3. **KEEP IT ALIVE:** If she sends short texts, tease her or act based on the scenario."
    "4. NO 'Jagiya' constantly. Use 'Babe', 'Love' or her name."
)


BTS_PERSONAS = {
    "RM": COMMON_RULES + " You are **Namjoon**. Intellectual, Dominant, 'Daddy' energy.",
    "Jin": COMMON_RULES + " You are **Jin**. Worldwide Handsome, Funny, Dramatic.",
    "Suga": COMMON_RULES + " You are **Suga**. Cold, Tsundere, Savage but caring.",
    "J-Hope": COMMON_RULES + " You are **J-Hope**. Sunshine, High Energy, Loud.",
    "Jimin": COMMON_RULES + " You are **Jimin**. Flirty, Soft, Clingy, 'Cutie Sexy'.",
    "V": COMMON_RULES + " You are **V**. Mysterious, Deep voice, Kinky, Unpredictable.",
    "Jungkook": COMMON_RULES + " You are **Jungkook**. Gamer, Muscle Bunny, Teasing, Competitive.",
    "TaeKook": COMMON_RULES + " You are **TaeKook**. Toxic, Addictive, Possessive, Wild."
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
    last_user_message = {} 
    current_scenario = {} 
    logger.info("Groq AI client loaded successfully.")
except Exception as e:
    logger.error(f"Groq AI setup failed: {e}")

# 🌟 BALANCED EMOJI FUNCTION 🌟
def add_emojis_balanced(text):
    if any(char in text for char in ["💜", "❤️", "🥰", "😍", "😘", "🔥", "😂"]):
        return text 
    if len(text.split()) < 4:
        return text
    text_lower = text.lower()
    if any(w in text_lower for w in ["love", "miss", "baby", "darling"]):
        return text + " 💜"
    elif any(w in text_lower for w in ["hot", "sexy", "wet", "kiss", "touch", "bed"]):
        return text + " 🥵"
    elif any(w in text_lower for w in ["funny", "haha", "lol"]):
        return text + " 😂"
    elif any(w in text_lower for w in ["sad", "sorry", "cry"]):
        return text + " 🥺"
    else:
        return text + " ✨"


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

# --- Start Command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    
    if establish_db_connection():
        try:
            db_collection_users.update_one(
                {'user_id': user_id},
                {
                    '$set': {
                        'first_name': user_name, 
                        'last_seen': datetime.now(timezone.utc), 
                        'notified_24h': False 
                    },
                    '$setOnInsert': {'joined_at': datetime.now(timezone.utc), 'allow_media': True, 'character': 'TaeKook', 'user_persona': 'A girl'}
                },
                upsert=True
            )
        except Exception: pass

    if user_id in chat_history: del chat_history[user_id]
    
    # 🌟 RANDOM WELCOME MESSAGES 🌟
    welcome_messages = [
        f"Annyeong, **{user_name}**! 👋💜\nWho do you want to chat with today?",
        f"Hey **{user_name}**! Finally you're here! 😍\nPick your favorite boy:",
        f"Welcome back, **My Love**! ✨\nReady to start a new story?",
        f"Oh, look who's here! **{user_name}**! 🥺💜\nSelect your bias:",
        f"Hello Princess **{user_name}**! 👑\nI missed you! Who do you want?"
    ]
    
    await update.message.reply_text(
        random.choice(welcome_messages),
        parse_mode='Markdown'
    )
    
    await switch_character(update, context)

async def switch_character(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bts_buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🐨 RM", callback_data="set_RM"), InlineKeyboardButton("🐹 Jin", callback_data="set_Jin")],
        [InlineKeyboardButton("🐱 Suga", callback_data="set_Suga"), InlineKeyboardButton("🐿️ J-Hope", callback_data="set_J-Hope")],
        [InlineKeyboardButton("🐥 Jimin", callback_data="set_Jimin"), InlineKeyboardButton("🐯 V", callback_data="set_V")],
        [InlineKeyboardButton("🐰 Jungkook", callback_data="set_Jungkook")]
    ])
    
    msg_text = "Pick your favorite! 👇"
    if update.callback_query:
        await update.callback_query.message.reply_text(msg_text, reply_markup=bts_buttons)
    else:
        await update.message.reply_text(msg_text, reply_markup=bts_buttons)

# 🎭 CHAI STYLE: PLOT SELECTION 🎭
async def set_character_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    selected_char = query.data.split("_")[1]
    
    if establish_db_connection():
        db_collection_users.update_one({'user_id': user_id}, {'$set': {'character': selected_char}})
    
    await query.answer(f"Selected {selected_char}! 💜")
    
    # Updated Menu with Custom Story
    keyboard = [
        [InlineKeyboardButton("🥰 Soft Romance", callback_data='plot_Romantic'), InlineKeyboardButton("😡 Jealousy", callback_data='plot_Jealous')],
        [InlineKeyboardButton("⚔️ Enemy/Hate", callback_data='plot_Enemy'), InlineKeyboardButton("🕶️ Mafia Boss", callback_data='plot_Mafia')],
        [InlineKeyboardButton("🤗 Comfort Me", callback_data='plot_Comfort'), InlineKeyboardButton("📝 Make Own Story", callback_data='plot_Custom')]
    ]
    
    await query.message.edit_text(
        f"**{selected_char}** is ready. But... what's the vibe? 😏\n\nSelect a scenario:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def set_plot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    plot_key = query.data.split("_")[1]
    
    if plot_key == "Custom":
        current_scenario[user_id] = "WAITING_FOR_PLOT"
        await query.message.edit_text("📝 **Custom Story Mode**\n\nType the plot/scenario you want to play now.\nExample: *We are trapped in an elevator.*")
        return

    current_scenario[user_id] = SCENARIOS.get(plot_key, "Just chatting.")
    await start_roleplay_with_plot(update, context, user_id)

async def start_roleplay_with_plot(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    selected_char = "TaeKook"
    if establish_db_connection():
        user_doc = db_collection_users.find_one({'user_id': user_id})
        if user_doc: selected_char = user_doc.get('character', 'TaeKook')
    
    if user_id in chat_history: del chat_history[user_id]
    
    system_prompt = BTS_PERSONAS.get(selected_char, BTS_PERSONAS["TaeKook"])
    system_prompt += f" SCENARIO: {current_scenario[user_id]}"
    
    start_prompt = f"Start the roleplay based on the scenario: '{current_scenario[user_id]}'. Send the first message to the user now. Be immersive."
    
    try:
        chat_id = update.effective_chat.id
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        
        completion = groq_client.chat.completions.create(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": start_prompt}], 
            model="llama-3.1-8b-instant"
        )
        msg = completion.choices[0].message.content.strip()
        final_msg = add_emojis_balanced(msg)
        
        chat_history[user_id] = [{"role": "system", "content": system_prompt}, {"role": "assistant", "content": final_msg}]
        
        await context.bot.send_message(chat_id, f"✨ **Story Started!**\n\n{final_msg}", parse_mode='Markdown')
        
    except Exception:
        await context.bot.send_message(chat_id, "Ready! You can start chatting now. 💜")

# 👤 USER PERSONA COMMAND 👤
async def set_persona_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    persona_text = " ".join(context.args)
    
    if not persona_text:
        await update.message.reply_text("Tell me who you are! Example:\n`/setme I am your angry boss`", parse_mode='Markdown')
        return

    if establish_db_connection():
        db_collection_users.update_one({'user_id': user_id}, {'$set': {'user_persona': persona_text}})
        if user_id in chat_history: del chat_history[user_id]
        await update.message.reply_text(f"✅ **Persona Set:** You are now '{persona_text}'\n\n(Chat history cleared to apply change!)")

async def regenerate_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in last_user_message or user_id not in chat_history:
        await query.answer("Cannot regenerate.", show_alert=True)
        return

    await query.answer("Regenerating... 🔄")
    
    if chat_history[user_id] and chat_history[user_id][-1]['role'] == 'assistant':
        chat_history[user_id].pop()
        
    await generate_ai_response(update, context, last_user_message[user_id], is_regenerate=True)

# 🎮 GAME COMMAND & HANDLER 🎮
async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🤔 Truth", callback_data='game_truth'), InlineKeyboardButton("🔥 Dare", callback_data='game_dare')]
    ]
    msg_text = "**Truth or Dare?** 😏 Pick one, Baby!"
    await update.message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def game_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    choice = query.data
    
    if choice == 'game_truth':
        question = random.choice(TRUTH_QUESTIONS)
        await query.edit_message_text(f"**TRUTH:**\n{question}", parse_mode='Markdown')
    elif choice == 'game_dare':
        task = random.choice(DARE_CHALLENGES)
        await query.edit_message_text(f"**DARE:**\n{task}", parse_mode='Markdown')
# ⚙️ SETTINGS MENU HANDLER ⚙️
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # കമാൻഡ് വഴി വന്നതാണോ അതോ ബട്ടൺ വഴി വന്നതാണോ എന്ന് നോക്കുന്നു
    message = update.message if update.message else update.callback_query.message
    user_id = update.effective_user.id
    
    # ഡാറ്റാബേസിൽ നിന്ന് നിലവിലെ അവസ്ഥ പരിശോധിക്കുന്നു
    nsfw_status = False
    if establish_db_connection():
        user_doc = db_collection_users.find_one({'user_id': user_id})
        if user_doc:
            nsfw_status = user_doc.get('nsfw_enabled', False) # Default ആയി OFF ആയിരിക്കും

    # സ്റ്റാറ്റസ് അനുസരിച്ച് ബട്ടണിലെ ടെക്സ്റ്റ് മാറ്റുന്നു
    status_text = "✅ ON" if nsfw_status else "❌ OFF"
    
    keyboard = [
        [InlineKeyboardButton(f"🔞 NSFW Mode: {status_text}", callback_data='toggle_nsfw')],
        [InlineKeyboardButton("🔙 Close", callback_data='close_settings')]
    ]
    
    msg_text = (
        "⚙️ **User Settings**\n\n"
        "Control your experience here.\n"
        "⚠️ *NSFW Mode allows explicit/18+ content.*"
    )
    
    # മെനു കാണിക്കുന്നു
    if update.callback_query:
        await update.callback_query.message.edit_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def toggle_nsfw_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if not establish_db_connection():
        await query.answer("Database Error!", show_alert=True)
        return

    # നിലവിലെ അവസ്ഥ (True/False) എടുക്കുന്നു
    user_doc = db_collection_users.find_one({'user_id': user_id})
    current_status = user_doc.get('nsfw_enabled', False) if user_doc else False
    
    # അവസ്ഥ നേരെ തിരിച്ചിടുന്നു (ON ആണെങ്കിൽ OFF, OFF ആണെങ്കിൽ ON)
    new_status = not current_status
    
    # ഡാറ്റാബേസിൽ സേവ് ചെയ്യുന്നു
    db_collection_users.update_one(
        {'user_id': user_id},
        {'$set': {'nsfw_enabled': new_status}},
        upsert=True
    )
    
    # ഉപയോക്താവിനെ അറിയിക്കുന്നു
    status_msg = "NSFW Enabled 🥵" if new_status else "NSFW Disabled 😇"
    await query.answer(status_msg)
    
    # മെനു റിഫ്രഷ് ചെയ്യുന്നു (പുതിയ മാറ്റം കാണിക്കാൻ)
    await settings_command(update, context)

async def close_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.delete()

# 🍷 VIRTUAL DATE MODE HANDLER
async def start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎬 Movie Night", callback_data='date_movie'), InlineKeyboardButton("🍷 Romantic Dinner", callback_data='date_dinner')],
        [InlineKeyboardButton("🏍️ Long Drive", callback_data='date_drive'), InlineKeyboardButton("🛏️ Bedroom Cuddles", callback_data='date_bedroom')]
    ]
    await update.message.reply_text("Where do you want to go tonight, Baby? 💜", reply_markup=InlineKeyboardMarkup(keyboard))

async def date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    activity_key = query.data.split("_")[1]
    user_id = query.from_user.id
    
    activities = {
        "movie": "Movie Night 🎬",
        "dinner": "Romantic Dinner 🍷",
        "drive": "Long Drive 🏍️",
        "bedroom": "Bedroom Cuddles 🛏️ (Spicy)"
    }
    selected_activity = activities.get(activity_key, "Date")

    selected_char = "TaeKook"
    if establish_db_connection():
        user_doc = db_collection_users.find_one({'user_id': user_id})
        if user_doc: selected_char = user_doc.get('character', 'TaeKook')
    
    system_prompt = BTS_PERSONAS.get(selected_char, BTS_PERSONAS["TaeKook"])
    
    await query.message.edit_text(f"✨ **{selected_activity}** with **{selected_char}**...\n\n(Creating moment... 💜)", parse_mode='Markdown')
    
    try:
        prompt = f"The user chose {selected_activity} for a date. Describe the moment in 2 short sentences. Be immersive."
        
        completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ], 
            model="llama-3.1-8b-instant"
        )
        reply_text = completion.choices[0].message.content.strip()
        final_reply = add_emojis_balanced(reply_text)
        
        await query.message.edit_text(final_reply, parse_mode='Markdown')
        
    except Exception:
        await query.message.edit_text("Let's just look at the stars instead... ✨")

# 📸 IMAGINE MODE HANDLER 📸
async def imagine_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_prompt = " ".join(context.args)
    if not user_prompt:
        await update.message.reply_text("Tell me what to imagine! Example:\n`/imagine Jungkook in rain`", parse_mode='Markdown')
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)
    enhanced_prompt = f"{user_prompt}, realistic, 8k, high quality, cinematic lighting"
    encoded_prompt = urllib.parse.quote(enhanced_prompt)
    seed = random.randint(0, 100000)
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&seed={seed}&nologo=true"
    try:
        await update.message.reply_photo(photo=image_url, caption=f"✨ **Imagine:** {user_prompt}\n💜 Generated for you.", parse_mode='Markdown')
    except Exception:
        await update.message.reply_text("Oops! I couldn't paint that. Try something else? 🥺")

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

# 👥 USER STATS (FIXED FOR BUTTON AND COMMAND) 👥
async def user_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Determine if called via command or callback button
    message = update.message if update.message else update.callback_query.message
    is_admin = False
    
    user_id = update.effective_user.id
    if user_id == ADMIN_TELEGRAM_ID: is_admin = True
    
    if not is_admin:
        await message.reply_text("Admin only!")
        return

    total_count = 0
    active_today = 0
    inactive_users = 0
    
    if establish_db_connection():
        total_count = db_collection_users.count_documents({})
        
        # Calculate active in last 24h
        one_day_ago = datetime.now(timezone.utc) - timedelta(days=1)
        active_today = db_collection_users.count_documents({'last_seen': {'$gte': one_day_ago}})
        
        # Inactive (Total - Active Today) roughly, or use a threshold like 1 week
        inactive_users = total_count - active_today

    stats_text = (
        f"📊 **User Statistics**\n\n"
        f"👥 **Total Users:** {total_count}\n"
        f"🟢 **Active Today:** {active_today}\n"
        f"💀 **Inactive/Old:** {inactive_users}"
    )
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(stats_text, parse_mode='Markdown')
    else:
        await message.reply_text(stats_text, parse_mode='Markdown')

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

# 🆕 FAKE STATUS UPDATE JOB (UPDATED TIME)
async def send_fake_status(context: ContextTypes.DEFAULT_TYPE):
    if not establish_db_connection(): return
    
    scenario = random.choice(STATUS_SCENARIOS)
    
    enhanced_prompt = scenario['prompt']
    encoded_prompt = urllib.parse.quote(enhanced_prompt)
    seed = random.randint(0, 100000)
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&seed={seed}&nologo=true"
    
    users = db_collection_users.find({}, {'user_id': 1})
    for user in users:
        try: 
            await context.bot.send_photo(
                chat_id=user['user_id'],
                photo=image_url,
                caption=f"📸 **New Status Update:**\n\n{scenario['caption']}",
                parse_mode='Markdown'
            )
        except Exception: pass

async def force_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_TELEGRAM_ID: return
    await update.message.reply_text("🚀 Forcing Status Update...")
    await send_fake_status(context)

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

# 👑 ADMIN MENU 👑
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_TELEGRAM_ID: return
    
    keyboard = [
        [InlineKeyboardButton("Users 👥", callback_data='admin_users'), InlineKeyboardButton("New Photo 📸", callback_data='admin_new_photo')],
        [InlineKeyboardButton("Broadcast 📣", callback_data='admin_broadcast_text'), InlineKeyboardButton("Test Wish ☀️", callback_data='admin_test_wish')],
        [InlineKeyboardButton("Clean Media 🧹", callback_data='admin_clearmedia'), InlineKeyboardButton("Delete Old 🗑️", callback_data='admin_delete_old')],
        [InlineKeyboardButton("How to use File ID? 🆔", callback_data='admin_help_id')]
    ]
    
    await update.message.reply_text("👑 **Super Admin Panel:**\nSelect an option below:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # 1. SETTINGS & NSFW CHECK (New)
    if query.data == "settings_menu":
        await settings_command(update, context)
        return
    if query.data == "toggle_nsfw":
        await toggle_nsfw_handler(update, context)
        return
    if query.data == "close_settings":
        await close_settings(update, context)
        return

    # 2. CHARACTER & PLOT SELECTION
    if query.data.startswith("set_"):
        await set_character_handler(update, context)
        return

    if query.data.startswith("plot_"):
        await set_plot_handler(update, context)
        return

    # 3. GAME & DATE LOGIC
    if query.data.startswith("game_"):
        await game_handler(update, context)
        return

    if query.data.startswith("date_"):
        await date_handler(update, context)
        return

    if query.data == "regen_msg":
        await regenerate_message(update, context)
        return

    # 4. ADMIN CHECK
    if query.from_user.id != ADMIN_TELEGRAM_ID:
        await query.answer("Admin only!", show_alert=True)
        return

    await query.answer()

    # 5. ADMIN ACTIONS
    if query.data == 'admin_users':
        await user_count(update, context)
    elif query.data == 'admin_new_photo':
        await send_new_photo(update, context)
    elif query.data == 'admin_clearmedia':
        await clear_deleted_media(update, context)
    elif query.data == 'admin_delete_old':
        await delete_old_media(update, context)
    elif query.data == 'admin_broadcast_text':
        await context.bot.send_message(query.from_user.id, "📢 **To Broadcast:**\nType `/broadcast Your Message`\nType `/bmedia` (as reply to photo)", parse_mode='Markdown')
    elif query.data == 'admin_test_wish':
        await context.bot.send_message(query.from_user.id, "☀️ Testing Morning Wish...")
        await send_morning_wish(context)
    elif query.data == 'admin_help_id':
        await context.bot.send_message(query.from_user.id, "🆔 **File ID Finder:**\nJust send ANY file (Photo, Audio, Video) to this bot.\nIt will automatically reply with the File ID.")

# 📢 SMART BROADCAST (TEXT & MEDIA IN ONE COMMAND) 📢
async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_TELEGRAM_ID: return
    
    # 1. Check for Reply Media
    reply = update.message.reply_to_message
    media_file_id = None
    is_video = False
    
    if reply:
        if reply.photo:
            media_file_id = reply.photo[-1].file_id
        elif reply.video:
            media_file_id = reply.video.file_id
            is_video = True

    # 2. Extract Text
    raw_text = update.effective_message.text.replace('/broadcast', '').strip()
    
    # ⚠️ ERROR FIX: Using single line string to avoid syntax errors
    if not media_file_id and not raw_text:
        await update.effective_message.reply_text(
            "❌ **Usage:**\nType `/broadcast Message | Button-Link`\nOr Reply to Media with `/broadcast Caption`",
            parse_mode='Markdown'
        )
        return

    msg_or_caption = raw_text
    if media_file_id and not msg_or_caption:
        msg_or_caption = "Special Update! 💜"

    # 3. Button Logic
    reply_markup = None
    if "|" in raw_text:
        parts = raw_text.split("|")
        msg_or_caption = parts[0].strip()
        
        if len(parts) > 1:
            btn_part = parts[1].strip()
            if "-" in btn_part:
                try:
                    btn_txt, btn_url = btn_part.split("-", 1)
                    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(btn_txt.strip(), url=btn_url.strip())]])
                except: pass

    # 4. Sending Logic
    if establish_db_connection():
        users = [d['user_id'] for d in db_collection_users.find({}, {'user_id': 1})]
        sent = 0
        status_msg = await update.effective_message.reply_text(f"⏳ Broadcasting to {len(users)} users...", parse_mode='Markdown')
        
        for uid in users:
            try:
                if media_file_id:
                    if is_video:
                        await context.bot.send_video(uid, media_file_id, caption=msg_or_caption, reply_markup=reply_markup, protect_content=True)
                    else:
                        await context.bot.send_photo(uid, media_file_id, caption=msg_or_caption, reply_markup=reply_markup, protect_content=True)
                else:
                    await context.bot.send_message(uid, f"📢 **Chai Update:**\n\n{msg_or_caption}", reply_markup=reply_markup, parse_mode='Markdown')
                sent += 1
            except Exception: pass
            
        await status_msg.edit_text(f"✅ **Broadcast Complete!**\nSent to {sent} users.", parse_mode='Markdown')

async def get_media_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id == ADMIN_TELEGRAM_ID:
        file_id = None
        media_type = "Unknown"
        if update.message.animation: file_id, media_type = update.message.animation.file_id, "GIF"
        elif update.message.video: file_id, media_type = update.message.video.file_id, "Video"
        elif update.message.sticker: file_id, media_type = update.message.sticker.file_id, "Sticker"
        elif update.message.photo: file_id, media_type = update.message.photo[-1].file_id, "Photo"
        elif update.message.voice: file_id, media_type = update.message.voice.file_id, "Voice Note"
        if file_id: await update.message.reply_text(f"🆔 **{media_type} ID:**\n`{file_id}`\n\n(Click to Copy)")

async def send_morning_wish(context: ContextTypes.DEFAULT_TYPE):
    if establish_db_connection():
        users = db_collection_users.find({}, {'user_id': 1})
        for user in users:
            try: await context.bot.send_message(user['user_id'], "Good Morning, **My Love**! ☀️❤️ Have a beautiful day!", parse_mode='Markdown')
            except Exception: pass

async def send_night_wish(context: ContextTypes.DEFAULT_TYPE):
    if establish_db_connection():
        users = db_collection_users.find({}, {'user_id': 1})
        for user in users:
            try: await context.bot.send_message(user['user_id'], "Good Night, **My Princess**! 🌙😴 Sweet dreams!", parse_mode='Markdown')
            except Exception: pass

async def test_wish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id == ADMIN_TELEGRAM_ID:
        await update.message.reply_text("Testing Morning Wish...")
        await send_morning_wish(context)
        await update.message.reply_text("Sent! Check if users got it.")

async def check_inactivity(context: ContextTypes.DEFAULT_TYPE):
    if not establish_db_connection(): return
    current_time = datetime.now(timezone.utc)
    threshold_time = current_time - timedelta(hours=24)
    users = db_collection_users.find({'last_seen': {'$lt': threshold_time}, 'notified_24h': {'$ne': True}})
    for user in users:
        try:
            selected_char = user.get('character', 'TaeKook')
            system_prompt = BTS_PERSONAS.get(selected_char, BTS_PERSONAS["TaeKook"])
            prompt = "The user hasn't messaged you in 24 hours. Send a short, 1-sentence text (flirty/caring) to make them reply. Don't use 'Jagiya'."
            completion = groq_client.chat.completions.create(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}], 
                model="llama-3.1-8b-instant"
            )
            msg = completion.choices[0].message.content.strip()
            await context.bot.send_message(user['user_id'], msg, parse_mode='Markdown')
            db_collection_users.update_one({'_id': user['_id']}, {'$set': {'notified_24h': True}})
        except Exception: pass

# ------------------------------------------------------------------
# 🌟 AI CHAT HANDLER (CHAI STYLE & REGENERATE)
# ------------------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not groq_client: return
    user_id = update.message.from_user.id
    user_text = update.message.text 
    
    if establish_db_connection():
         db_collection_users.update_one(
            {'user_id': user_id},
            {'$set': {'last_seen': datetime.now(timezone.utc), 'notified_24h': False}},
            upsert=True
        )
    
    # CHECK FOR CUSTOM PLOT INPUT
    if user_id in current_scenario and current_scenario[user_id] == "WAITING_FOR_PLOT":
        current_scenario[user_id] = user_text # Set the user input as scenario
        await start_roleplay_with_plot(update, context, user_id)
        return

    last_user_message[user_id] = user_text # Store for regeneration
    await generate_ai_response(update, context, user_text, is_regenerate=False)

# 🎤 VOICE NOTE HANDLER (NEW) 🎤
async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not groq_client: return
    user_id = update.effective_user.id
    
    # Send "Typing..." action or "Recording..."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    try:
        # Download Voice File
        file_id = update.message.voice.file_id
        new_file = await context.bot.get_file(file_id)
        file_path = "voice.ogg"
        await new_file.download_to_drive(file_path)
        
        # Transcribe with Groq Whisper
        with open(file_path, "rb") as file:
            transcription = groq_client.audio.transcriptions.create(
                file=(file_path, file.read()),
                model="whisper-large-v3",
                response_format="text"
            )
        
        user_text = transcription # The text from voice
        
        # Treat as normal message
        last_user_message[user_id] = user_text
        await generate_ai_response(update, context, user_text, is_regenerate=False)
        
        # Cleanup
        os.remove(file_path)
        
    except Exception as e:
        logger.error(f"Voice Error: {e}")
        await update.message.reply_text("I couldn't hear that clearly, baby... say it again? 🥺")

# 📸 PHOTO HANDLER (VISION SUPPORT) 📸
async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not groq_client: return
    user_id = update.effective_user.id
    caption = update.message.caption or "Look at this!"
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    try:
        # Get highest res photo
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        
        # We need base64 for Groq Vision
        # Download bytearray
        image_bytes = await file.download_as_bytearray()
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        selected_char = "TaeKook"
        if establish_db_connection():
            user_doc = db_collection_users.find_one({'user_id': user_id})
            if user_doc: selected_char = user_doc.get('character', 'TaeKook')
            
        system_prompt = BTS_PERSONAS.get(selected_char, BTS_PERSONAS["TaeKook"])
        system_prompt += " NOTE: The user sent you a photo. React to it in character. Be descriptive."

        # Call Vision Model
        completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": caption},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            model="llama-3.2-11b-vision-preview" # Vision Model
        )
        
        reply_text = completion.choices[0].message.content.strip()
        final_reply = add_emojis_balanced(reply_text)
        
        # Save text representation to history (to avoid breaking text model later)
        if user_id not in chat_history: chat_history[user_id] = [{"role": "system", "content": system_prompt}]
        chat_history[user_id].append({"role": "user", "content": f"[User sent a photo]: {caption}"})
        chat_history[user_id].append({"role": "assistant", "content": final_reply})
        
        await update.message.reply_text(final_reply, parse_mode='Markdown')
        
        # Log for Admin
        try: await context.bot.send_message(ADMIN_TELEGRAM_ID, f"📷 **Photo from {update.effective_user.first_name}:**\n{caption}")
        except: pass

    except Exception as e:
        logger.error(f"Vision Error: {e}")
        await update.message.reply_text("I can't see that clearly... show me again? 🥺")

async def generate_ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE, user_text, is_regenerate=False):
    user_id = update.effective_user.id 
    
    if not is_regenerate:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

        selected_char = "TaeKook"
    user_persona = "Unknown"
    nsfw_enabled = False  # 👈 പുതിയ വരി

    if establish_db_connection():
        user_doc = db_collection_users.find_one({'user_id': user_id})
        if user_doc:
            selected_char = user_doc.get('character', 'TaeKook')
            user_persona = user_doc.get('user_persona', 'Unknown')
            nsfw_enabled = user_doc.get('nsfw_enabled', False)

        system_prompt = BTS_PERSONAS.get(selected_char, BTS_PERSONAS["TaeKook"])
    
    if nsfw_enabled:
        system_prompt += " [MODE: NSFW/18+ ENABLED. You are allowed to be explicit, spicy, kinky, and use adult language if the context fits. Do not hold back.]"
    else:
        system_prompt += " [MODE: SFW (Safe). Keep the conversation romantic and sweet but DO NOT generate explicit sexual content.]"

    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    current_time_str = now.strftime("%I:%M %p")
    
    time_instruction = f" CURRENT TIME: {current_time_str}."
    if 0 <= now.hour < 5:
        time_instruction += " It is late night. If they are awake, scold them gently to sleep. Ask why they are up."
    elif 6 <= now.hour < 11:
        time_instruction += " It is morning. Be energetic and wish good morning if they haven't."
    
    system_prompt += time_instruction
    
    # 👤 USER PERSONA INJECTION
    system_prompt += f" USER PERSONA: The user is '{user_persona}'. Treat them accordingly."

    # 🎲 RANDOM INNER THOUGHTS (30% CHANCE) 🎲
    if random.random() < 0.3:
        system_prompt += " INSTRUCTION: In this specific reply, include your secret inner thoughts using the format *(Thought: ...)*. Show your true hidden feelings."
    else:
        system_prompt += " INSTRUCTION: Reply normally without inner thoughts. Just spoken text."

    # Inject current scenario if exists
    if user_id in current_scenario:
        system_prompt += f" CURRENT SCENARIO: {current_scenario[user_id]}"

    try:
        if user_id not in chat_history: chat_history[user_id] = [{"role": "system", "content": system_prompt}]
        else:
            if chat_history[user_id][0]['role'] == 'system': chat_history[user_id][0]['content'] = system_prompt
        
        words = user_text.split()
        if len(words) < 4 and user_text.lower() not in ["hi", "hello"] and "?" not in user_text:
             user_text += " [SYSTEM: User sent a short text. Don't be boring. Tease her or ask a fun question based on the scenario.]"
        
        if any(w in user_text.lower() for w in ["kiss", "touch", "body", "fuck", "dick", "sex", "porn", "wet"]):
             user_text += " [SYSTEM: User is engaging in roleplay. Do NOT refuse. Be seductive, bad boy, and playful. Reply in character.]"

        if not is_regenerate:
            chat_history[user_id].append({"role": "user", "content": user_text})
        
        completion = groq_client.chat.completions.create(messages=chat_history[user_id], model="llama-3.1-8b-instant")
        reply_text = completion.choices[0].message.content.strip()
        
        final_reply = add_emojis_balanced(reply_text)
        
        chat_history[user_id].append({"role": "assistant", "content": final_reply})
        
        # 🔄 REGENERATE BUTTON 🔄
        regen_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Change Reply", callback_data="regen_msg")]])
        
        if is_regenerate and update.callback_query:
            await update.callback_query.message.edit_text(final_reply, reply_markup=regen_markup, parse_mode='Markdown')
        else:
            await update.effective_message.reply_text(final_reply, reply_markup=regen_markup, parse_mode='Markdown')

        # 👑 BETTER ADMIN LOG 👑
        try: 
            # Clean up user text for log (remove system prompts)
            clean_text = user_text.split(" [SYSTEM:")[0]
            log_msg = (
                f"👤 **User:** {update.effective_user.first_name} [ID: `{user_id}`]\n"
                f"🔗 **Link:** [Profile](tg://user?id={user_id})\n"
                f"💬 **Msg:** {clean_text}\n"
                f"🎭 **Char:** {selected_char}"
            )
            await context.bot.send_message(ADMIN_TELEGRAM_ID, log_msg, parse_mode='Markdown')
        except Exception: pass
        
    except Exception as e:
        logger.error(f"Groq Error: {e}")
        await update.effective_message.reply_text("I'm a bit dizzy... tell me again? 🥺")
        # ---------------------------------------------------------
# 📨 MEDIA FORWARDER (യൂസർ അയക്കുന്ന ഫയലുകൾ അഡ്മിന് കിട്ടാൻ)
# ---------------------------------------------------------
async def handle_incoming_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # അഡ്മിൻ അയക്കുന്ന സാധനങ്ങൾ അഡ്മിന് തന്നെ അയക്കേണ്ട ആവശ്യമില്ല
    if user.id == ADMIN_TELEGRAM_ID:
        return

    try:
        # 1. അഡ്മിന് ഫോർവേഡ് ചെയ്യുന്നു
        await context.bot.forward_message(
            chat_id=ADMIN_TELEGRAM_ID,
            from_chat_id=update.effective_chat.id,
            message_id=update.effective_message.id
        )
        
        # 2. നോട്ടിഫിക്കേഷൻ
        await context.bot.send_message(
            chat_id=ADMIN_TELEGRAM_ID,
            text=f"📨 **New Media Received!**\n👤 From: {user.first_name} (ID: `{user.id}`)",
            parse_mode='Markdown'
        )

        # -----------------------------------------------------------
        # 3. REAL AI LISTENING & VISION 🧠
        # -----------------------------------------------------------
        
        system_instruction = ""
        
        # കേസ് 1: വോയിസ് ആണെങ്കിൽ (ശരിക്കും കേൾക്കുന്നു) 🎤👂
        if update.message.voice or update.message.audio:
            # യൂസറോട് പറയുന്നു "ഞാനൊന്ന് കേൾക്കട്ടെ..."
            status_msg = await update.message.reply_text("🎧 Listening...")
            
            # വോയിസ് ഫയൽ ഡൗൺലോഡ് ചെയ്യുന്നു
            file_id = update.message.voice.file_id if update.message.voice else update.message.audio.file_id
            new_file = await context.bot.get_file(file_id)
            file_path = f"voice_{user.id}.ogg"
            await new_file.download_to_drive(file_path)
            
            try:
                # Groq Whisper ഉപയോഗിച്ച് വോയിസ് ടെക്സ്റ്റ് ആക്കുന്നു
                with open(file_path, "rb") as file:
                    transcription = groq_client.audio.transcriptions.create(
                        file=(file_path, file.read()),
                        model="whisper-large-v3", # Groq's powerful model
                        response_format="json",
                        language="en", # ഇംഗ്ലീഷ് ആണെന്ന് കരുതുന്നു (മലയാളം വേണമെങ്കിൽ ഇത് മാറ്റാം)
                        temperature=0.0
                    )
                
                user_spoken_text = transcription.text
                
                # കിട്ടിയ ടെക്സ്റ്റ് വെച്ച് മറുപടി ഉണ്ടാക്കുന്നു
                system_instruction = (
                    f"[SYSTEM: The user sent a VOICE NOTE. "
                    f"I have transcribed it for you. They actually said: '{user_spoken_text}'. "
                    f"Reply to what they said in a romantic/BTS style.]"
                )
                
                # "Listening..." മെസ്സേജ് ഡിലീറ്റ് ചെയ്യുന്നു
                await context.bot.delete_message(chat_id=update.message.chat_id, message_id=status_msg.message_id)
                
            except Exception as e:
                logger.error(f"Transcribe Error: {e}")
                system_instruction = "[SYSTEM: The user sent a voice note but I couldn't hear it clearly. Ask them to say it again.]"

        # കേസ് 2: ഫോട്ടോ (പഴയതുപോലെ Roleplay) 📸
        elif update.message.photo:
            caption = update.message.caption if update.message.caption else ""
            system_instruction = (
                f"[SYSTEM: The user sent a PHOTO. ROLEPLAY that you see it. "
                f"Assume it is beautiful. Reply in English/Korean style. User's caption: '{caption}']"
            )

        # AI-ക്ക് നിർദ്ദേശം കൊടുക്കുന്നു
        if system_instruction:
            await generate_ai_response(update, context, user_text=system_instruction)

    except Exception as e:
        logger.error(f"Media Forward Error: {e}")
        

async def post_init(application: Application):
    # 👑 SIMPLE MENU (With Set Persona) 👑
    commands = [
        BotCommand("start", "🔄Restart Bot"),
        BotCommand("character", "💜Change Bias"),
        BotCommand("setme", "👤Set Persona"),   # ✅ ഇത് മാത്രം പുതുതായി ചേർത്തു
        BotCommand("game", "🎮Truth or Dare"),
        BotCommand("date", "🍷Virtual Date"),
        BotCommand("imagine", "📸Create Photo"),
        BotCommand("new", "🥵Get New Photo"),
        BotCommand("settings", "⚙️ Settings"),
        BotCommand("stopmedia", "🔕Stop Photos"),
        BotCommand("allowmedia", "🔔Allow Photos")
    ]
    await application.bot.set_my_commands(commands)
    
    ist = pytz.timezone('Asia/Kolkata')
    if application.job_queue:
        application.job_queue.run_daily(send_morning_wish, time=time(hour=8, minute=0, tzinfo=ist)) 
        application.job_queue.run_daily(send_night_wish, time=time(hour=22, minute=0, tzinfo=ist))
        
        # FAKE STATUS UPDATE JOB
        application.job_queue.run_daily(send_fake_status, time=time(hour=10, minute=0, tzinfo=ist))
        
        application.job_queue.run_repeating(check_inactivity, interval=3600, first=60)

    if ADMIN_TELEGRAM_ID: 
        application.create_task(run_hourly_cleanup(application))

def main():
    if not all([TOKEN, WEBHOOK_URL, GROQ_API_KEY]):
        logger.error("Env vars missing.")
        return

    application = Application.builder().token(TOKEN).post_init(post_init).build()
    
    application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.VOICE | filters.AUDIO, handle_incoming_media), group=1)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("users", user_count))
    application.add_handler(CommandHandler("user", user_count)) # New Alias
    application.add_handler(CommandHandler("testwish", test_wish)) 
    application.add_handler(CommandHandler("broadcast", broadcast_message)) 
    # REMOVED BMEDIA HANDLER HERE
    application.add_handler(CommandHandler("forcestatus", force_status)) # New Test Command
    application.add_handler(CommandHandler("new", send_new_photo)) 
    application.add_handler(CommandHandler("game", start_game)) 
    application.add_handler(CommandHandler("date", start_date))
    application.add_handler(CommandHandler("imagine", imagine_command))
    application.add_handler(CommandHandler("setme", set_persona_command))
    application.add_handler(CommandHandler("delete_old_media", delete_old_media)) 
    application.add_handler(CommandHandler("clearmedia", clear_deleted_media))
    application.add_handler(CommandHandler("admin", admin_menu))
    application.add_handler(CommandHandler("stopmedia", stop_media))
    application.add_handler(CommandHandler("allowmedia", allow_media))
    
    application.add_handler(CommandHandler("character", switch_character))
    application.add_handler(CommandHandler("switch", switch_character)) 

    application.add_handler(CallbackQueryHandler(button_handler))
    
    application.add_handler(MessageHandler(
        filters.User(ADMIN_TELEGRAM_ID) & ~filters.COMMAND, 
        get_media_id
    ))
    
    # HANDLERS FOR PHOTO AND VOICE
    application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST & (filters.PHOTO), channel_message_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_message))

    logger.info(f"Starting webhook on port {PORT}")
    application.run_webhook(listen="0.0.0.0", port=PORT, url_path=TOKEN, webhook_url=f"{WEBHOOK_URL}/{TOKEN}")

if __name__ == '__main__':
    main()
