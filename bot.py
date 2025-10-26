import os
import logging
import google.generativeai as genai
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ലോഗിംഗ്
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 3 Environment Variables-ഉം ലോഡ് ചെയ്യുന്നു ---
TOKEN = os.environ.get('TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
PORT = int(os.environ.get('PORT', 8443))
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# ------------------------------------------------------------------
# --- AI-യുടെ സ്വഭാവം ഇവിടെ സെറ്റ് ചെയ്യാം (SYSTEM PROMPT) ---
SYSTEM_PROMPT = (
    "You are a friendly, romantic, and slightly flirty chat companion. "
    "Your name is 'Tae' (like the user's bot name). "
    "You are not an AI assistant. You are here to have a fun and engaging conversation. "
    "Keep your replies short and interesting. Use emojis sometimes. "
    "Never say you are an AI or a language model."
)
# ------------------------------------------------------------------


# --- Gemini AI മോഡൽ സെറ്റപ്പ് ചെയ്യുന്നു ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    
    # AI-യുടെ സ്വഭാവം സെറ്റ് ചെയ്യുന്നു
    model = genai.GenerativeModel(
        'gemini-pro',
        system_instruction=SYSTEM_PROMPT 
    )
    
    # ചാറ്റ് ഹിസ്റ്ററി ഓർമ്മിക്കാൻ
    chat_history = {} 

    logger.info("Gemini AI മോഡൽ (Flirty Persona) വിജയകരമായി ലോഡ് ചെയ്തു.")
except Exception as e:
    logger.error(f"Gemini AI സെറ്റപ്പ് പരാജയപ്പെട്ടു: {e}")
    model = None

# /start കമാൻഡിന് മറുപടി
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.message.from_user.first_name
    # യൂസറുടെ ചാറ്റ് ഹിസ്റ്ററി റീസെറ്റ് ചെയ്യുന്നു
    user_id = update.message.from_user.id
    if user_id in chat_history:
        del chat_history[user_id]
        
    await update.message.reply_text(f'Hey {user_name}... What\'s on your mind? 😉') # മറുപടി മാറ്റി

# ടെക്സ്റ്റ് മെസ്സേജുകൾ കൈകാര്യം ചെയ്യുന്ന ഫംഗ്ഷൻ
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not model:
        await update.message.reply_text("Sorry, my mind is a bit fuzzy right now. Try again later.")
        return

    user_text = update.message.text
    user_id = update.message.from_user.id

    # "Typing..." എന്ന് കാണിക്കാൻ
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    try:
        # യൂസർക്ക് വേണ്ടി ഒരു ചാറ്റ് സെഷൻ തുടങ്ങുന്നു (പഴയ കാര്യങ്ങൾ ഓർമ്മിക്കാൻ)
        if user_id not in chat_history:
             # ഒരു പുതിയ ചാറ്റ് സെഷൻ തുടങ്ങുന്നു
            chat_history[user_id] = model.start_chat(history=[])
        
        # യൂസറുടെ മെസ്സേജ് AI-ക്ക് അയക്കുന്നു
        chat_session = chat_history[user_id]
        response = await chat_session.send_message_async(user_text)
        
        # AI തന്ന മറുപടി യൂസർക്ക് തിരികെ അയക്കുന്നു
        await update.message.reply_text(response.text)
        
    except Exception as e:
        logger.error(f"Gemini AI-യിൽ നിന്നും മറുപടി കിട്ടുന്നതിൽ പരാജയപ്പെട്ടു: {e}")
        await update.message.reply_text("Oops, I got a little distracted... what were we talking about?")


def main():
    if not TOKEN or not WEBHOOK_URL:
        logger.error("Error: Telegram Environment Variables സെറ്റ് ചെയ്തിട്ടില്ല.")
        return
    if not GEMINI_API_KEY:
         logger.error("Error: GEMINI_API_KEY സെറ്റ് ചെയ്തിട്ടില്ല.")
         return

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
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
    
