import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ലോഗിംഗ് എനേബിൾ ചെയ്യുന്നു
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Render നൽകുന്ന Environment Variables
TOKEN = os.environ.get('TOKEN')
# Render-ലെ നിങ്ങളുടെ ആപ്പിന്റെ URL (ഇത് നമ്മൾ അടുത്ത ഘട്ടത്തിൽ സെറ്റ് ചെയ്യും)
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
# Render ഓട്ടോമാറ്റിക്കായി നൽകുന്ന പോർട്ട് നമ്പർ
PORT = int(os.environ.get('PORT', 8443))

# /start കമാൻഡിന് മറുപടി നൽകുന്ന ഫംഗ്ഷൻ (പഴയതുപോലെ)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.message.from_user.first_name
    await update.message.reply_text(f'ഹലോ {user_name}! എന്നോട് എന്തെങ്കിലും പറയൂ...')

# മെസ്സേജുകൾക്ക് മറുപടി (echo) നൽകുന്ന ഫംഗ്ഷൻ (പഴയതുപോലെ)
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await update.message.reply_text(f'നിങ്ങൾ പറഞ്ഞത്: "{user_text}"')

def main():
    if not TOKEN:
        logger.error("Error: 'TOKEN' Environment Variable സെറ്റ് ചെയ്തിട്ടില്ല.")
        return
    if not WEBHOOK_URL:
        logger.error("Error: 'WEBHOOK_URL' Environment Variable സെറ്റ് ചെയ്തിട്ടില്ല.")
        return

    # ബോട്ട് ആപ്ലിക്കേഷൻ സ്റ്റാർട്ട് ചെയ്യുന്നു
    application = Application.builder().token(TOKEN).build()

    # ഹാൻഡ്ലറുകൾ ചേർക്കുന്നു
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Webhook സെറ്റ് ചെയ്യുന്നു
    # ഈ ഫംഗ്ഷൻ ടെലിഗ്രാമിനോട് നമ്മുടെ URL അറിയിക്കുകയും 
    # Render-ന് ആവശ്യമായ പോർട്ടിൽ വെബ് സെർവർ സ്റ്റാർട്ട് ചെയ്യുകയും ചെയ്യും
    logger.info(f"പോർട്ട് {PORT}-ൽ Webhook സ്റ്റാർട്ട് ചെയ്യുന്നു")
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,  # URL-ന്റെ അവസാന ഭാഗം (സുരക്ഷയ്ക്കായി ടോക്കൺ തന്നെ ഉപയോഗിക്കുന്നു)
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}" # ടെലിഗ്രാം മെസ്സേജ് അയക്കേണ്ട ഫുൾ URL
    )

if __name__ == '__main__':
    main()
