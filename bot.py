import os
import logging
import random
import tweepy
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Load all 6 Environment Variables ---
TOKEN = os.environ.get('TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
PORT = int(os.environ.get('PORT', 8443))

# Twitter Keys
API_KEY = os.environ.get('TWITTER_API_KEY')
API_SECRET = os.environ.get('TWITTER_API_SECRET')
ACCESS_TOKEN = os.environ.get('TWITTER_ACCESS_TOKEN')
ACCESS_TOKEN_SECRET = os.environ.get('TWITTER_ACCESS_TOKEN_SECRET')

# --- Connect to Twitter API ---
def setup_twitter_client():
    try:
        client = tweepy.Client(
            consumer_key=API_KEY,
            consumer_secret=API_SECRET,
            access_token=ACCESS_TOKEN,
            access_token_secret=ACCESS_TOKEN_SECRET
        )
        logger.info("Twitter client setup successfully")
        return client
    except Exception as e:
        logger.error(f"Failed to setup Twitter client: {e}")
        return None

# Responds to /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.message.from_user.first_name
    await update.message.reply_text(f'Hello {user_name}! Type "send" to get a random photo from Twitter.')

# Function that runs when "send" is typed
async def send_random_tweet_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Searching Twitter for a photo... please wait...")
    
    try:
        client = setup_twitter_client()
        if not client:
            await update.message.reply_text("Sorry, I couldn't connect to the Twitter API.")
            return

        # Get your own user ID from Twitter
        me = client.get_me(user_auth=True)
        user_id = me.data.id
        
        # Get your tweets (only those with media)
        response = client.get_users_tweets(
            id=user_id,
            expansions=["attachments.media_keys"],
            media_fields=["url", "type"],
            max_results=20  # Checks the last 20 tweets
        )
        
        photo_urls = []
        if response.includes and 'media' in response.includes:
            for media in response.includes['media']:
                if media.type == 'photo':
                    # media.url contains the URL of the photo
                    photo_urls.append(media.url)

        if not photo_urls:
            await update.message.reply_text("Sorry, I couldn't find any photos in your last 20 tweets.")
            return

        # Choose a random photo from the list
        random_photo_url = random.choice(photo_urls)
        
        # Send that photo to Telegram
        await update.message.reply_photo(photo=random_photo_url, caption="Here is your random photo from Twitter!")

    except Exception as e:
        logger.error(f"Failed to search tweets: {e}")
        await update.message.reply_text("Sorry, something went wrong.")


def main():
    if not TOKEN or not WEBHOOK_URL:
        logger.error("Error: Telegram Environment Variables are not set.")
        return
    if not API_KEY or not ACCESS_TOKEN:
         logger.error("Error: Twitter Environment Variables are not set.")
         return

    # Start the bot application
    application = Application.builder().token(TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    
    # This handler now triggers on 'send' or 'Send' (case-insensitive)
    application.add_handler(MessageHandler(filters.Regex(r'(?i)^send$'), send_random_tweet_media))

    # Set up the Webhook
    logger.info(f"Starting webhook on port {PORT}")
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN, 
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
    )

if __name__ == '__main__':
    main()
        
