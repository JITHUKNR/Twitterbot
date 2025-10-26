import os
import logging
import random
import tweepy  # ട്വിറ്റർ ലൈബ്രറി
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ലോഗിംഗ് എനേബിൾ ചെയ്യുന്നു
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 6 Environment Variables-ഉം ലോഡ് ചെയ്യുന്നു ---
TOKEN = os.environ.get('TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
PORT = int(os.environ.get('PORT', 8443))

# ട്വിറ്റർ കീകൾ
API_KEY = os.environ.get('TWITTER_API_KEY')
API_SECRET = os.environ.get('TWITTER_API_SECRET')
ACCESS_TOKEN = os.environ.get('TWITTER_ACCESS_TOKEN')
ACCESS_TOKEN_SECRET = os.environ.get('TWITTER_ACCESS_TOKEN_SECRET')

# --- ട്വിറ്റർ API-യുമായി ബന്ധിപ്പിക്കുന്നു ---
def setup_twitter_client():
    try:
        client = tweepy.Client(
            consumer_key=API_KEY,
            consumer_secret=API_SECRET,
            access_token=ACCESS_TOKEN,
            access_token_secret=ACCESS_TOKEN_SECRET
        )
        logger.info("ട്വിറ്റർ ക്ലയന്റ് വിജയകരമായി സെറ്റപ്പ് ചെയ്തു")
        return client
    except Exception as e:
        logger.error(f"ട്വിറ്റർ ക്ലയന്റ് സെറ്റപ്പ് പരാജയപ്പെട്ടു: {e}")
        return None

# /start കമാൻഡിന് മറുപടി
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.message.from_user.first_name
    await update.message.reply_text(f'ഹലോ {user_name}! ട്വിറ്ററിൽ നിന്നും ഒരു റാൻഡം ഫോട്ടോ കിട്ടാൻ "സെൻറ്" എന്ന് ടൈപ്പ് ചെയ്യൂ.')

# "സെൻറ്" എന്ന് അയക്കുമ്പോൾ പ്രവർത്തിക്കുന്ന ഫംഗ്ഷൻ
async def send_random_tweet_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ട്വിറ്ററിൽ നിന്നും ഫോട്ടോ തിരയുന്നു... ദയവായി കാത്തിരിക്കുക...")
    
    try:
        client = setup_twitter_client()
        if not client:
            await update.message.reply_text("ക്ഷമിക്കണം, ട്വിറ്റർ API-യുമായി ബന്ധിപ്പിക്കാൻ സാധിക്കുന്നില്ല.")
            return

        # നിങ്ങളുടെ സ്വന്തം യൂസർ ID ട്വിറ്ററിൽ നിന്നും എടുക്കുന്നു
        me = client.get_me(user_auth=True)
        user_id = me.data.id
        
        # നിങ്ങളുടെ ട്വീറ്റുകൾ എടുക്കുന്നു (മീഡിയ ഉള്ളവ മാത്രം)
        response = client.get_users_tweets(
            id=user_id,
            expansions=["attachments.media_keys"],
            media_fields=["url", "type"],
            max_results=20  # അവസാന 20 ട്വീറ്റുകൾ പരിശോധിക്കുന്നു
        )
        
        photo_urls = []
        if response.includes and 'media' in response.includes:
            for media in response.includes['media']:
                if media.type == 'photo':
                    # media.url-ൽ ഫോട്ടോയുടെ URL ഉണ്ടാകും
                    photo_urls.append(media.url)

        if not photo_urls:
            await update.message.reply_text("ക്ഷമിക്കണം, നിങ്ങളുടെ അവസാന 20 ട്വീറ്റുകളിൽ ഫോട്ടോകൾ ഒന്നും കണ്ടെത്താനായില്ല.")
            return

        # കിട്ടിയ ഫോട്ടോകളിൽ നിന്നും ഒരെണ്ണം റാൻഡം ആയി തിരഞ്ഞെടുക്കുന്നു
        random_photo_url = random.choice(photo_urls)
        
        # ആ ഫോട്ടോ ടെലിഗ്രാമിലേക്ക് അയക്കുന്നു
        await update.message.reply_photo(photo=random_photo_url, caption="ട്വിറ്ററിൽ നിന്നുള്ള നിങ്ങളുടെ റാൻഡം ഫോട്ടോ!")

    except Exception as e:
        logger.error(f"ട്വീറ്റ് തിരയുന്നതിൽ പരാജയപ്പെട്ടു: {e}")
        await update.message.reply_text("ക്ഷമിക്കണം, എന്തോ ഒരു എറർ സംഭവിച്ചു.")


def main():
    if not TOKEN or not WEBHOOK_URL:
        logger.error("Error: Telegram-ന്റെ Environment Variables സെറ്റ് ചെയ്തിട്ടില്ല.")
        return
    if not API_KEY or not ACCESS_TOKEN:
         logger.error("Error: Twitter-ന്റെ Environment Variables സെറ്റ് ചെയ്തിട്ടില്ല.")
         return

    # ബോട്ട് ആപ്ലിക്കേഷൻ സ്റ്റാർട്ട് ചെയ്യുന്നു
    application = Application.builder().token(TOKEN).build()

    # ഹാൻഡ്ലറുകൾ ചേർക്കുന്നു
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex(r'^സെൻറ്$'), send_random_tweet_media))

    # Webhook സെറ്റ് ചെയ്യുന്നു
    logger.info(f"പോർട്ട് {PORT}-ൽ Webhook സ്റ്റാർട്ട് ചെയ്യുന്നു")
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN, 
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
    )

if __name__ == '__main__':
    main()
    
