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
TWITTER_USERNAME = "abhiixz" # <-- നിങ്ങളുടെ യൂസർനെയിം മാറ്റാൻ മറക്കരുത്!

# --- 2. Clients സജ്ജീകരിക്കുന്നു ---
bot = Bot(token=BOT_TOKEN)
app = Flask(__name__)

# Tweepy (X API) Client Initialization
auth = tweepy.OAuthHandler(TWITTER_API_KEY, TWITTER_API_SECRET)
auth.set_access_token(TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET)
twitter_client = None # Global variable
try:
    twitter_client = tweepy.API(auth)
    logging.info("Twitter API client initialized successfully.")
except Exception as e:
    logging.error(f"Error initializing Twitter API: {e}")

# --- 3. Twitter മീഡിയ ഫയലുകൾ എടുക്കാനുള്ള ഫംഗ്ഷൻ ---

def get_random_media(username):
    if not twitter_client:
        return None, "Error: Twitter API Client is not available."
    
    try:
        # ഒരു യൂസറുടെ 200 പോസ്റ്റുകൾ വരെ എടുക്കാൻ ശ്രമിക്കുന്നു
        tweets = twitter_client.user_timeline(screen_name=username, count=200, include_rts=False, exclude_replies=True)
        
        media_items = []
        for tweet in tweets:
            if hasattr(tweet, 'extended_entities') and 'media' in tweet.extended_entities:
                for media in tweet.extended_entities['media']:
                    # ഫോട്ടോ ആണെങ്കിൽ (type='photo')
                    if media.get('type') == 'photo':
                        media_items.append({'type': 'photo', 'url': media['media_url_https']})
                    # വീഡിയോ/GIF ആണെങ്കിൽ
                    elif media.get('type') in ('video', 'animated_gif'):
                        # ഏറ്റവും നല്ല ക്വാളിറ്റി ഉള്ള വീഡിയോ URL എടുക്കുന്നു
                        # [0] പകരം [-1] ഉപയോഗിച്ച് ഏറ്റവും ഉയർന്ന ബിറ്റ്റേറ്റ് എടുക്കാൻ ശ്രമിക്കുന്നു.
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

def send_media(chat_id, media_item):
    media_type = media_item['type']
    url = media_item['url']
    
    try:
        # URL ഉപയോഗിച്ച് ഫയൽ ഡൗൺലോഡ് ചെയ്ത് മെമ്മറിയിൽ സൂക്ഷിക്കുന്നു
        file_response = requests.get(url, stream=True)
        file_response.raise_for_status()
        
        # ഫയൽ അയക്കുന്നു
        if media_type == 'photo':
            bot.send_photo(chat_id=chat_id, photo=file_response.content)
        elif media_type in ('video', 'animated_gif'):
            bot.send_video(chat_id=chat_id, video=file_response.content, supports_streaming=True)
        
        return True, "Media sent successfully."
    
    except requests.exceptions.RequestException as e:
        logging.error(f"Error downloading media file: {e}")
        return False, f"Error downloading media file: {e}"
    except TelegramError as e:
        # Telegram File Size Limit പോലുള്ള പിശകുകൾ ഇവിടെ വരും
        logging.error(f"Telegram Send Error: {e}")
        return False, f"Telegram Error: Could not send media (Too large or unsupported format)."
    except Exception as e:
        logging.error(f"An unknown error occurred during media sending: {e}")
        return False, f"An unknown error occurred: {e}"

# --- 5. Webhook Route ---

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        
        if "message" in update and "text" in update["message"]:
            text = update["message"]["text"].lower().strip()
            chat_id = update["message"]["chat"]["id"]
            
            # ഉപയോക്താവ് 'send' എന്ന് അയച്ചാൽ
            if text == "send":
                bot.send_message(chat_id=chat_id, text="Searching your X account for a random media... 🔄")
                
                media_item, error = get_random_media(TWITTER_USERNAME)
                
                if error:
                    bot.send_message(chat_id=chat_id, text=f"ERROR: {error}")
                elif media_item:
                    success, send_error = send_media(chat_id, media_item)
                    if not success:
                        bot.send_message(chat_id=chat_id, text=f"FINAL SEND ERROR: {send_error}")
            
            # മറ്റെന്തെങ്കിലും മെസ്സേജ് വന്നാൽ
            elif text == "/start":
                 bot.send_message(chat_id=chat_id, text="Welcome! To get a random photo or video from my linked X account, please type 'send'.")

    except Exception as e:
        print(f"An unhandled error occurred in webhook: {e}") # അവസാനത്തെ സുരക്ഷ
    
    return "ok", 200

# --- 6. App സ്റ്റാർട്ട് ചെയ്യുന്നു ---

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
