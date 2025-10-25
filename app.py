import os
import random
import requests
import tweepy
from flask import Flask, request
from telegram import Bot
from telegram.error import TelegramError

# --- 1. Environment Variables എടുക്കുന്നു ---
# Render-ൽ സെറ്റ് ചെയ്ത കീകൾ ഇവിടെ ഉപയോഗിക്കുന്നു
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Twitter API (X) Credentials
TWITTER_API_KEY = os.environ.get("TWITTER_API_KEY")
TWITTER_API_SECRET = os.environ.get("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.environ.get("TWITTER_ACCESS_SECRET")
# നിങ്ങൾ മീഡിയ എടുക്കാൻ ഉദ്ദേശിക്കുന്ന X അക്കൗണ്ടിന്റെ യൂസർനെയിം (ഉദാഹരണത്തിന്: 'NASA')
TWITTER_USERNAME = "abhiixz" 

# --- 2. Clients സജ്ജീകരിക്കുന്നു ---
bot = Bot(token=BOT_TOKEN)
app = Flask(__name__)

# Tweepy (X API) ക്ലയിന്റ്
auth = tweepy.OAuthHandler(TWITTER_API_KEY, TWITTER_API_SECRET)
auth.set_access_token(TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET)
try:
    twitter_client = tweepy.API(auth)
    print("Twitter API client initialized successfully.")
except Exception as e:
    print(f"Error initializing Twitter API: {e}")
    twitter_client = None

# --- 3. Twitter മീഡിയ ഫയലുകൾ എടുക്കാനുള്ള ഫംഗ്ഷൻ ---

def get_random_media(username):
    if not twitter_client:
        return None, "Error: Twitter API Client not initialized."
    
    try:
        # ഒരു യൂസറുടെ 500 പോസ്റ്റുകൾ വരെ എടുക്കാൻ ശ്രമിക്കുന്നു
        tweets = twitter_client.user_timeline(screen_name=username, count=500, include_rts=False, exclude_replies=True)
        
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
                        video_url = media['video_info']['variants'][-1]['url']
                        media_items.append({'type': 'video', 'url': video_url})
        
        if not media_items:
            return None, f"No media found in the last 500 posts of @{username}."
        
        # കണ്ടെത്തിയ മീഡിയകളിൽ നിന്ന് ഒരെണ്ണം റാൻഡമായി തിരഞ്ഞെടുക്കുന്നു
        return random.choice(media_items), None
    
    print(f"CRITICAL TWITTER ERROR DETAILS: {e}")
        return None, f"Twitter API Error: {e}"
    except Exception as e:
        return None, f"An unexpected error occurred: {e}"

# --- 4. ടെലിഗ്രാമിലേക്ക് മീഡിയ അയക്കാനുള്ള ഫംഗ്ഷൻ ---

def send_media(chat_id, media_item):
    media_type = media_item['type']
    url = media_item['url']
    
    try:
        # URL ഉപയോഗിച്ച് ഫയൽ ഡൗൺലോഡ് ചെയ്ത് മെമ്മറിയിൽ സൂക്ഷിക്കുന്നു
        file_response = requests.get(url, stream=True)
        file_response.raise_for_status() # Bad status code ആണെങ്കിൽ exception throw ചെയ്യും
        
        # ഫയൽ അയക്കുന്നു
        if media_type == 'photo':
            bot.send_photo(chat_id=chat_id, photo=file_response.content)
        elif media_type in ('video', 'animated_gif'):
            # വീഡിയോ അല്ലെങ്കിൽ GIF അയക്കുന്നു. (Telegram API-യിൽ Video അയക്കാൻ send_video ഉപയോഗിക്കുന്നു)
            bot.send_video(chat_id=chat_id, video=file_response.content, supports_streaming=True)
        
        return True, "Media sent successfully."
    
    except requests.exceptions.RequestException as e:
        return False, f"Error downloading media file: {e}"
    except TelegramError as e:
        return False, f"Telegram Error: {e}"
    except Exception as e:
        return False, f"An error occurred: {e}"

# --- 5. Webhook Route ---

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        
        # മെസ്സേജ് ടെക്സ്റ്റ് ആണോ എന്ന് പരിശോധിക്കുന്നു
        if "message" in update and "text" in update["message"]:
            text = update["message"]["text"].lower().strip()
            chat_id = update["message"]["chat"]["id"]
            
            # ഉപയോക്താവ് 'send' എന്ന് അയച്ചാൽ
            if text == "send":
                bot.send_message(chat_id=chat_id, text="Searching your X account for a random media... 🔄")
                
                # റാൻഡം മീഡിയ എടുക്കുന്നു
                media_item, error = get_random_media(TWITTER_USERNAME)
                
                if error:
                    bot.send_message(chat_id=chat_id, text=f"Error: Could not fetch media from X. Details: {error}")
                elif media_item:
                    # മീഡിയ അയക്കുന്നു
                    success, send_error = send_media(chat_id, media_item)
                    if not success:
                        bot.send_message(chat_id=chat_id, text=f"Error sending media to Telegram: {send_error}")
            
            # മറ്റെന്തെങ്കിലും മെസ്സേജ് വന്നാൽ
            elif text == "/start":
                 bot.send_message(chat_id=chat_id, text="Welcome! To get a random photo or video from my linked X account, please type 'send'.")

    except Exception as e:
        # ലോഗിങ്ങിനായി ഉപയോഗിക്കാം
        print(f"An error occurred during webhook processing: {e}")
    
    return "ok", 200 # Telegram-ന് വിജയകരമായ മറുപടി നൽകുന്നു

# --- 6. App സ്റ്റാർട്ട് ചെയ്യുന്നു ---

if __name__ == '__main__':
    # Render പോർട്ട് എടുക്കുന്നു, അല്ലെങ്കിൽ ലോക്കൽ ടെസ്റ്റിങ്ങിനായി 5000 ഉപയോഗിക്കുന്നു
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
