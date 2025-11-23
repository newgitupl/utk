import os
from flask import Flask
from threading import Thread
from pyrogram import Client

# Flask app for landing page
app = Flask(__name__)

@app.route('/')
def landing():
    return """
    <html>
      <head>
        <title>MARCO</title>
        <style>
          body { 
            font-family: Arial, sans-serif; 
            background: #222; 
            color: #fff;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
          }
          .title {
            font-size: 60px;
            letter-spacing: 10px;
            color: #FFDF00;
            text-shadow: 2px 2px 8px #666;
          }
          .subtitle {
            font-size: 24px;
            color: #bbb;
            margin-top: 30px;
          }
        </style>
      </head>
      <body>
        <div class="title">MARCO</div>
        <div class="subtitle">Your Telegram Bot is Live on Koyeb! 🚀</div>
      </body>
    </html>
    """

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    print(f"Landing page running on port {port}! 🌐")
    app.run(host="0.0.0.0", port=port)

def run_bot():
    bot = Client(
        "⏤͟͞𝗠𝗔𝗥𝗖𝗢 🐦‍🔥",
        bot_token=os.environ.get("BOT_TOKEN"),
        api_id=int(os.environ.get("API_ID")),
        api_hash=os.environ.get("API_HASH"),
    )
    print("Telegram bot started! 🚀")
    bot.run()

if __name__ == "__main__":
    Thread(target=run_flask).start()
    run_bot()
