import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pymongo import MongoClient
from groq import Groq

# -----------------
# 1. API കീകൾ സജ്ജമാക്കുക (API Keys Setup)
# -----------------
# ഈ വേരിയബിളുകൾ Render എൻവയോൺമെൻ്റ് വേരിയബിളിൽ സജ്ജമാക്കണം (Render Environment Variables)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
MONGO_URI = os.environ.get("MONGO_URI") # DATABASE_URL ന് പകരം MONGO_URI ഉപയോഗിക്കുക
ADMIN_USER_ID = int(os.environ.get("ADMIN_USER_ID"))

# -----------------
# 2. ലോഗിംഗ് കോൺഫിഗറേഷൻ (Logging Configuration)
# -----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# -----------------
# 3. ഡാറ്റാബേസ് കണക്ഷനും AI ക്ലൈൻ്റുകളും (DB Connection & AI Clients)
# -----------------
groq_client = Groq(api_key=GROQ_API_KEY)
mongo_client = None
db = None
conversations_collection = None
users_collection = None

def establish_db_connection():
    """MongoDB കണക്ഷൻ സ്ഥാപിക്കുന്നു."""
    global mongo_client, db, conversations_collection, users_collection
    try:
        if MONGO_URI:
            mongo_client = MongoClient(MONGO_URI)
            db = mongo_client.get_database("telegram_bot_db")
            conversations_collection = db.get_collection("conversations")
            users_collection = db.get_collection("users")
            logger.info("Successfully connected to MongoDB.")
        else:
            logger.error("MONGO_URI is not set. Database connection failed.")
    except Exception as e:
        logger.error(f"MongoDB connection error: {e}")

# -----------------
# 4. യൂട്ടിലിറ്റി ഫംഗ്ഷനുകൾ (Utility Functions)
# -----------------
def get_user_data(user_id):
    """ഒരു യൂസറിൻ്റെ നിലവിലെ ഡാറ്റാബേസ് സ്റ്റേറ്റ് എടുക്കുന്നു."""
    if users_collection:
        return users_collection.find_one({"user_id": user_id})
    return {"chat_history": []}

def update_user_data(user_id, data):
    """യൂസറിൻ്റെ ഡാറ്റാബേസ് സ്റ്റേറ്റ് അപ്ഡേറ്റ് ചെയ്യുന്നു."""
    if users_collection:
        users_collection.update_one(
            {"user_id": user_id}, {"$set": data}, upsert=True
        )

def get_conversation_history(user_id):
    """ചാറ്റ് ഹിസ്റ്ററി ഡാറ്റാബേസിൽ നിന്ന് എടുക്കുന്നു."""
    if conversations_collection:
        conversation_data = conversations_collection.find_one({"user_id": user_id})
        return conversation_data.get("chat_history", []) if conversation_data else []
    return []

def save_conversation_history(user_id, chat_history):
    """ചാറ്റ് ഹിസ്റ്ററി ഡാറ്റാബേസിൽ സേവ് ചെയ്യുന്നു."""
    if conversations_collection:
        conversations_collection.update_one(
            {"user_id": user_id}, {"$set": {"chat_history": chat_history}}, upsert=True
        )

def get_allowed_status(user_id):
    """ഒരു യൂസർക്ക് മീഡിയാ ഫയലുകൾ അയക്കാൻ അനുവാദമുണ്ടോ എന്ന് പരിശോധിക്കുന്നു."""
    user_data = users_collection.find_one({"user_id": user_id})
    return user_data.get("allow_media", True) if user_data else True

# -----------------
# 5. കമാൻഡ് ഹാൻഡ്ലറുകൾ (Command Handlers)
# -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start കമാൻഡിനുള്ള പ്രതികരണം."""
    user_id = update.effective_user.id
    update_user_data(user_id, {"user_id": user_id, "allow_media": True, "is_admin": user_id == ADMIN_USER_ID})
    
    await update.message.reply_text(
        "👋 നമസ്കാരം! ഞാൻ നിങ്ങളുടെ AI അസിസ്റ്റൻ്റ് ആണ്. നിങ്ങൾക്ക് എന്നോട് സംസാരിക്കാം.\n\n"
        "പുതിയ സംഭാഷണം തുടങ്ങാൻ /new ഉപയോഗിക്കുക.\n"
        "മീഡിയാ ഫയലുകൾ അയക്കുന്നത് നിർത്താൻ /stopmedia ഉപയോഗിക്കുക."
    )

async def new_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/new കമാൻഡ് - പുതിയ സംഭാഷണം തുടങ്ങുന്നു."""
    user_id = update.effective_user.id
    save_conversation_history(user_id, [])
    await update.message.reply_text("✅ പുതിയ സംഭാഷണം ആരംഭിച്ചിരിക്കുന്നു. നിങ്ങൾക്കിപ്പോൾ ചോദ്യങ്ങൾ ചോദിക്കാം.")

async def clear_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/clearmedia കമാൻഡ് - മീഡിയാ ഫയലുകൾ അയക്കുന്നതിനുള്ള അനുവാദം മാറ്റുന്നു."""
    user_id = update.effective_user.id
    update_user_data(user_id, {"allow_media": True}) # ഇത് ഡാറ്റാബേസ് പ്രശ്നം പരിഹരിക്കാൻ വേണ്ടി വീണ്ടും True ആക്കുന്നു
    await update.message.reply_text("🚫 മീഡിയാ ഫയലുകൾ അയക്കുന്നത് താൽക്കാലികമായി നിർത്തിവെച്ചിരിക്കുന്നു. ചാറ്റ് തുടരാം.")

async def stop_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/stopmedia കമാൻഡ് - മീഡിയാ ഫയലുകൾ അയക്കുന്നത് നിർത്തുന്നു."""
    user_id = update.effective_user.id
    update_user_data(user_id, {"allow_media": False})
    await update.message.reply_text("🚫 മീഡിയാ ഫയലുകൾ അയക്കുന്നത് നിർത്തിയിരിക്കുന്നു. ഇനി മുതൽ AI ചാറ്റ് മാത്രമേ ലഭ്യമാകൂ.")

async def allow_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/allowmedia കമാൻഡ് - മീഡിയാ ഫയലുകൾ അയക്കുന്നത് പുനരാരംഭിക്കുന്നു."""
    user_id = update.effective_user.id
    update_user_data(user_id, {"allow_media": True})
    await update.message.reply_text("✅ മീഡിയാ ഫയലുകൾ അയക്കുന്നത് പുനരാരംഭിച്ചിരിക്കുന്നു.")

# -----------------
# 6. മെസ്സേജ് ഹാൻഡ്ലർ (Message Handler - AI Chat Logic)
# -----------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ടെക്സ്റ്റ് മെസ്സേജുകൾ സ്വീകരിച്ച് AI പ്രതികരണം നൽകുന്നു."""
    user_id = update.effective_user.id
    
    # യൂസർ മീഡിയാ ഫയലുകൾ അയക്കുന്നത് നിർത്തിയിട്ടുണ്ടോ എന്ന് പരിശോധിക്കുന്നു
    if not get_allowed_status(user_id) and update.message.media_group_id:
        await update.message.reply_text(
            "നിങ്ങൾ ഇപ്പോൾ മീഡിയാ ഫയലുകൾ അയക്കുന്നത് നിർത്തിവെച്ചിരിക്കുകയാണ് (/stopmedia). മീഡിയാ ഫയലുകൾ അയക്കാൻ അനുവാദം നൽകാൻ /allowmedia ഉപയോഗിക്കുക."
        )
        return

    # ചാറ്റ് ഹിസ്റ്ററി എടുക്കുന്നു
    chat_history = get_conversation_history(user_id)
    
    # പുതിയ യൂസർ മെസ്സേജ് ചേർക്കുന്നു
    user_message = {"role": "user", "content": update.message.text}
    chat_history.append(user_message)

    # Groq API കോൾ ചെയ്യുന്നു
    try:
        response = groq_client.chat.completions.create(
            messages=chat_history,
            model="llama3-8b-8192", # അല്ലെങ്കിൽ നിങ്ങൾ തിരഞ്ഞെടുക്കുന്ന മോഡൽ
            temperature=0.7,
        )
        ai_response = response.choices[0].message.content
        
        # AI പ്രതികരണം ചാറ്റ് ഹിസ്റ്ററിയിൽ ചേർക്കുന്നു
        ai_message = {"role": "assistant", "content": ai_response}
        chat_history.append(ai_message)

        # ഡാറ്റാബേസിൽ ഹിസ്റ്ററി സേവ് ചെയ്യുന്നു
        save_conversation_history(user_id, chat_history)

        # യൂസർക്ക് മറുപടി നൽകുന്നു
        await update.message.reply_text(ai_response)
        
    except Exception as e:
        logger.error(f"Groq API Error: {e}")
        await update.message.reply_text("ക്ഷമിക്കണം, AI പ്രതികരണം നൽകുന്നതിൽ ഒരു പിഴവ് സംഭവിച്ചു.")
        
# -----------------
# 7. മെയിൻ ഫംഗ്ഷൻ (Main Function)
# -----------------
def main() -> None:
    """ബോട്ടിനെ പ്രവർത്തിപ്പിക്കാൻ തുടങ്ങുന്നു."""
    establish_db_connection()
    
    application = Application.builder().token(BOT_TOKEN).build()

    # കമാൻഡ് ഹാൻഡ്ലറുകൾ
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("new", new_conversation))
    application.add_handler(CommandHandler("clearmedia", clear_media))
    application.add_handler(CommandHandler("stopmedia", stop_media))
    application.add_handler(CommandHandler("allowmedia", allow_media))

    # മെസ്സേജ് ഹാൻഡ്ലർ
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    # ബോട്ട് തുടങ്ങുന്നു
    application.run_polling(read_timeout=35)

if __name__ == "__main__":
    main()
