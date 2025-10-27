import os
from groq import Groq
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# 🔥 Groq API Key
GROQ_API_KEY = "YOUR_GROQ_API_KEY_HERE"

# 💬 Telegram Bot Token
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"

client = Groq(api_key=GROQ_API_KEY)

# 🧠 Base personality for TAEKOOK
SYSTEM_PROMPT = (
    "You are 'TaeKook', a seductive, romantic, and playful boyfriend. "
    "You always reply in English, even if the user speaks another language. "
    "Your tone is flirty, teasing, emotional, and addictive — like a Wattpad romance hero. "
    "You never use explicit sexual words; instead, you use poetic, suggestive language. "
    "You can include emojis that fit the mood — but only if they match the tone."
)

# 💦 Mood-based emoji generator
def add_emojis_based_on_mood(text):
    text_lower = text.lower()
    if any(word in text_lower for word in ["love", "sweetheart", "darling", "kiss", "romantic", "mine", "heart"]):
        return text + " ❤️💋🥰"
    elif any(word in text_lower for word in ["hot", "burn", "fire", "desire", "temptation", "flirt"]):
        return text + " 🥵💦👅"
    elif any(word in text_lower for word in ["sad", "cry", "lonely", "heartbreak", "miss you"]):
        return text + " 😢💔"
    elif any(word in text_lower for word in ["happy", "smile", "laugh", "funny", "joy"]):
        return text + " 😄✨💫"
    else:
        return text + " 😁💞"

# 🧠 Generate reply using Groq
async def generate_reply(user_message: str) -> str:
    response = client.chat.completions.create(
        model="llama3-8b-8192",  # safe & smooth model
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]
    )
    reply_text = response.choices[0].message.content.strip()
    reply_text = add_emojis_based_on_mood(reply_text)
    return reply_text

# 💬 Telegram message handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    reply_text = await generate_reply(user_message)
    await update.message.reply_text(reply_text)

# 🚀 Main function
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🔥 TAEKOOK is online and ready to flirt!")
    app.run_polling()

if __name__ == "__main__":
    main()
