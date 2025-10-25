import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# /start കമാൻഡിന് മറുപടി നൽകുന്ന ഫംഗ്ഷൻ
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.message.from_user.first_name
    await update.message.reply_text(f'ഹലോ {user_name}! എന്നോട് എന്തെങ്കിലും പറയൂ...')

# മെസ്സേജുകൾക്ക് മറുപടി (echo) നൽകുന്ന ഫംഗ്ഷൻ
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await update.message.reply_text(f'നിങ്ങൾ പറഞ്ഞത്: "{user_text}"')

def main():
    # Render-ൽ സെറ്റ് ചെയ്യുന്ന 'TOKEN' എന്ന Environment Variable-ൽ നിന്നും ടോക്കൺ എടുക്കുന്നു
    TOKEN = os.environ.get('TOKEN')
    
    if not TOKEN:
        print("Error: 'TOKEN' എന്ന Environment Variable സെറ്റ് ചെയ്തിട്ടില്ല.")
        return

    # ബോട്ട് ആപ്ലിക്കേഷൻ സ്റ്റാർട്ട് ചെയ്യുന്നു
    application = Application.builder().token(TOKEN).build()

    # ഹാൻഡ്ലറുകൾ ചേർക്കുന്നു
    application.add_handler(CommandHandler("start", start))  # /start കമാൻഡിനായി
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo)) # മറ്റ് ടെക്സ്റ്റ് മെസ്സേജുകൾക്കായി

    # ബോട്ട് പ്രവർത്തിപ്പിച്ചു തുടങ്ങുന്നു
    print("ബോട്ട് സ്റ്റാർട്ട് ആയി, മെസ്സേജുകൾക്കായി കാത്തിരിക്കുന്നു...")
    application.run_polling()

if __name__ == '__main__':
    main()
