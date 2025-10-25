import os
import random
import requests
import logging
from flask import Flask, request
from telegram import Bot
from telegram.error import TelegramError
import tweepy
from tweepy import TweepyException

# --- ലോഗിംഗ് സജ്ജീകരിക്കുന്നു ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

# --- 1. Environment Variables എടുക്കുന്നു ---
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Twitter API (X) Credentials
TWITTER_API_KEY = os.environ.get("TWITTER_API_KEY")
TWITTER_API_SECRET = os.environ.get("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.environ.get("TWITTER_ACCESS_SECRET")
TWITTER_USERNAME = "abhiixz" # <-- ശ്രദ്ധിക്കുക: ഇത് നിങ്ങളുടെ യൂസർനെയിം ആണ്.

# --- 2. Clients സജ്ജീകരിക്കുന്നു ---
bot = Bot(token=BOT_TOKEN)
app = Flask(__name__)

# Tweepy (X API) Client Initialization
auth = tweepy.OAuthHandler(TWITTER_API_KEY, TWITTER_API_SECRET)
auth.set_access_token(TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET)
twitter_client = None 

try:
    twitter_client = tweepy.API(auth)
    # പുതിയ ഘട്ടം: API കീ ശരിയാണോ എന്ന് Bot തുടങ്ങുമ്പോൾ തന്നെ പരിശോധിക്കുന്നു.
    twitter_client.verify_credentials() 
    logging.info("Twitter API client initialized successfully and credentials verified.")
except Exception as e:
    # API കീകളിൽ പിശകുണ്ടെങ്കിൽ ഈ ERROR സന്ദേശം Log-ൽ കാണിക്കും.
    logging.error(f"CRITICAL API KEY ERROR ON STARTUP (Check Keys): {e}")

# --- 3. Twitter മീഡിയ ഫയലുകൾ എടുക്കാനുള്ള ഫംഗ്ഷൻ ---

def get_random_media(username):
    # ... (ഈ ഭാഗത്ത് മാറ്റങ്ങൾ ഇല്ല)
    if not twitter_client:
        return None, "Error: Twitter API Client is not available."
    
    try:
        tweets = twitter_client.user_timeline(screen_name=username, count=200, include_rts=False, exclude_replies=True)
        
        media_items = []
        for tweet in tweets:
            if hasattr(tweet, 'extended_entities') and 'media' in tweet.extended_entities:
                for media in tweet.extended_entities['media']:
                    if media.get('type') == 'photo':
                        media_items.append({'type': 'photo', 'url': media['media_url_https']})
                    elif media.get('type') in ('video', 'animated_gif'):
                        video_url = media['video_info']['variants'][-1]['url'] 
                        media_items.append({'type': 'video', 'url': video_url})
        
        if not media_items:
            return None, f"No media found in the last 200 posts of @{username} or account is protected."
        
        logging.info(f"Found {len(media_items)} media items. Selecting one randomly.")
        return random.choice(media_items), None
    
    except TweepyException as e:
        # ട്വിറ്റർ അനുമതി പിശക്
        logging.error(f"CRITICAL TWITTER ERROR DETAILS (Tweepy): {e}") 
        return None, f"Twitter API Authorization/Rate Limit Error: {e}"
    except Exception as e:
        # മറ്റ് അപ്രതീക്ഷിത പിശകുകൾ
        logging.error(f"CRITICAL UNEXPECTED ERROR: {e}")
        return None, f"An unexpected error occurred: {e}"

# --- 4. ടെലിഗ്രാമിലേക്ക് മീഡിയ അയക്കാനുള്ള ഫംഗ്ഷൻ ---
# ... (മാറ്റങ്ങൾ ഇല്ല)
def send_media(chat_id, media_item):
    media_type = media_item['type']
    url = media_item['url']
    
    try:
        file_response = requests.get(url, stream=True)
        file_response.raise_for_status()
        
        if media_type == 'photo':
            bot.send_photo(chat_id=chat_id, photo=file_response.content)
        elif media_type in ('video', 'animated_gif'):
            bot.send_video(chat_id=chat_id, video=file_response.content, supports_streaming=True)
        
        return True, "Media sent successfully."
    
    except requests.exceptions.RequestException as e:
        logging.error(f"Error downloading media file: {e}")
        return False, f"Error downloading media file: {e}"
    except TelegramError as e:
        logging.error(f"Telegram Send Error: {e}")
        return False, f"Telegram Error: Could not send media (Too large or unsupported format)."
    except Exception as e:
        logging.error(f"An unknown error occurred during media sending: {e}")
        return False, f"An unknown error occurred: {e}"

# --- 5. Webhook Route ---
# ... (മാറ്റങ്ങൾ ഇല്ല)
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        
        if "message" in update and "text" in update["message"]:
            text = update["message"]["text"].lower().strip()
            chat_id = update["message"]["chat"]["id"]
            
            if text == "send":
                bot.send_message(chat_id=chat_id, text="Searching your X account for a random media... 🔄")
                
                media_item, error = get_random_media(TWITTER_USERNAME)
                
                if error:
                    bot.send_message(chat_id=chat_id, text=f"ERROR: {error}")
                elif media_item:
                    success, send_error = send_media(chat_id, media_item)
                    if not success:
                        bot.send_message(chat_id=chat_id, text=f"FINAL SEND ERROR: {send_error}")
            
            elif text == "/start":
                 bot.send_message(chat_id=chat_id, text="Welcome! To get a random photo or video from my linked X account, please type 'send'.")

    except Exception as e:
        print(f"An unhandled error occurred in webhook: {e}") 
    
    return "ok", 200

# --- 6. App സ്റ്റാർട്ട് ചെയ്യുന്നു ---
# ... (മാറ്റങ്ങൾ ഇല്ല)
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
  
