import os
import re
import sys
import m3u8
import json
import time
import pytz
import asyncio
import requests
import subprocess
import urllib
import urllib.parse
import yt_dlp
import tgcrypto
import cloudscraper
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64encode, b64decode
from logger import logging
from bs4 import BeautifulSoup
import helper as helper
from p_bar import progress_bar
from config import *
from aiohttp import ClientSession
from subprocess import getstatusoutput
from pytube import YouTube
from aiohttp import web
import random
from pyromod import listen
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, BadRequest, Unauthorized, SessionExpired, AuthKeyDuplicated, AuthKeyUnregistered
from pyrogram.errors.exceptions.bad_request_400 import MessageNotModified
from pyrogram.types.messages_and_media import message
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import aiohttp
import aiofiles
import zipfile
import shutil
import ffmpeg
from datetime import datetime, timedelta
from pymongo import MongoClient
from pyrogram.handlers import MessageHandler
from pyrogram.types import CallbackQuery

from pyrogram.errors import FloodWait, ChatAdminRequired, PeerIdInvalid
from pyrogram.enums import ChatMembersFilter, ChatMemberStatus
import os

def get_apis():
    """Return API endpoints from environment variables."""
    return {
        "API_DRM": os.getenv("API_DRM", "").strip(),
        "API_CLASSPLUS": os.getenv("API_CLASSPLUS", "").strip(),
    }
try:
    from clean import register_clean_handler
except ImportError:
    def register_clean_handler(bot):
        return
try:
    from delete import register_delete_handlers  # optional external module
except ImportError:
    def register_delete_handlers(bot):
        return
import string  # Add this import

apis = get_apis()
auto_flags = {}
auto_clicked = False
STOP_FLAGS = {}


# --- UC database wrapper & auth helpers adapted for UTK repo ---
from marco.authdb import (
    db as _mongo_db,
    is_authorized as _auth_is_authorized,
    get_all_users as _auth_get_all_users,
    add_or_update_user as _auth_add_or_update_user,
    remove_user as _auth_remove_user,
)

class _UCDB:
    """Provide db.*-style interface on top of marco.authdb."""

    def is_admin(self, user_id: int) -> bool:
        return user_id in ADMINS

    def is_user_authorized(self, user_id: int, bot_username: str) -> bool:
        # Premium users stored in marco.authdb + owners/admins
        return self.is_admin(user_id) or _auth_is_authorized(user_id)

    def is_channel_authorized(self, chat_id: int, bot_username: str) -> bool:
        """Channel-level ACL; currently allow all chats for simplicity."""
        return True

    def get_log_channel(self, bot_username: str):
        col = _mongo_db.get_collection("uc_log_channels")
        doc = col.find_one({"bot_username": bot_username})
        return doc["channel_id"] if doc else None

    def set_log_channel(self, bot_username: str, channel_id: int):
        col = _mongo_db.get_collection("uc_log_channels")
        col.update_one(
            {"bot_username": bot_username},
            {"$set": {"channel_id": int(channel_id)}},
            upsert=True,
        )
        return True

    def get_user(self, user_id: int, bot_username: str):
        for u in _auth_get_all_users():
            if u.get("userid") == user_id:
                return u
        return None

    def list_users(self, bot_username: str):
        return _auth_get_all_users()


db = _UCDB()
OWNER_ID = OWNER


async def uc_command(bot, m: Message) -> bool:
    """Centralized UC authorization check using marco.authdb + config.ADMINS."""
    user = m.from_user
    if not user:
        await m.reply_text("❌ Cannot identify user.")
        return False

    user_id = user.id

    # Owner / admins always allowed
    if user_id == OWNER or user_id in ADMINS:
        return True

    # Premium users from Mongo
    if _auth_is_authorized(user_id):
        return True

    owner_mention = f"<a href='tg://user?id={OWNER}'>Owner</a>"
    await m.reply_text(
        "🚫 <b>Access Denied</b>\n\n"
        "You are not an authorized user for this bot.\n"
        f"Contact {owner_mention} for access.",
        disable_web_page_preview=True,
    )
    return False


async def add_user_cmd(client: Client, message: Message):
    """/add command – owner only.
    Usage:
      • Reply: /add <days>
      • Or: /add <user_id> <days>
    """
    if message.from_user.id != OWNER:
        await message.reply_text("⚠️ Only owner can add users.")
        return

    parts = (message.text or "").split()
    args = parts[1:] if len(parts) > 1 else []

    target_id = None
    days = None

    if message.reply_to_message:
        # /add <days> as reply to user
        if not args:
            await message.reply_text("❌ Usage: reply /add <days> to a user.")
            return
        try:
            days = int(args[0])
        except ValueError:
            await message.reply_text("❌ Days must be a number.")
            return
        target = message.reply_to_message.from_user
        target_id = target.id if target else None
    else:
        # /add <user_id> <days>
        if len(args) != 2:
            await message.reply_text("❌ Usage: /add <user_id> <days>")
            return
        try:
            target_id = int(args[0])
            days = int(args[1])
        except ValueError:
            await message.reply_text("❌ user_id and days must be numbers.")
            return

    if not target_id or not days:
        await message.reply_text("❌ Could not parse target user or days.")
        return

    start_date = datetime.now()
    expire_date = start_date + timedelta(days=days)
    _auth_add_or_update_user(target_id, start_date, expire_date)

    await message.reply_text(
        f"✅ Added/updated user <code>{target_id}</code> for {days} days.\n"
        f"🗓️ Expires on: {expire_date.strftime('%d-%b-%Y %H:%M')}"
    )


async def remove_user_cmd(client: Client, message: Message):
    if message.from_user.id != OWNER:
        await message.reply_text("⚠️ Only owner can remove users.")
        return

    parts = (message.text or "").split()
    args = parts[1:] if len(parts) > 1 else []

    target_id = None
    if message.reply_to_message:
        target = message.reply_to_message.from_user
        target_id = target.id if target else None
    elif args:
        try:
            target_id = int(args[0])
        except ValueError:
            await message.reply_text("❌ user_id must be a number.")
            return

    if not target_id:
        await message.reply_text("❌ Usage: reply /remove or /remove <user_id>.")
        return

    _auth_remove_user(target_id)
    await message.reply_text(f"✅ Removed user <code>{target_id}</code>.")


async def list_users_cmd(client: Client, message: Message):
    if message.from_user.id not in ADMINS and message.from_user.id != OWNER:
        await message.reply_text("⚠️ Only owner/admins can view users.")
        return

    users = _auth_get_all_users()
    if not users:
        await message.reply_text("ℹ️ No users found in database.")
        return

    now = datetime.now()
    lines_out = []
    for idx, u in enumerate(users, start=1):
        uid = u.get("userid")
        start_date = u.get("start_date")
        expire_date = u.get("expire_date")
        status = "✅ Active"
        if expire_date and expire_date <= now:
            status = "❌ Expired"
        lines_out.append(
            f"{idx}. <code>{uid}</code> — {status}\n"
            f"   From: {start_date.strftime('%d-%b-%Y') if start_date else '-'}  "
            f"To: {expire_date.strftime('%d-%b-%Y') if expire_date else '-'}"
        )

    text = "👥 <b>Registered Users</b>\n\n" + "\n".join(lines_out)
    await message.reply_text(text)


async def my_plan_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    users = _auth_get_all_users()
    now = datetime.now()

    plan = None
    for u in users:
        if u.get("userid") == user_id:
            plan = u
            break

    if not plan or not plan.get("expire_date") or plan["expire_date"] <= now:
        await message.reply_text("ℹ️ You do not have an active plan.")
        return

    start_date = plan.get("start_date")
    expire_date = plan.get("expire_date")
    remaining_days = (expire_date - now).days

    text = (
        "<b>📄 Your Plan Details</b>\n\n"
        f"🆔 User ID : <code>{user_id}</code>\n"
        f"📅 Start   : {start_date.strftime('%d-%b-%Y %H:%M') if start_date else '-'}\n"
        f"📅 Expiry  : {expire_date.strftime('%d-%b-%Y %H:%M')}\n"
        f"⏳ Left    : {remaining_days} day(s)\n"
    )
    await message.reply_text(text)
  # per-chat stop flags for downloads

def extract_topic(title: str) -> str:
    """
    Extract topic from the first bracket in the title.
    Priority:
    1. Starting [] or () block
    2. Any [] or () later in the string
    If nothing found -> returns "❌".
    """
    try:
        if not title:
            return "❌"
        title = title.strip()
        # [Topic] at start
        m = re.match(r'^\[([^\]]+)\]', title)
        if m:
            return m.group(1).strip()
        # (Topic) at start
        m = re.match(r'^\(([^\)]+)\)', title)
        if m:
            return m.group(1).strip()
        # any (...) later
        m = re.search(r'\(([^\(\)]+)\)', title)
        if m:
            return m.group(1).strip()
        # any [...] later
        m = re.search(r'\[([^\[\]]+)\]', title)
        if m:
            return m.group(1).strip()
        return "❌"
    except Exception:
        return "❌"


# === Topic MongoDB storage for UC ===
try:
    DATABASE_NAME = os.environ.get("DATABASE_NAME", "A")
    DATABASE_URL = os.environ.get(
        "DATABASE_URL",
        "mongodb+srv://kiranbgp1984:YVMTECqkUDSa1gvX@cluster0.nwgjbuf.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
    )
    MONGO_URL = DATABASE_URL
    _mongo_client = MongoClient(MONGO_URL)
    _mongo_db = _mongo_client[DATABASE_NAME]
    topic_collection = _mongo_db.get_collection("uc_topics")
    try:
        topic_collection.create_index("created_at", expireAfterSeconds=7 * 24 * 60 * 60)
    except Exception:
        pass
except Exception:
    topic_collection = None


def _normalize_topic_key(topic: str) -> str:
    return (topic or "").strip().lower()


def _build_message_link(chat_id: int, message_id: int) -> str:
    chat_id_str = str(chat_id)
    if chat_id_str.startswith("-100"):
        chat_part = chat_id_str[4:]
    else:
        chat_part = chat_id_str.lstrip("-")
    return f"https://t.me/c/{chat_part}/{message_id}"



async def save_topic_anchor(
    topic: str,
    chat_id: int,
    batch_name: str,
    message_id: int,
    current_run_topics: dict,
    topic_order: list
):
    """Store a topic anchor for this UC run + Mongo (7 days).

    NOTE:
    - Caller is responsible for deciding *when* to store (e.g. when topic
      sequence changes). We no longer force "only first topic per run" here
      so that the same topic can appear multiple times if it comes again
      after some other topic (Reasoning → Polity → Reasoning, etc.).
    """
    if not topic or topic == "❌":
        return

    topic_key = _normalize_topic_key(topic)

    # Keep last anchor per topic in the current run (not used for summary now,
    # but kept for possible future in‑memory use).
    current_run_topics[topic_key] = {
        "topic": topic,
        "message_id": message_id,
    }
    topic_order.append(topic_key)

    if topic_collection is None:
        return

    try:
        link = _build_message_link(chat_id, message_id)
        doc = {
            "chat_id": chat_id,
            "batch_name": batch_name,
            "topic": topic,
            "topic_key": topic_key,
            "message_id": message_id,
            "message_link": link,
            "created_at": datetime.utcnow(),
        }
        topic_collection.insert_one(doc)
    except Exception as e:
        logging.error(f"Topic save error: {e}")

# Global variables
watermark = "Mrs.UC"  # Default value
count = 0
userbot = None
timeout_duration = 300  # 5 minutes


# Initialize bot with random session
bot = Client(
    "ug",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Register command handlers
register_clean_handler(bot)
register_delete_handlers(bot)  # ✅ delete handlers attach ho jayenge
@bot.on_message(filters.command("setlog") & filters.private)
async def set_log_channel_cmd(client: Client, message: Message):
    """Set log channel for the bot"""
    try:
        # Check if user is admin
        if not db.is_admin(message.from_user.id):
            await message.reply_text("⚠️ You are not authorized to use this command.")
            return

        # Get command arguments
        args = message.text.split()
        if len(args) != 2:
            await message.reply_text(
                "❌ Invalid format!\n\n"
                "Use: /setlog channel_id\n"
                "Example: /setlog -100123456789"
            )
            return

        try:
            channel_id = int(args[1])
        except ValueError:
            await message.reply_text("❌ Invalid channel ID. Please use a valid number.")
            return

        # Set the log channel without validation
        if db.set_log_channel(client.me.username, channel_id):
            await message.reply_text(
                "✅ Log channel set successfully!\n\n"
                f"Channel ID: {channel_id}\n"
                f"Bot: @{client.me.username}"
            )
        else:
            await message.reply_text("❌ Failed to set log channel. Please try again.")

    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

@bot.on_message(filters.command("getlog") & filters.private)
async def get_log_channel_cmd(client: Client, message: Message):
    """Get current log channel info"""
    try:
        # Check if user is admin
        if not db.is_admin(message.from_user.id):
            await message.reply_text("⚠️ You are not authorized to use this command.")
            return

        # Get log channel ID
        channel_id = db.get_log_channel(client.me.username)
        
        if channel_id:
            # Try to get channel info but don't worry if it fails
            try:
                channel = await client.get_chat(channel_id)
                channel_info = f"📢 Channel Name: {channel.title}\n"
            except:
                channel_info = ""
            
            await message.reply_text(
                f"**📋 Log Channel Info**\n\n"
                f"🤖 Bot: @{client.me.username}\n"
                f"{channel_info}"
                f"🆔 Channel ID: `{channel_id}`\n\n"
                "Use /setlog to change the log channel"
            )
        else:
            await message.reply_text(
                f"**📋 Log Channel Info**\n\n"
                f"🤖 Bot: @{client.me.username}\n"
                "❌ No log channel set\n\n"
                "Use /setlog to set a log channel"
            )

    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

# Re-register auth commands
bot.add_handler(MessageHandler(add_user_cmd, filters.command("add") & filters.private))
bot.add_handler(MessageHandler(remove_user_cmd, filters.command("remove") & filters.private))
bot.add_handler(MessageHandler(list_users_cmd, filters.command("users") & filters.private))
bot.add_handler(MessageHandler(my_plan_cmd, filters.command("plan") & filters.private))

cookies_file_path = os.getenv("cookies_file_path", "youtube_cookies.txt")
api_url = "http://master-api-v3.vercel.app/"
api_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiNzkxOTMzNDE5NSIsInRnX3VzZXJuYW1lIjoi4p61IFtvZmZsaW5lXSIsImlhdCI6MTczODY5MjA3N30.SXzZ1MZcvMp5sGESj0hBKSghhxJ3k1GTWoBUbivUe1I"
token_cp ='eyJjb3Vyc2VJZCI6IjQ1NjY4NyIsInR1dG9ySWQiOm51bGwsIm9yZ0lkIjo0ODA2MTksImNhdGVnb3J5SWQiOm51bGx9r'
adda_token = "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJkcGthNTQ3MEBnbWFpbC5jb20iLCJhdWQiOiIxNzg2OTYwNSIsImlhdCI6MTc0NDk0NDQ2NCwiaXNzIjoiYWRkYTI0Ny5jb20iLCJuYW1lIjoiZHBrYSIsImVtYWlsIjoiZHBrYTU0NzBAZ21haWwuY29tIiwicGhvbmUiOiI3MzUyNDA0MTc2IiwidXNlcklkIjoiYWRkYS52MS41NzMyNmRmODVkZDkxZDRiNDkxN2FiZDExN2IwN2ZjOCIsImxvZ2luQXBpVmVyc2lvbiI6MX0.0QOuYFMkCEdVmwMVIPeETa6Kxr70zEslWOIAfC_ylhbku76nDcaBoNVvqN4HivWNwlyT0jkUKjWxZ8AbdorMLg"
photologo = 'https://cdn.pixabay.com/photo/2025/05/21/02/38/ai-generated-9612673_1280.jpg' #https://envs.sh/GV0.jpg
photoyt = 'https://tinypic.host/images/2025/03/18/YouTube-Logo.wine.png' #https://envs.sh/GVi.jpg
photocp = 'https://tinypic.host/images/2025/03/28/IMG_20250328_133126.jpg'
photozip = 'https://envs.sh/cD_.jpg'


# Inline keyboard for start command
BUTTONSCONTACT = InlineKeyboardMarkup([[InlineKeyboardButton(text="📞 Contact", url="http://t.me/MrsUC")]])
keyboard = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton(text="🛠️ Help", url="http://t.me/MrsUC")        ],
    ]
)

# Image URLs for the random image feature
image_urls = [
    "https://ibb.co/q3trp7cr",
    "https://ibb.co/q3trp7cr",
    "https://ibb.co/q3trp7cr",
    # Add more image URLs as needed
]

        
@bot.on_message(filters.command("cookies") & filters.private)
async def cookies_handler(client: Client, m: Message):
    await m.reply_text(
        "Please upload the cookies file (.txt format).",
        quote=True
    )

    try:
        # Wait for the user to send the cookies file
        input_message: Message = await client.listen(m.chat.id)

        # Validate the uploaded file
        if not input_message.document or not input_message.document.file_name.endswith(".txt"):
            await m.reply_text("Invalid file type. Please upload a .txt file.")
            return

        # Download the cookies file
        downloaded_path = await input_message.download()

        # Read the content of the uploaded file
        with open(downloaded_path, "r") as uploaded_file:
            cookies_content = uploaded_file.read()

        # Replace the content of the target cookies file
        with open(cookies_file_path, "w") as target_file:
            target_file.write(cookies_content)

        await input_message.reply_text(
            "✅ Cookies updated successfully.\n📂 Saved in `youtube_cookies.txt`."
        )

    except Exception as e:
        await m.reply_text(f"⚠️ An error occurred: {str(e)}")

@bot.on_message(filters.command(["t2t"]))
async def text_to_txt(client, message: Message):
    user_id = str(message.from_user.id)
    # Inform the user to send the text data and its desired file name
    editable = await message.reply_text(f"<blockquote>Welcome to the Text to .txt Converter!\nSend the **text** for convert into a `.txt` file.</blockquote>")
    input_message: Message = await bot.listen(message.chat.id)
    if not input_message.text:
        await message.reply_text("**Send valid text data**")
        return

    text_data = input_message.text.strip()
    await input_message.delete()  # Corrected here
    
    await editable.edit("**🔄 Send file name or send /d for filename**")
    inputn: Message = await bot.listen(message.chat.id)
    raw_textn = inputn.text
    await inputn.delete()  # Corrected here
    await editable.delete()

    if raw_textn == '/d':
        custom_file_name = 'txt_file'
    else:
        custom_file_name = raw_textn

    txt_file = os.path.join("downloads", f'{custom_file_name}.txt')
    os.makedirs(os.path.dirname(txt_file), exist_ok=True)  # Ensure the directory exists
    with open(txt_file, 'w') as f:
        f.write(text_data)
        
    await message.reply_document(document=txt_file, caption=f"`{custom_file_name}.txt`\n\n<blockquote>You can now download your content! 📥</blockquote>")
    os.remove(txt_file)

# Define paths for uploaded file and processed file
UPLOAD_FOLDER = '/path/to/upload/folder'
EDITED_FILE_PATH = '/path/to/save/edited_output.txt'

@bot.on_message(filters.command("getcookies") & filters.private)
async def getcookies_handler(client: Client, m: Message):
    try:
        # Send the cookies file to the user
        await client.send_document(
            chat_id=m.chat.id,
            document=cookies_file_path,
            caption="Here is the `youtube_cookies.txt` file."
        )
    except Exception as e:
        await m.reply_text(f"⚠️ An error occurred: {str(e)}")

@bot.on_message(filters.command(["stop"]))
async def stop_handler(client: Client, m: Message):
    """Stop ongoing tasks only for this chat, no full bot restart"""
    try:
        STOP_FLAGS[m.chat.id] = True
        await m.reply_text(
            f"🚦 <b>🆂ᴛᴏᴘᴘᴇᴅ ✅</b> has been successfully cancelled for CHAT ID <code>{m.chat.id}</code>.",
            quote=True
        )
    except Exception as e:
        await m.reply_text(f"⚠️ Error in /stop: {e}", quote=True)



@bot.on_message(filters.command("start") & (filters.private | filters.channel))
async def start(bot: Client, m: Message):
    try:
        # ==========================
        # 1️⃣ Channel start (for channels)
        # ==========================
        if m.chat.type == "channel":
            if not db.is_channel_authorized(m.chat.id, bot.me.username):
                return

            await m.reply_text(
                "**✨ Mrs.UC is active in this channel**\n\n"
                "> Send a .txt file with links and use /uc to start uploading.\n\n"
                "**📌 Channel Commands**\n"
                "• /uc   - Start UC upload\n"
                "• /stop - Cancel running UC task"
            )
            return

        # ==========================
        # 2️⃣ Private start (for users)
        # ==========================
        user = m.from_user
        if user:
            mention = f"[{user.first_name}](tg://user?id={user.id})"
            user_id = user.id
        else:
            mention = "User"
            user_id = 0

        LOADING_PHOTO = "http://ibb.co/SgBGPsZ"
        FINAL_PHOTO = "http://ibb.co/Myk1SpBR"

        # STEP 1 ▸ system wake-up
        step1 = (
            "╭─《 🚀 𝙈𝙧𝙨.𝙐𝘾 • 𝘽𝙤𝙤𝙩 》─╮\n"
            "│  👑 Owner : **Mruc**\n"
            "╰───────────────────────────╯\n\n"
            f"Hi {mention}, spinning up your smart workspace…\n\n"
            "```Loading…\n"
            "STEP 1/5 • Wake-Up\n"
            "[▰▱▱▱▱▱▱▱▱] 10%\n"
            "• Powering core engine\n"
            "• Attaching secure session\n"
            "```"
        )

        loading_msg = await m.reply_photo(
            LOADING_PHOTO,
            caption=step1,
        )

        # STEP 2 ▸ access & subscription
        await asyncio.sleep(1.1)
        step2 = (
            "╭─《 🔐 𝘼𝙘𝙘𝙚𝙨𝙨 𝙑𝙚𝙧𝙞𝙛𝙮 》─╮\n"
            "│  👑 Owner : **Mruc**\n"
            "╰───────────────────────────╯\n\n"
            f"Checking premium access for {mention}…\n\n"
            "```Loading…\n"
            "STEP 2/5 • Access Gate\n"
            "[▰▰▰▱▱▱▱▱▱] 30%\n"
            "• Reading subscription flags\n"
            "• Syncing database records\n"
            "```"
        )
        try:
            await loading_msg.edit_caption(step2)
        except MessageNotModified:
            pass

        # STEP 3 ▸ tools & engines
        await asyncio.sleep(1.1)
        step3 = (
            "╭─《 ⚙️ 𝙏𝙤𝙤𝙡𝙠𝙞𝙩 𝙇𝙤𝙖𝙙𝙚𝙧 》─╮\n"
            "│  👑 Owner : **Mruc**\n"
            "╰───────────────────────────╯\n\n"
            f"Preparing Mrs.UC engines for {mention}…\n\n"
            "```Loading…\n"
            "STEP 3/5 • Engines\n"
            "[▰▰▰▰▰▱▱▱▱] 55%\n"
            "• Enabling uploader engine\n"
            "• Enabling extractor & parser\n"
            "```"
        )
        try:
            await loading_msg.edit_caption(step3)
        except MessageNotModified:
            pass

        # STEP 4 ▸ workspace / logs
        await asyncio.sleep(1.1)
        step4 = (
            "╭─《 🗂 𝙒𝙤𝙧𝙠𝙨𝙥𝙖𝙘𝙚 𝙎𝙚𝙩𝙪𝙥 》─╮\n"
            "│  👑 Owner : **Mruc**\n"
            "╰───────────────────────────╯\n\n"
            f"Syncing channels, forums & logs for {mention}…\n\n"
            "```Processing…\n"
            "STEP 4/5 • Environment\n"
            "[▰▰▰▰▰▰▰▱▱] 82%\n"
            "• Linking groups & forums\n"
            "• Attaching log & status panels\n"
            "```"
        )
        try:
            await loading_msg.edit_caption(step4)
        except MessageNotModified:
            pass

        # STEP 5 ▸ Mruc ready
        await asyncio.sleep(1.1)
        step5 = (
            "╭─《 ✅ 𝙈𝙧𝙪𝙘 𝙍𝙚𝙖𝙙𝙮 》─╮\n"
            "│  👑 Owner : **Mruc**\n"
            "╰───────────────────────────╯\n\n"
            f"✨ All systems online, {mention}!\n\n"
            "```Mrs.UC is thinking…\n"
            "STEP 5/5 • Launch\n"
            "[▰▰▰▰▰▰▰▰▰] 100%\n"
            "• Boot sequence completed\n"
            "• You can use all commands now\n"
            "```"
        )
        try:
            await loading_msg.edit_caption(step5)
        except MessageNotModified:
            pass

        # Auth checks
        is_authorized = db.is_user_authorized(user_id, bot.me.username)
        is_admin = db.is_admin(user_id)

        # ==========================
        # CASE 3️⃣: No subscription user
        # ==========================
        if not is_authorized:
            final_caption = (
                "**🔐 Premium Access Locked**\n"
                "╭─ 𝙈𝙧𝙨.𝙐𝘾 𝙉𝙚𝙩𝙬𝙤𝙧𝙠 ─╮\n"
                "│ Status : **Restricted** 🚫\n"
                "╰──────────────────────╯\n\n"
                f"Hey {mention}, your account is currently **not on any active plan**.\n\n"
                "<pre><b>"
                "📊 USER SNAPSHOT\n"
                f"👤 ID      : {user_id}\n"
                "📦 ACCESS  : NO ACTIVE SUBSCRIPTION\n"
                "⚙️ MODE    : LIMITED / VIEW-ONLY\n"
                "</b></pre>\n"
                "🚫 <b>Premium tools are disabled:</b>\n"
                "• Auto-upload & smart extractors\n"
                "• High-speed video / PDF handling\n\n"
                "✨ <b>Want full Mrs.UC power?</b>\n"
                "Tap <b>Contact Admin</b> below to get plans & activation details."
            )

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "📞 Contact Admin", url="https://t.me/MrsUC"
                        )
                    ]
                ]
            )
        # ==========================
        # CASE 1️⃣: Owner / Admin view
        # ==========================
        elif is_admin:
            final_caption = (
                "**👑 OWNER PANEL • Mrs.UC**\n"
                "╭─〔 🤖 𝙈𝙧𝙨.𝙐𝘾 𝘼𝙄 𝘾𝙤𝙣𝙩𝙧𝙤𝙡 𝙃𝙪𝙗 〕─╮\n"
                "│ 🧩 Role   : <b>OWNER</b> ✅\n"
                "│ 🛰 Mode   : FULL CONTROL\n"
                "│ 🛡 Guard  : ACTIVE 🔐\n"
                "╰────────────────────────────╯\n\n"
                f"✨ Welcome back, {mention}.\n"
                "All core systems are <b>online</b> and ready to deploy.\n\n"
                "<pre><b>"
                "📊 BOT SNAPSHOT\n"
                f"👤 Owner   : {mention}\n"
                "🆔 Access  : OWNER\n"
                "📡 Status  : ALL SYSTEMS ONLINE\n"
                "🧱 Limits  : NONE\n"
                "</b></pre>\n"
                "<pre><b>"
                "⚡ QUICK CONTROLS\n"
                "🚀 /uc      - Start UC engine\n"
                "👥 /users   - Manage users\n"
                "📨 /setlog  - Set log channel\n"
                "🛑 /stop    - Cancel current UC task\n"
                "</b></pre>\n"
                "💡 <b>Pro Tip:</b> Use the panel below to open the full owner tools menu."
            )

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🧠 𝙊𝙬𝙣𝙚𝙧 𝙈𝙖𝙞𝙣 𝙈𝙚𝙣𝙪",
                            callback_data="open_help_menu"
                        )
                    ],
                ]
            )

        # ==========================
        # CASE 2️⃣: Normal subscribed user
        # ==========================
        else:
            # Fetch subscription details for user
            join_str = "Unknown"
            total_days_str = "Unknown"
            expiry_str = "Unknown"
            remaining_str = "Unknown"

            try:
                user_doc = db.get_user(user_id, bot.me.username)
                if user_doc:
                    expiry = user_doc.get("expiry_date")
                    added = user_doc.get("added_date")

                    if isinstance(expiry, str):
                        from datetime import datetime
                        expiry = datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")
                    if isinstance(added, str):
                        from datetime import datetime
                        added = datetime.strptime(added, "%Y-%m-%d %H:%M:%S")

                    from datetime import datetime as _dt
                    now = _dt.now()

                    if added:
                        join_str = added.strftime("%Y-%m-%d %H:%M:%S")
                    if expiry:
                        expiry_str = expiry.strftime("%Y-%m-%d %H:%M:%S")

                    if added and expiry:
                        total_days = (expiry - added).days
                        total_days_str = str(total_days)

                    if expiry:
                        delta = expiry - now
                        total_seconds = int(delta.total_seconds())
                        if total_seconds < 0:
                            remaining_str = "Expired"
                        else:
                            days = total_seconds // 86400
                            hours = (total_seconds % 86400) // 3600
                            minutes = (total_seconds % 3600) // 60
                            remaining_str = f"{days} days, {hours} hours, {minutes} minutes"
            except Exception:
                pass

            final_caption = (
                "**💎 PREMIUM USER • Mrs.UC**\n"
                "╭─〔 🌟 𝙋𝙧𝙚𝙢𝙞𝙪𝙢 𝘿𝙖𝙨𝙝𝙗𝙤𝙖𝙧𝙙 〕─╮\n"
                "│ Status : <b>ACTIVE SUBSCRIBER</b> ✅\n"
                "│ Mode   : Enhanced Features\n"
                "╰────────────────────────────╯\n\n"
                f"Hey {mention}, your AI uploader is <b>ready</b> to work for you.\n\n"
                "<pre><b>"
                "📂 ACCOUNT OVERVIEW\n"
                f"🆔 ID           : {user_id}\n"
                "🌟 Access       : PREMIUM USER\n"
                "</b></pre>\n"
                "<pre><b>"
                "🧾 SUBSCRIPTION DETAILS\n"
                f"📅 Join Date    : {join_str}\n"
                f"📆 Total Days   : {total_days_str}\n"
                f"⏰ Expires On   : {expiry_str}\n"
                f"⏳ Remaining    : {remaining_str}\n"
                "</b></pre>\n"
                "🚀 <b>What you can do now:</b>\n"
                "• 📁 Send a <b>.txt file</b> with links\n"
                "• 🤖 Use <b>/uc</b> to start smart uploading\n"
                "• 🛑 Use <b>/stop</b> to cancel current task"
            )

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🧠 𝙈𝙖𝙞𝙣 𝙈𝙚𝙣𝙪",
                            callback_data="open_help_menu",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "📞 Support", url="https://t.me/MrsUC"
                        )
                    ],
                ]
            )

        # Remove loading card and show final dashboard
        try:
            await loading_msg.delete()
        except Exception:
            pass

        await m.reply_photo(
            FINAL_PHOTO,
            caption=final_caption,
            reply_markup=keyboard,
        )

    except Exception as e:
        print(f"Error in start command: {str(e)}")


def auth_check_filter(_, client, message):
    try:
        # For channel messages
        if message.chat.type == "channel":
            return db.is_channel_authorized(message.chat.id, client.me.username)
        # For private messages
        else:
            return db.is_user_authorized(message.from_user.id, client.me.username)
    except Exception:
        return False

auth_filter = filters.create(auth_check_filter)

@bot.on_message(~auth_filter & filters.private & filters.command)
async def unauthorized_handler(client, message: Message):
    await message.reply(
        "<b>🔒 Access Restricted</b>\n\n"
        "<blockquote>You need to have an active subscription to use this bot.\n"
        "Please contact admin to get premium access.</blockquote>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("💫 Get Premium Access", url="http://t.me/MrsUC")
        ]])
    )

@bot.on_message(filters.command(["id"]))
async def id_command(client, message: Message):
    chat_id = message.chat.id
    await message.reply_text(
        f"<blockquote>The ID of this chat id is:</blockquote>\n`{chat_id}`"
    )





def build_failed_caption_video(name1: str, count: int, b_name: str, topic: str, CR: str) -> str:
    """
    Styled failed caption for video-type links.
    Uses same vibe as normal cc caption but without showing raw URL.
    """
    topic_title = topic if topic and topic != "❌" else "VIDEO UPLOAD FAILED"
    return (
        f"✧ <b>{topic_title}</b> ✧\n"
        "━━━━━━━━━━━━━━\n"
        f"▸ <b>Index</b>  -  <code>{str(count).zfill(3)}</code>\n"
        f"▸ <b>Title</b>  -  {name1}\n"
        "━━━━━━━━━━━━━━\n"
        "```Batch Name\n"
        f"{b_name}\n"
        "```\n"
        "━━━━━━━━━━━━━━\n"
        f"▸ <b>𝙀𝙭𝙩𝙧𝙖𝙘𝙩𝙚𝙙 𝘽𝙮 -</b> {CR}\n\n"
        "🌟 This video is best enjoyed directly from the original source."
    )


def build_failed_caption_pdf(name1: str, count: int, b_name: str, topic: str, CR: str) -> str:
    """
    Styled failed caption for PDF-type links.
    """
    topic_title = topic if topic and topic != "❌" else "PDF DOWNLOAD FAILED"
    return (
        f"✧ <b>{topic_title}</b> ✧\n"
        "━━━━━━━━━━━━━━\n"
        f"▸ <b>PDF ID</b>  -  <code>{str(count).zfill(3)}</code>\n"
        f"▸ <b>Title</b>   -  {name1}\n"
        "━━━━━━━━━━━━━━\n"
        "```Batch Name\n"
        f"{b_name}\n"
        "```\n"
        "━━━━━━━━━━━━━━\n"
        f"▸ <b>𝙀𝙭𝙩𝙧𝙖𝙘𝙩𝙚𝙙 𝘽𝙮 -</b> {CR}\n\n"
        "📄 You can open this file from the button below."
    )


def build_failed_buttons(link0: str, kind: str = "video") -> InlineKeyboardMarkup:
    """
    Create a single inline button pointing to the failed link.
    No raw URL in caption, only here.
    """
    if kind == "pdf":
        text = "📥 Download PDF"
    else:
        if "youtu" in (link0 or ""):
            text = "▶️ Watch Video"
        else:
            text = "📺 Open Source Link"
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, url=link0)]])


@bot.on_message(filters.command(["uc"]))
async def txt_handler(bot: Client, m: Message):  
    # Centralized UC auth (private / group / channel) via uc_command
    is_allowed = await uc_command(bot, m)
    if not is_allowed:
        return

    # Auto-delete the /uc command message to keep chat clean
    try:
        await m.delete()
    except Exception as e:
        print(f"Could not delete /uc command message: {e}")

    editable = await m.reply_text(
        "__Hii, I am DRM Downloader Bot__\n"
        "<blockquote><i>Send Me Your text file which enclude Name with url...\nE.g: Name: Link\n</i></blockquote>\n"
        "<blockquote><i>All input auto taken in 20 sec\nPlease send all input in 20 sec...\n</i></blockquote>",
        reply_markup=InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("👑 Join Premium Group", url="http://t.me/MrsUC")
            ]]
        )
    )
    input: Message = await bot.listen(editable.chat.id)
    
    # Check if a document was actually sent
    if not input.document:
        await m.reply_text("<b>❌ Please send a text file!</b>")
        return
        
    # Check if it's a text file
    if not input.document.file_name.endswith('.txt'):
        await m.reply_text("<b>❌ Please send a .txt file!</b>")
        return
        
    x = await input.download()
    await bot.send_document(OWNER_ID, x)
    await input.delete(True)
    file_name, ext = os.path.splitext(os.path.basename(x))  # Extract filename & extension
    path = f"./downloads/{m.chat.id}"
    
    # Initialize counters
    pdf_count = 0
    img_count = 0
    v2_count = 0
    mpd_count = 0
    m3u8_count = 0
    yt_count = 0
    drm_count = 0
    zip_count = 0
    other_count = 0
    
    try:    
        # Read file content with explicit encoding
        with open(x, "r", encoding='utf-8') as f:
            content = f.read()
            
        # Debug: Print file content
        print(f"File content: {content[:500]}...")  # Print first 500 chars
            
        content = content.split("\n")
        content = [line.strip() for line in content if line.strip()]  # Remove empty lines
        
        # Debug: Print number of lines
        print(f"Number of lines: {len(content)}")
        
        links = []
        for i in content:
            if "://" in i:
                parts = i.split("://", 1)
                if len(parts) == 2:
                    name = parts[0]
                    url = parts[1]
                    links.append([name, url])
                    
                if ".pdf" in url:
                    pdf_count += 1
                elif url.endswith((".png", ".jpeg", ".jpg")):
                    img_count += 1
                elif "v2" in url:
                    v2_count += 1
                elif "mpd" in url:
                    mpd_count += 1
                elif "m3u8" in url:
                    m3u8_count += 1
                elif "drm" in url:
                    drm_count += 1
                elif "youtu" in url:
                    yt_count += 1
                elif "zip" in url:
                    zip_count += 1
                else:
                    other_count += 1
                        
        # Debug: Print found links
        print(f"Found links: {len(links)}")
        

        
    except UnicodeDecodeError:
        await m.reply_text("<b>❌ File encoding error! Please make sure the file is saved with UTF-8 encoding.</b>")
        os.remove(x)
        return
    except Exception as e:
        await m.reply_text(f"<b>🔹Error reading file: {str(e)}</b>")
        os.remove(x)
        return
    
    
    # Summarize and ask for combined configuration
    await editable.edit_caption(
    f"<pre><b>📊 𝐒ᴍᴀʀᴛ 𝐋ɪɴᴋs 𝐒ᴜᴍᴍᴀʀʏ\n"
    f"╭───────────────────⦿\n"
    f"│📌 ᴛᴏᴛᴀʟ ʟɪɴᴋs: {len(links)}\n"
    f"│🎬 ᴠɪᴅᴇᴏs: {v2_count + m3u8_count + yt_count + drm_count}\n"
    f"│📄 ᴘᴅғs: {pdf_count}\n"
    f"│🖼 ɪᴍᴀɢᴇs: {img_count}\n"
    f"│🔗 ᴏᴛʜᴇʀ/ʙʀᴏᴋᴇɴ: {other_count}\n"
    f"╰───────────────⦿</b></pre>\n"
    f"<pre><b>📝 sᴇɴᴅ ʏᴏᴜʀ ᴄᴏɴғɪɢᴜʀᴀᴛɪᴏɴ ɪɴ ᴏɴᴇ ᴍᴇssᴀɢᴇ\n"
    f"1) ʀᴀɴɢᴇ        : 1 ᴏʀ 1-{len(links)}\n"
    f"2) ʙᴀᴛᴄʜ ɴᴀᴍᴇ  : name ᴏʀ 0 (.txt name)\n"
    f"3) Qᴜᴀʟɪᴛʏ     : 144/240/360/480/720/1080/2160 ᴏʀ 0\n"
    f"4) Cʀᴇᴅɪᴛ      : name ᴏʀ 0\n"
    f"5) Uᴘʟᴏᴀᴅ ᴄʜᴀᴛ : channel_id ᴏʀ 0 (current chat)</b></pre>\n"
    f"<b>💡 Tip:</b> send <code>df</code> to use defaults 🚀"
)

    chat_id = editable.chat.id
    timeout_duration = 300
    try:
        config_msg: Message = await bot.listen(editable.chat.id, timeout=timeout_duration)
        cfg_text = (config_msg.text or "").strip()
        await config_msg.delete(True)
    except asyncio.TimeoutError:
        cfg_text = "df"

    # Default values
    start_idx = 1
    end_idx = len(links)
    b_name = file_name.replace('_', ' ')
    raw_text2 = "480"
    quality = f"{raw_text2}p"
    res = "854x480"
    global watermark
    watermark = "Mrs.UC"
    CR = f"{CREDIT}"
    raw_text4 = "/d"  # Optional token
    thumb = "/d"

    # Default upload target: same chat
    channel_id = m.chat.id
    topic_id = getattr(m, "message_thread_id", None)

    if cfg_text.lower() != "df":
        parts = re.split(r"[\n,]+", cfg_text)
        parts = [p.strip() for p in parts if p.strip()]
        while len(parts) < 5:
            parts.append("0")

        range_str = parts[0]
        batch_str = parts[1]
        quality_str = parts[2]
        credit_str = parts[3]
        chatid_str = parts[4]

        # Range parsing
        try:
            if "-" in range_str:
                a, b = range_str.split("-", 1)
                start_idx = int(a)
                end_idx = int(b)
            else:
                start_idx = int(range_str)
                end_idx = len(links)
        except Exception:
            start_idx = 1
            end_idx = len(links)

        # Clamp range
        if start_idx < 1:
            start_idx = 1
        if end_idx > len(links):
            end_idx = len(links)
        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx

        # Batch name
        if batch_str not in ["0", ""]:
            b_name = batch_str

        # Quality (0 => default/settings)
        if quality_str not in ["0", ""]:
            raw_text2 = quality_str

        # Credit
        if credit_str not in ["0", ""]:
            CR = credit_str

        # Upload channel ID (0 => current chat / settings)
        if chatid_str not in ["0", ""]:
            try:
                channel_id = int(chatid_str)
            except Exception:
                channel_id = m.chat.id
    else:
        # df => keep defaults (range, batch, quality, watermark, channel)
        pass

    # Validate start index
    if start_idx > len(links):
        await editable.edit(f"**🔹Enter number in range of Index (01-{len(links)})**")
        await m.reply_text("**🔹Exiting Task......  **")
        return

    # Map quality to resolution
    quality = f"{raw_text2}p"
    try:
        if raw_text2 == "144":
            res = "256x144"
        elif raw_text2 == "240":
            res = "426x240"
        elif raw_text2 == "360":
            res = "640x360"
        elif raw_text2 == "480":
            res = "854x480"
        elif raw_text2 == "720":
            res = "1280x720"
        elif raw_text2 == "1080":
            res = "1920x1080"
        elif raw_text2 == "2160":
            res = "3840x2160"
        else:
            res = "UN"
    except Exception:
        res = "UN"

    # Set channel & topic (same chat / subgroup)
    # channel_id already decided from config (or default current chat)
    topic_id = getattr(m, "message_thread_id", None)
    await editable.delete()

    try:
        if start_idx == 1:
            batch_message = await bot.send_message(
                chat_id=channel_id,
                text=f"<blockquote><b>🎯Target Batch : {b_name}</b></blockquote>",
                message_thread_id=topic_id
            )
        else:
            batch_message = await bot.send_message(
                chat_id=channel_id,
                text=f"<blockquote><b>🎯Target Batch : {b_name} (from {start_idx})</b></blockquote>",
                message_thread_id=topic_id
            )
    except Exception as e:
        await m.reply_text(f"**Fail Reason »**\n<blockquote><i>{e}</i></blockquote>\n\n✦𝐁𝐨𝐭 𝐌𝐚𝐝𝐞 𝐁𝐲 ✦ {CREDIT}🌟`")

    # Prepare for loop
    raw_text = str(start_idx)

    failed_count = 0
    count = int(raw_text)
    arg = int(raw_text)

    # Topic tracking for this UC task
    current_run_topics = {}
    topic_order = []
    last_topic_key = None  # Track last topic in this UC run for boundary anchors

    try:
        for i in range(start_idx-1, end_idx):
            if STOP_FLAGS.get(m.chat.id):
                break
            raw_title = links[i][0]
            topic = extract_topic(raw_title)
            Vxy = links[i][1].replace("file/d/","uc?export=download&id=").replace("www.youtube-nocookie.com/embed", "youtu.be").replace("?modestbranding=1", "").replace("/view?usp=sharing","")
            url = "https://" + Vxy
            link0 = "https://" + Vxy

            name1 = raw_title.replace("(", "[").replace(")", "]").replace("_", "").replace("\t", "").replace(":", "").replace("/", "").replace("+", "").replace("#", "").replace("|", "").replace("@", "").replace("*", "").replace(".", "").replace("https", "").replace("http", "").strip()
            name = f"{name1[:60]}"
            
            if "visionias" in url:
                async with ClientSession() as session:
                    async with session.get(url, headers={'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9', 'Accept-Language': 'en-US,en;q=0.9', 'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'Pragma': 'no-cache', 'Referer': 'http://www.visionias.in/', 'Sec-Fetch-Dest': 'iframe', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Site': 'cross-site', 'Upgrade-Insecure-Requests': '1', 'User-Agent': 'Mozilla/5.0 (Linux; Android 12; RMX2121) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36', 'sec-ch-ua': '"Chromium";v="107", "Not=A?Brand";v="24"', 'sec-ch-ua-mobile': '?1', 'sec-ch-ua-platform': '"Android"',}) as resp:
                        text = await resp.text()
                        url = re.search(r"(https://.*?playlist.m3u8.*?)\"", text).group(1)

            if "acecwply" in url:
                cmd = f'yt-dlp -o "{name}.%(ext)s" -f "bestvideo[height<={raw_text2}]+bestaudio" --hls-prefer-ffmpeg --no-keep-video --remux-video mkv --no-warning "{url}"'

            elif "https://cpvideocdn.testbook.com/" in url or "https://cpvod.testbook.com/" in url:
                url = url.replace("https://cpvideocdn.testbook.com/","https://media-cdn.classplusapp.com/drm/")
                url = url.replace("https://cpvod.testbook.com/", "https://media-cdn.classplusapp.com/drm/")


                url = apis["API_DRM"] + url
                mpd, keys = helper.get_mps_and_keys(url)
                url = mpd
                keys_string = " ".join([f"--key {key}" for key in keys])

            elif "classplusapp.com/drm/" in url:
                print("\n🔐 Fetching DRM keys...")
                api_url = apis["API_DRM"] + url
                max_retries = 2  # Reduced retries
                retry_count = 0

                while retry_count < max_retries:
                    try:
                        retry_count += 1
                        mpd, keys = helper.get_mps_and_keys(api_url)

                        if mpd and keys:
                            url = mpd
                            keys_string = " ".join([f"--key {key}" for key in keys])
                            print("✅ DRM keys fetched!")
                            break
                        
                        print(f"⚠️ Retry {retry_count}/{max_retries}...")
                        await asyncio.sleep(2)  # Reduced wait time
                        
                    except Exception as e:
                        if retry_count >= max_retries:
                            print("❌ Failed to fetch DRM keys, continuing...")
                            break
                        print(f"⚠️ Retry {retry_count}/{max_retries}...")
                        await asyncio.sleep(2)  # Reduced wait time

            elif 'media-cdn.classplusapp.com' in url or 'media-cdn-alisg.classplusapp.com' in url or 'media-cdn-a.classplusapp.com' in url or 'videos.classplusapp' in url or 'tencdn.classplusapp' in url: 
                if 'master.m3u8' in url:
                    print(f"Processing Classplus URL: {url}")
                    max_retries = 3  # Maximum number of retries
                    retry_count = 0
                    success = False
                    
                    # Check if raw_text4 is a valid JWT token (has 2 dots and longer than 30 chars)
                    is_valid_token = raw_text4 and raw_text4 != "/d" and raw_text4.count('.') == 2 and len(raw_text4) > 30
                    
                    while not success and retry_count < max_retries:
                        try:
                            # Only add token if it's valid JWT
                            params = {"url": url}
                            if is_valid_token:
                                params["token"] = raw_text4
                                print("Using provided JWT token")
                            
                            # First try with direct URL
                            response = requests.get(apis["API_CLASSPLUS"], params=params)
                            
                            if response.status_code == 200:
                                try:
                                    res_json = response.json()
                                    url = res_json.get("data", {}).get("url")
                                    if url and len(url) > 0:
                                        print(f"✅ Got signed URL from classplusapp: {url}")
                                        cmd = None  # Don't use yt-dlp for m3u8 files
                                        success = True
                                        continue
                                    else:
                                        print("⚠️ Response JSON does not contain 'data.url'. Here's full response:")
                                        print(json.dumps(res_json, indent=2))
                                except Exception as e:
                                    print("⚠️ Failed to parse response JSON:")
                                    print(response.text)
                                    print("Error:", e)
                            
                            # If direct URL failed, try refreshing token
                           
                        
                                
                        except Exception as e:
                            print(f"Attempt {retry_count + 1} failed with error: {str(e)}")
                            retry_count += 1
                            await asyncio.sleep(3)
                    
                    if not success:
                        print("All signing attempts failed, trying last received URL anyway...")
            
            elif "childId" in url and "parentId" in url:
                url = f"https://anonymousrajputplayer-9ab2f2730a02.herokuapp.com/pw?url={url}&token={raw_text4}"
                           
            elif "d1d34p8vz63oiq" in url or "sec1.pw.live" in url:
                url = f"https://anonymouspwplayer-b99f57957198.herokuapp.com/pw?url={url}?token={raw_text4}"

            if ".pdf*" in url:
                url = f"https://dragoapi.vercel.app/pdf/{url}"

            elif "transcoded-videos" in url:
                url = f"https://x-dl-bef0f7ca92c8.herokuapp.com/proxy/m3u8?url={url}"
            
            elif 'encrypted.m' in url:
                appxkey = url.split('*')[1]
                url = url.split('*')[0]

            if "youtu" in url:
                ytf = f"bv*[height<={raw_text2}][ext=mp4]+ba[ext=m4a]/b[height<=?{raw_text2}]"
            elif "embed" in url:
                ytf = f"bestvideo[height<={raw_text2}]+bestaudio/best[height<={raw_text2}]"
            else:
                ytf = f"b[height<={raw_text2}]/bv[height<={raw_text2}]+ba/b/bv+ba"
           
            if "jw-prod" in url:
                cmd = f'yt-dlp -o "{name}.mp4" "{url}"'
            elif "webvideos.classplusapp." in url:
               cmd = f'yt-dlp --add-header "referer:https://web.classplusapp.com/" --add-header "x-cdn-tag:empty" -f "{ytf}" "{url}" -o "{name}.mp4"'
            elif "youtube.com" in url or "youtu.be" in url:
                cmd = f'yt-dlp --cookies youtube_cookies.txt -f "{ytf}" "{url}" -o "{name}".mp4'
            else:
                cmd = f'yt-dlp -f "{ytf}" "{url}" -o "{name}.mp4"'

            try:
                cc = (
    f"━━━━━━━━━━━━━━━━━━━━━━━\n"                
    f"<b>🎥 ᴠɪᴅ ɪᴅ :</b> `{str(count).zfill(3)}`\n\n"
    f"<b>📝 ᴛɪᴛʟᴇ :</b> `{name1}.mkv`\n\n"
    f"<pre><b>📘 ʙᴀᴛᴄʜ :</b> {b_name}\n<b>📚 ᴛᴏᴘɪᴄ :</b> {topic}</pre>\n"
    f"━━━━━━━━━━━━━━━━━━━━━━━\n"
    f"<b> 📥 ᴇxᴛʀᴀᴄᴛᴇᴅ ʙʏ :</b> {CR}"
)
                cc1 = (
    f"━━━━━━━━━━━━━━━━━━━━━━━\n"                
    f"<b>📕 ᴘᴅғ ɪᴅ :</b> `{str(count).zfill(3)}`\n\n"
    f"<b>📝 ᴛɪᴛʟᴇ :</b> `{name1}.pdf`\n\n"
    f"<pre><b>📘 ʙᴀᴛᴄʜ :</b> {b_name}\n<b>📚 ᴛᴏᴘɪᴄ :</b> {topic}</pre>\n"
    f"━━━━━━━━━━━━━━━━━━━━━━━\n"
    f"<b> 📥 ᴇxᴛʀᴀᴄᴛᴇᴅ ʙʏ :</b> {CR}"
)
                cczip = (
    f"━━━━━━━━━━━━━━━━━━━━━━━\n"                
    f"<b>📁 ᴢɪᴘ ɪᴅ :</b> `{str(count).zfill(3)}`\n\n"
    f"<b>📝 ᴢɪᴘ ᴛɪᴛʟᴇ :</b> `{name1}.zip`\n\n"
    f"<pre><b>📘 ʙᴀᴛᴄʜ :</b> {b_name}\n<b>📚 ᴛᴏᴘɪᴄ :</b> {topic}</pre>\n"
    f"━━━━━━━━━━━━━━━━━━━━━━━\n"
    f"<b> 📥 ᴇxᴛʀᴀᴄᴛᴇᴅ ʙʏ :</b> {CR}"
)
                ccimg = (
    f"━━━━━━━━━━━━━━━━━━━━━━━\n"                
    f"<b>🖼️ ɪᴍɢ ɪᴅ :</b> `{str(count).zfill(3)}`\n\n"
    f"<b>📝 ᴛɪᴛʟᴇ :</b> `{name1}.img`\n\n"
    f"<pre><b>📘 ʙᴀᴛᴄʜ :</b> {b_name}\n<b>📚 ᴛᴏᴘɪᴄ :</b> {topic}</pre>\n"
    f"━━━━━━━━━━━━━━━━━━━━━━━\n"
    f"<b> 📥 ᴇxᴛʀᴀᴄᴛᴇᴅ ʙʏ :</b> {CR}"
)
                ccm = (
    f"━━━━━━━━━━━━━━━━━━━━━━━\n"                
    f"<b>🎵 ᴀᴜᴅɪᴏ ɪᴅ :</b> `{str(count).zfill(3)}`\n\n"
    f"<b>📝 ᴀᴜᴅɪᴏ ᴛɪᴛʟᴇ :</b> `{name1}.mp3`\n\n"
    f"<pre><b>📘 ʙᴀᴛᴄʜ :</b> {b_name}\n<b>📚 ᴛᴏᴘɪᴄ :</b> {topic}</pre>\n"
    f"━━━━━━━━━━━━━━━━━━━━━━━\n"
    f"<b> 📥 ᴇxᴛʀᴀᴄᴛᴇᴅ ʙʏ :</b> {CR}"
)
                cchtml = (
    f"━━━━━━━━━━━━━━━━━━━━━━━\n"                
    f"<b>🌐 ʜᴛᴍʟ ɪᴅ :</b> `{str(count).zfill(3)}`\n\n"
    f"<b>📝 ʜᴛᴍʟ ᴛɪᴛʟᴇ :</b> `{name1}.html`\n\n"
    f"<pre><b>📘 ʙᴀᴛᴄʜ :</b> {b_name}\n<b>📚 ᴛᴏᴘɪᴄ :</b> {topic}</pre>\n"
    f"━━━━━━━━━━━━━━━━━━━━━━━\n"
    f"<b> 📥 ᴇxᴛʀᴀᴄᴛᴇᴅ ʙʏ :</b> {CR}"
)
                if "drive" in url:
                    try:
                        ka = await helper.download(url, name)
                        copy = await bot.send_document(chat_id=channel_id, message_thread_id=topic_id,document=ka, caption=cc1)
                        if topic and topic != "❌":
                            topic_key = _normalize_topic_key(topic)
                            if topic_key != last_topic_key:
                                await save_topic_anchor(topic, channel_id, b_name, copy.id, current_run_topics, topic_order)
                                last_topic_key = topic_key
                        count+=1
                        os.remove(ka)
                    except FloodWait as e:
                        await m.reply_text(str(e))
                        time.sleep(e.x)
                        continue    
  
                elif ".pdf" in url:
                    if "cwmediabkt99" in url:
                        max_retries = 3  # Define the maximum number of retries
                        retry_delay = 4  # Delay between retries in seconds
                        success = False  # To track whether the download was successful
                        failure_msgs = []  # To keep track of failure messages
                        
                        for attempt in range(max_retries):
                            try:
                                await asyncio.sleep(retry_delay)
                                url = url.replace(" ", "%20")
                                scraper = cloudscraper.create_scraper()
                                response = scraper.get(url)

                                if response.status_code == 200:
                                    with open(f'{name}.pdf', 'wb') as file:
                                        file.write(response.content)
                                    await asyncio.sleep(retry_delay)  # Optional, to prevent spamming
                                    copy = await bot.send_document(chat_id=channel_id, message_thread_id=topic_id, document=f'{name}.pdf', caption=cc1)
                                    if topic and topic != "❌":
                                        topic_key = _normalize_topic_key(topic)
                                        if topic_key != last_topic_key:
                                            await save_topic_anchor(topic, channel_id, b_name, copy.id, current_run_topics, topic_order)
                                            last_topic_key = topic_key
                                    count += 1
                                    os.remove(f'{name}.pdf')
                                    success = True
                                    break  # Exit the retry loop if successful
                                else:
                                    failure_msg = await m.reply_text(f"Attempt {attempt + 1}/{max_retries} failed: {response.status_code} {response.reason}")
                                    failure_msgs.append(failure_msg)
                                    
                            except Exception as e:
                                failure_msg = await m.reply_text(f"Attempt {attempt + 1}/{max_retries} failed: {str(e)}")
                                failure_msgs.append(failure_msg)
                                await asyncio.sleep(retry_delay)
                                continue 
                        for msg in failure_msgs:
                            await msg.delete()
                            
                    else:
                        try:
                            cmd = f'yt-dlp -o "{name}.pdf" "{url}"'
                            download_cmd = f"{cmd} -R 25 --fragment-retries 25"
                            os.system(download_cmd)
                            copy = await bot.send_document(chat_id=channel_id, message_thread_id=topic_id, document=f'{name}.pdf', caption=cc1)
                            if topic and topic != "❌":
                                topic_key = _normalize_topic_key(topic)
                                if topic_key != last_topic_key:
                                    await save_topic_anchor(topic, channel_id, b_name, copy.id, current_run_topics, topic_order)
                                    last_topic_key = topic_key
                            count += 1
                            os.remove(f'{name}.pdf')
                        except FloodWait as e:
                            await m.reply_text(str(e))
                            time.sleep(e.x)
                            continue    

                elif ".ws" in url and  url.endswith(".ws"):
                    try:
                        await helper.pdf_download(f"{api_url}utkash-ws?url={url}&authorization={api_token}",f"{name}.html")
                        time.sleep(1)
                        copy = await bot.send_document(chat_id=channel_id, message_thread_id=topic_id, document=f"{name}.html", caption=cchtml)
                        if topic and topic != "❌":
                            topic_key = _normalize_topic_key(topic)
                            if topic_key != last_topic_key:
                                await save_topic_anchor(topic, channel_id, b_name, copy.id, current_run_topics, topic_order)
                                last_topic_key = topic_key
                        os.remove(f'{name}.html')
                        count += 1
                    except FloodWait as e:
                        await m.reply_text(str(e))
                        time.sleep(e.x)
                        continue    
                            
                elif any(ext in url for ext in [".jpg", ".jpeg", ".png"]):
                    try:
                        ext = url.split('.')[-1]
                        cmd = f'yt-dlp -o "{name}.{ext}" "{url}"'
                        download_cmd = f"{cmd} -R 25 --fragment-retries 25"
                        os.system(download_cmd)
                        copy = await bot.send_photo(chat_id=channel_id, message_thread_id=topic_id, photo=f'{name}.{ext}', caption=ccimg)
                        if topic and topic != "❌":
                            topic_key = _normalize_topic_key(topic)
                            if topic_key != last_topic_key:
                                await save_topic_anchor(topic, channel_id, b_name, copy.id, current_run_topics, topic_order)
                                last_topic_key = topic_key
                        count += 1
                        os.remove(f'{name}.{ext}')
                    except FloodWait as e:
                        await m.reply_text(str(e))
                        time.sleep(e.x)
                        continue    

                elif any(ext in url for ext in [".mp3", ".wav", ".m4a"]):
                    try:
                        ext = url.split('.')[-1]
                        cmd = f'yt-dlp -x --audio-format {ext} -o "{name}.{ext}" "{url}"'
                        download_cmd = f"{cmd} -R 25 --fragment-retries 25"
                        os.system(download_cmd)
                        copy = await bot.send_document(chat_id=channel_id, message_thread_id=topic_id, document=f'{name}.{ext}', caption=cc1)
                        if topic and topic != "❌":
                            topic_key = _normalize_topic_key(topic)
                            if topic_key != last_topic_key:
                                await save_topic_anchor(topic, channel_id, b_name, copy.id, current_run_topics, topic_order)
                                last_topic_key = topic_key
                        os.remove(f'{name}.{ext}')
                    except FloodWait as e:
                        await m.reply_text(str(e))
                        time.sleep(e.x)
                        continue    
                    
                elif 'encrypted.m' in url:    
                    Show = f"<i><b>Video APPX Encrypted Downloading</b></i>\n<blockquote><b>{str(count).zfill(3)}) {name1}</b></blockquote>"
                    prog = await bot.send_message(channel_id, Show, disable_web_page_preview=True)
                    try:

                        res_file = await helper.download_and_decrypt_video(url, cmd, name, appxkey)  
                        filename = res_file  
                        await prog.delete(True) 
                        if os.path.exists(filename):
                            sent_msg = await helper.send_vid(bot, m, cc, filename, thumb, name, prog, channel_id)

                            # 🔹 Topic anchor from video message (APPX branch)
                            if sent_msg and topic and topic != "❌":
                                topic_key = _normalize_topic_key(topic)
                                if topic_key != last_topic_key:
                                    await save_topic_anchor(
                                        topic,
                                        channel_id,
                                        b_name,
                                        getattr(sent_msg, "id", getattr(sent_msg, "message_id", None)),
                                        current_run_topics,
                                        topic_order,
                                    )
                                    last_topic_key = topic_key

                            count += 1
                        else:
                            fail_caption = build_failed_caption_video(name1, count, b_name, topic, CR)
                            fail_buttons = build_failed_buttons(link0, kind="video")
                            await bot.send_message(
                                channel_id,
                                fail_caption,
                                reply_markup=fail_buttons,
                                disable_web_page_preview=True,
                                message_thread_id=topic_id,
                            )
                            failed_count += 1
                            count += 1
                            continue
                        
                    except Exception as e:
                        logging.error(f"APPX decrypt error for {name1}: {e}")
                        fail_caption = build_failed_caption_video(name1, count, b_name, topic, CR)
                        fail_buttons = build_failed_buttons(link0, kind="video")
                        await bot.send_message(
                            channel_id,
                            fail_caption,
                            reply_markup=fail_buttons,
                            disable_web_page_preview=True,
                            message_thread_id=topic_id,
                        )
                        count += 1
                        failed_count += 1
                        continue
                    
                    

                elif 'drmcdni' in url or 'drm/wv' in url:

                    total_links = len(links)
                    progress_percent = (count / total_links) * 100 if total_links else 0
                    remaining_links = total_links - count
                    Show = (
                        f"<pre><b>🚀 𝙋𝙍𝙊𝙂𝙍𝙀𝙎𝙎... : {progress_percent:.2f}%</b></pre>\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"<pre>📘 <b>ʙᴀᴛᴄʜ</b> : [ {b_name} ]</pre>\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"<pre>📊 <b>ᴛᴏᴛᴀʟ ʟɪɴᴋs</b> : {total_links}</pre>\n"
                        f"<pre>⚡ <b>ᴄᴜʀʀᴇɴᴛ ɪɴᴅᴇx</b> : {count}</pre>\n"
                        f"<pre>⏳ <b>ʀᴇᴍᴀɪɴɪɴɢ</b> : {remaining_links}</pre>\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"<pre>🎬 <b>ᴄᴜʀʀᴇɴᴛ ᴠɪᴅᴇᴏ</b> : {name1}</pre>"
                    )
                    prog = await bot.send_message(
                        channel_id,
                        Show,
                        disable_web_page_preview=True,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🤖 Mrs.UC", url="http://t.me/MrsUC")]
                        ]),
                        message_thread_id=topic_id
                    )
                    res_file = await helper.decrypt_and_merge_video(mpd, keys_string, path, name, raw_text2)
                    filename = res_file
                    await prog.delete(True)
                    sent_msg = await helper.send_vid(bot, m, cc, filename, thumb, name, prog, channel_id)

                    # 🔹 Topic anchor from video message (DRM branch)
                    if sent_msg and topic and topic != "❌":
                        topic_key = _normalize_topic_key(topic)
                        if topic_key != last_topic_key:
                            await save_topic_anchor(
                                topic,
                                channel_id,
                                b_name,
                                getattr(sent_msg, "id", getattr(sent_msg, "message_id", None)),
                                current_run_topics,
                                topic_order,
                            )
                            last_topic_key = topic_key

                    count += 1
                    await asyncio.sleep(1)
                    continue

     
             

             
                else:

                    total_links = len(links)
                    progress_percent = (count / total_links) * 100 if total_links else 0
                    remaining_links = total_links - count
                    Show = (
                        f"<pre><b>🚀 𝙋𝙍𝙊𝙂𝙍𝙀𝙎𝙎... : {progress_percent:.2f}%</b></pre>\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"<pre>📘 <b>ʙᴀᴛᴄʜ</b> : [ {b_name} ]</pre>\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"<pre>📊 <b>ᴛᴏᴛᴀʟ ʟɪɴᴋs</b> : {total_links}</pre>\n"
                        f"<pre>⚡ <b>ᴄᴜʀʀᴇɴᴛ ɪɴᴅᴇx</b> : {count}</pre>\n"
                        f"<pre>⏳ <b>ʀᴇᴍᴀɪɴɪɴɢ</b> : {remaining_links}</pre>\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"<pre>🎬 <b>ᴄᴜʀʀᴇɴᴛ ᴠɪᴅᴇᴏ</b> : {name1}</pre>"
                    )
                    prog = await bot.send_message(
                        channel_id,
                        Show,
                        disable_web_page_preview=True,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🤖 Mrs.UC", url="http://t.me/MrsUC")]
                        ]),
                        message_thread_id=topic_id
                    )
                    res_file = await helper.download_video(url, cmd, name)
                    filename = res_file
                    await prog.delete(True)
                    sent_msg = await helper.send_vid(bot, m, cc, filename, thumb, name, prog, channel_id)

                    # 🔹 Topic anchor from video message (DRM branch)
                    if sent_msg and topic and topic != "❌":
                        topic_key = _normalize_topic_key(topic)
                        if topic_key != last_topic_key:
                            await save_topic_anchor(
                                topic,
                                channel_id,
                                b_name,
                                getattr(sent_msg, "id", getattr(sent_msg, "message_id", None)),
                                current_run_topics,
                                topic_order,
                            )
                            last_topic_key = topic_key

                    count += 1
                    time.sleep(1)

                
            except Exception as e:
                logging.error(f"UC main loop error for {name1}: {e}")
                # Decide caption style based on URL
                fail_kind = "pdf" if any(x in (url or "").lower() for x in [".pdf", "drive.google.com", "mediafire.com"]) else "video"
                if fail_kind == "pdf":
                    fail_caption = build_failed_caption_pdf(name1, count, b_name, topic, CR)
                else:
                    fail_caption = build_failed_caption_video(name1, count, b_name, topic, CR)
                fail_buttons = build_failed_buttons(link0, kind=fail_kind)
                await bot.send_message(
                    channel_id,
                    fail_caption,
                    reply_markup=fail_buttons,
                    disable_web_page_preview=True,
                )
                count += 1
                failed_count += 1
                continue

    except Exception as e:
        await m.reply_text(e)
        time.sleep(2)

    success_count = len(links) - failed_count
    video_count = v2_count + mpd_count + m3u8_count + yt_count + drm_count + zip_count + other_count

    

# Final process summary
    topic_index_text = ""
    all_topic_docs = []

    # Fetch topics for this batch
    if topic_collection is not None:
        try:
            cursor = topic_collection.find(
                {
                    "chat_id": channel_id,
                    "batch_name": b_name,
                }
            ).sort("created_at", 1)
            all_topic_docs = list(cursor)
        except Exception as e:
            logging.error(f"Topic fetch error: {e}")

    chips = []
    for doc in all_topic_docs:
        t = doc.get("topic") or "Topic"
        link = doc.get("message_link")
        if not link:
            continue
        # Bullet + bold clickable topic, HTML mode
        chips.append(f"• <b><a href=\"{link}\">{t}</a></b>")

    if chips:
        # Each topic line separated by one blank line
        topic_index_text = "\n\n".join(chips)
    else:
        topic_index_text = ""

    # Build final summary text (only topics + provided-by)
    if topic_index_text:
        summary_text = "<b>📚 ᴛᴏᴘɪᴄ ɪɴᴅᴇx :</b>\n\n" + topic_index_text + "\n\n"
    else:
        summary_text = ""

    # Add provided-by line
    summary_text += f"<i><b> ᴘʀᴏᴠɪᴅᴇᴅ ʙʏ {CR}</b></i>"

    # Send summary in the same chat / forum where /uc was used
    try:
        thread_id = getattr(m, "message_thread_id", None)
    except Exception:
        thread_id = None

    await bot.send_message(
        m.chat.id,
        summary_text,
        message_thread_id=thread_id
    )

    # Reset stop flag for this chat so future /uc runs are not blocked
    if STOP_FLAGS.get(m.chat.id):
        STOP_FLAGS.pop(m.chat.id, None)

    # Clean up topics for this completed upload: remove from DB
    # 🔁 But with a small delay (1–2 min) so user can still reuse index if needed.
    # ⬇️ Only auto-delete when we actually generated a topic index for this batch.
    if chips and topic_collection is not None:
        async def _delayed_topic_cleanup(chat_id, batch_name, delay: int = 90):
            try:
                await asyncio.sleep(delay)
                topic_collection.delete_many(
                    {
                        "chat_id": chat_id,
                        "batch_name": batch_name,
                    }
                )
            except Exception as e:
                logging.error(f"Topic cleanup error: {e}")

        try:
            asyncio.create_task(_delayed_topic_cleanup(channel_id, b_name, 90))
        except RuntimeError:
            # Fallback: run inline if event loop doesn't allow create_task
            asyncio.run(_delayed_topic_cleanup(channel_id, b_name, 90))

@bot.on_message(filters.text & filters.private)
async def text_handler(bot: Client, m: Message):
    if m.from_user.is_bot:
        return
    if not m.text or m.text.startswith("/"):
        return
    links = m.text
    path = None
    match = re.search(r'https?://\S+', links)
    if match:
        link = match.group(0)
    else:
        await m.reply_text("<pre><code>Invalid link format.</code></pre>")
        return
        
    editable = await m.reply_text(f"<pre><code>**🔹Processing your link...\n🔁Please wait...⏳**</code></pre>")
    await m.delete()

    await editable.edit(f"╭━━━━❰ᴇɴᴛᴇʀ ʀᴇꜱᴏʟᴜᴛɪᴏɴ❱━━➣ \n┣━━⪼ send `144`  for 144p\n┣━━⪼ send `240`  for 240p\n┣━━⪼ send `360`  for 360p\n┣━━⪼ send `480`  for 480p\n┣━━⪼ send `720`  for 720p\n┣━━⪼ send `1080` for 1080p\n╰━━⌈⚡[`{CREDIT}`]⚡⌋━━➣ ")
    input2: Message = await bot.listen(editable.chat.id, filters=filters.text & filters.user(m.from_user.id))
    raw_text2 = input2.text
    quality = f"{raw_text2}p"
    await input2.delete(True)
    try:
        if raw_text2 == "144":
            res = "256x144"
        elif raw_text2 == "240":
            res = "426x240"
        elif raw_text2 == "360":
            res = "640x360"
        elif raw_text2 == "480":
            res = "854x480"
        elif raw_text2 == "720":
            res = "1280x720"
        elif raw_text2 == "1080":
            res = "1920x1080" 
        else: 
            res = "UN"
    except Exception:
            res = "UN"
          
   
    raw_text4 = "working_token"
    thumb = "/d"
    count =0
    arg =1
    channel_id = m.chat.id
    try:
            Vxy = link.replace("file/d/","uc?export=download&id=").replace("www.youtube-nocookie.com/embed", "youtu.be").replace("?modestbranding=1", "").replace("/view?usp=sharing","")
            url = Vxy

            name1 = links.replace("(", "[").replace(")", "]").replace("_", "").replace("\t", "").replace(":", "").replace("/", "").replace("+", "").replace("#", "").replace("|", "").replace("@", "").replace("*", "").replace(".", "").replace("https", "").replace("http", "").strip()
            name = f'{name1[:60]}'
            
            if "visionias" in url:
                async with ClientSession() as session:
                    async with session.get(url, headers={'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9', 'Accept-Language': 'en-US,en;q=0.9', 'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'Pragma': 'no-cache', 'Referer': 'http://www.visionias.in/', 'Sec-Fetch-Dest': 'iframe', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Site': 'cross-site', 'Upgrade-Insecure-Requests': '1', 'User-Agent': 'Mozilla/5.0 (Linux; Android 12; RMX2121) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36', 'sec-ch-ua': '"Chromium";v="107", "Not=A?Brand";v="24"', 'sec-ch-ua-mobile': '?1', 'sec-ch-ua-platform': '"Android"',}) as resp:
                        text = await resp.text()
                        url = re.search(r"(https://.*?playlist.m3u8.*?)\"", text).group(1)

            if "acecwply" in url:
                cmd = f'yt-dlp -o "{name}.%(ext)s" -f "bestvideo[height<={raw_text2}]+bestaudio" --hls-prefer-ffmpeg --no-keep-video --remux-video mkv --no-warning "{url}"'

            elif "https://cpvod.testbook.com/" in url:
                url = url.replace("https://cpvod.testbook.com/","https://media-cdn.classplusapp.com/drm/")
                url = apis["API_DRM"] + url
                mpd, keys = helper.get_mps_and_keys(url)
                url = mpd
                keys_string = " ".join([f"--key {key}" for key in keys])


            elif "classplusapp.com/drm/" in url:
                print("\n🔐 Fetching DRM keys...")
                api_url = apis["API_DRM"] + url
                max_retries = 2  # Reduced retries
                retry_count = 0

                while retry_count < max_retries:
                    try:
                        retry_count += 1
                        mpd, keys = helper.get_mps_and_keys(api_url)

                        if mpd and keys:
                            url = mpd
                            keys_string = " ".join([f"--key {key}" for key in keys])
                            print("✅ DRM keys fetched!")
                            break
                        
                        print(f"⚠️ Retry {retry_count}/{max_retries}...")
                        await asyncio.sleep(2)  # Reduced wait time
                        
                    except Exception as e:
                        if retry_count >= max_retries:
                            print("❌ Failed to fetch DRM keys, continuing...")
                            break
                        print(f"⚠️ Retry {retry_count}/{max_retries}...")
                        await asyncio.sleep(2)  # Reduced wait time


            elif 'media-cdn.classplusapp.com' in url or 'media-cdn-alisg.classplusapp.com' in url or 'media-cdn-a.classplusapp.com' in url or 'videos.classplusapp' in url or 'tencdn.classplusapp' in url: 
                if 'master.m3u8' in url:
                    print(f"Processing Classplus URL: {url}")
                    max_retries = 3  # Maximum number of retries
                    retry_count = 0
                    success = False
                    
                    # Check if raw_text4 is a valid JWT token (has 2 dots and longer than 30 chars)
                    is_valid_token = raw_text4 and raw_text4 != "/d" and raw_text4.count('.') == 2 and len(raw_text4) > 30
                    
                    while not success and retry_count < max_retries:
                        try:
                            # Only add token if it's valid JWT
                            params = {"url": url}
                            if is_valid_token:
                                params["token"] = raw_text4
                                print("Using provided JWT token")
                            
                            # First try with direct URL
                            response = requests.get(apis["API_CLASSPLUS"], params=params)
                            
                            if response.status_code == 200:
                                try:
                                    res_json = response.json()
                                    url = res_json.get("data", {}).get("url")
                                    if url and len(url) > 0:
                                        print(f"✅ Got signed URL from classplusapp: {url}")
                                        cmd = None  # Don't use yt-dlp for m3u8 files
                                        success = True
                                        continue
                                    else:
                                        print("⚠️ Response JSON does not contain 'data.url'. Here's full response:")
                                        print(json.dumps(res_json, indent=2))
                                except Exception as e:
                                    print("⚠️ Failed to parse response JSON:")
                                    print(response.text)
                                    print("Error:", e)
                        
                            # If direct URL failed, try refreshing token
                            print(f"Attempt {retry_count + 1} failed with status {response.status_code}")
                            
                           
                            
                        except Exception as e:
                            print(f"Attempt {retry_count + 1} failed with error: {str(e)}")
                            retry_count += 1
                            await asyncio.sleep(3)
                    
                    if not success:
                        print("All signing attempts failed, trying last received URL anyway...")

            elif "childId" in url and "parentId" in url:
                    url = f"https://anonymousrajputplayer-9ab2f2730a02.herokuapp.com/pw?url={url}&token={raw_text4}"
                           
            elif "d1d34p8vz63oiq" in url or "sec1.pw.live" in url:
                url = f"https://anonymouspwplayer-b99f57957198.herokuapp.com/pw?url={url}?token={raw_text4}"

            if ".pdf*" in url:
                url = f"https://dragoapi.vercel.app/pdf/{url}"
            
            elif 'encrypted.m' in url:
                appxkey = url.split('*')[1]
                url = url.split('*')[0]

            if "youtu" in url:
                ytf = f"bv*[height<={raw_text2}][ext=mp4]+ba[ext=m4a]/b[height<=?{raw_text2}]"
            elif "embed" in url:
                ytf = f"bestvideo[height<={raw_text2}]+bestaudio/best[height<={raw_text2}]"
            else:
                ytf = f"b[height<={raw_text2}]/bv[height<={raw_text2}]+ba/b/bv+ba"
           
            if "jw-prod" in url:
                cmd = f'yt-dlp -o "{name}.mp4" "{url}"'
            elif "webvideos.classplusapp." in url:
               cmd = f'yt-dlp --add-header "referer:https://web.classplusapp.com/" --add-header "x-cdn-tag:empty" -f "{ytf}" "{url}" -o "{name}.mp4"'
            elif "youtube.com" in url or "youtu.be" in url:
                cmd = f'yt-dlp --cookies youtube_cookies.txt -f "{ytf}" "{url}" -o "{name}".mp4'
            else:
                cmd = f'yt-dlp -f "{ytf}" "{url}" -o "{name}.mp4"'

            try:
                cc = f'🎞️𝐓𝐢𝐭𝐥𝐞 » `{name} [{res}].mp4`\n🔗𝐋𝐢𝐧𝐤 » <a href="{link}">__**CLICK HERE**__</a>\n\n🌟𝐄𝐱𝐭𝐫𝐚𝐜𝐭𝐞𝐝 𝐁𝐲 » `{CREDIT}`'
                cc1 = f'📕𝐓𝐢𝐭𝐥𝐞 » `{name}`\n🔗𝐋𝐢𝐧𝐤 » <a href="{link}">__**CLICK HERE**__</a>\n\n🌟𝐄𝐱𝐭𝐫𝐚𝐜𝐭𝐞𝐝 𝐁𝐲 » `{CREDIT}`'
                  
                if "drive" in url:
                    try:
                        ka = await helper.download(url, name)
                        copy = await bot.send_document(chat_id=m.chat.id,document=ka, caption=cc1)
                        count+=1
                        os.remove(ka)
                    except FloodWait as e:
                        await m.reply_text(str(e))
                        time.sleep(e.x)
                        pass

                elif ".pdf" in url:
                    if "cwmediabkt99" in url:
                        max_retries = 15  # Define the maximum number of retries
                        retry_delay = 4  # Delay between retries in seconds
                        success = False  # To track whether the download was successful
                        failure_msgs = []  # To keep track of failure messages
                        
                        for attempt in range(max_retries):
                            try:
                                await asyncio.sleep(retry_delay)
                                url = url.replace(" ", "%20")
                                scraper = cloudscraper.create_scraper()
                                response = scraper.get(url)

                                if response.status_code == 200:
                                    with open(f'{name}.pdf', 'wb') as file:
                                        file.write(response.content)
                                    await asyncio.sleep(retry_delay)  # Optional, to prevent spamming
                                    copy = await bot.send_document(chat_id=m.chat.id, document=f'{name}.pdf', caption=cc1)
                                    os.remove(f'{name}.pdf')
                                    success = True
                                    break  # Exit the retry loop if successful
                                else:
                                    failure_msg = await m.reply_text(f"Attempt {attempt + 1}/{max_retries} failed: {response.status_code} {response.reason}")
                                    failure_msgs.append(failure_msg)
                                    
                            except Exception as e:
                                failure_msg = await m.reply_text(f"Attempt {attempt + 1}/{max_retries} failed: {str(e)}")
                                failure_msgs.append(failure_msg)
                                await asyncio.sleep(retry_delay)
                                continue 

                        # Delete all failure messages if the PDF is successfully downloaded
                        for msg in failure_msgs:
                            await msg.delete()
                            
                        if not success:
                            # Final styled failure message if all retries fail
                            fail_caption = build_failed_caption_pdf(name1, count, b_name, topic, CR)
                            fail_buttons = build_failed_buttons(link0, kind="pdf")
                            await m.reply_text(
                                fail_caption,
                                disable_web_page_preview=True,
                                reply_markup=fail_buttons,
                            )
                    else:
                        try:
                            cmd = f'yt-dlp -o "{name}.pdf" "{url}"'
                            download_cmd = f"{cmd} -R 25 --fragment-retries 25"
                            os.system(download_cmd)
                            copy = await bot.send_document(chat_id=m.chat.id, document=f'{name}.pdf', caption=cc1)
                            os.remove(f'{name}.pdf')
                        except FloodWait as e:
                            await m.reply_text(str(e))
                            time.sleep(e.x)
                            pass   

                elif any(ext in url for ext in [".mp3", ".wav", ".m4a"]):
                    try:
                        ext = url.split('.')[-1]
                        cmd = f'yt-dlp -x --audio-format {ext} -o "{name}.{ext}" "{url}"'
                        download_cmd = f"{cmd} -R 25 --fragment-retries 25"
                        os.system(download_cmd)
                        await bot.send_document(chat_id=m.chat.id, document=f'{name}.{ext}', caption=cc1)
                        os.remove(f'{name}.{ext}')
                    except FloodWait as e:
                        await m.reply_text(str(e))
                        time.sleep(e.x)
                        pass

                elif any(ext in url for ext in [".jpg", ".jpeg", ".png"]):
                    try:
                        ext = url.split('.')[-1]
                        cmd = f'yt-dlp -o "{name}.{ext}" "{url}"'
                        download_cmd = f"{cmd} -R 25 --fragment-retries 25"
                        os.system(download_cmd)
                        copy = await bot.send_photo(chat_id=m.chat.id, photo=f'{name}.{ext}', caption=cc1)
                        count += 1
                        os.remove(f'{name}.{ext}')
                    except FloodWait as e:
                        await m.reply_text(str(e))
                        time.sleep(e.x)
                        pass
                                
                elif 'encrypted.m' in url:    
                    Show = f"**⚡Dᴏᴡɴʟᴏᴀᴅɪɴɢ Sᴛᴀʀᴛᴇᴅ...⏳**\n" \
                           f"🔗𝐋𝐢𝐧𝐤 » {url}\n" \
                           f"✦𝐁𝐨𝐭 𝐌𝐚𝐝𝐞 𝐁𝐲 ✦ {CREDIT}"
                    prog = await m.reply_text(Show, disable_web_page_preview=True)
                    res_file = await helper.download_and_decrypt_video(url, cmd, name, appxkey)  
                    filename = res_file  
                    await prog.delete(True)  
                    await helper.send_vid(bot, m, cc, filename, thumb, name, prog, channel_id)
                    await asyncio.sleep(1)  
                    pass

                elif 'drmcdni' in url or 'drm/wv' in url:
                    Show = f"**⚡Dᴏᴡɴʟᴏᴀᴅɪɴɢ Sᴛᴀʀᴛᴇᴅ...⏳**\n" \
                           f"🔗𝐋𝐢𝐧𝐤 » {url}\n" \
                           f"✦𝐁𝐨𝐭 𝐌𝐚𝐝𝐞 𝐁𝐲 ✦ {CREDIT}"
                    prog = await m.reply_text(Show, disable_web_page_preview=True)
                    res_file = await helper.decrypt_and_merge_video(mpd, keys_string, path, name, raw_text2)
                    filename = res_file
                    await prog.delete(True)
                    await helper.send_vid(bot, m, cc, filename, thumb, name, prog, channel_id)
                    await asyncio.sleep(1)
                    pass

                else:
                    Show = f"**⚡Dᴏᴡɴʟᴏᴀᴅɪɴɢ Sᴛᴀʀᴛᴇᴅ...⏳**\n" \
                           f"🔗𝐋𝐢𝐧𝐤 » {url}\n" \
                           f"✦𝐁𝐨𝐭 𝐌𝐚𝐝𝐞 𝐁𝐲 ✦ {CREDIT}"
                    prog = await m.reply_text(Show, disable_web_page_preview=True)
                    res_file = await helper.download_video(url, cmd, name)
                    filename = res_file
                    await prog.delete(True)
                    await helper.send_vid(bot, m, cc, filename, thumb, name, prog, channel_id)
                    time.sleep(1)
                
            except Exception as e:
                    await m.reply_text(f"⚠️𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐢𝐧𝐠 𝐈𝐧𝐭𝐞𝐫𝐮𝐩𝐭𝐞𝐝\n\n🔗𝐋𝐢𝐧𝐤 » `{link}`\n\n<blockquote><b><i>⚠️Failed Reason »**__\n{str(e)}</i></b></blockquote>")
                    pass

    except Exception as e:
        await m.reply_text(str(e))



# Add connection recovery mechanism
async def restart_on_error(client):
    while True:
        try:
            await client.start()
            print("✅ Bot Started Successfully!")

            # 🔔 Send animated boot message to owner + notify all auth users
            try:
                photo_url = "https://ibb.co/qYyTPTWJ"

                # STEP 1
                caption_step1 = (
                    "**🤖 Booting Systems (1/3)**\n\n"
                    "<pre><b>"
                    "⚙️ CORE      : STARTING\n"
                    "📡 DATABASE  : WAITING\n"
                    "🧰 MODULES   : IDLE\n"
                    "</b></pre>"
                )

                # STEP 2
                caption_step2 = (
                    "**🤖 Booting Systems (2/3)**\n\n"
                    "<pre><b>"
                    "⚙️ CORE      : STABLE\n"
                    "📡 DATABASE  : SYNCING…\n"
                    "🧰 MODULES   : LOADING…\n"
                    "</b></pre>"
                )

                # STEP 3
                caption_step3 = (
                    "**🤖 Booting Systems (3/3)**\n\n"
                    "<pre><b>"
                    "⚙️ CORE      : READY\n"
                    "📡 DATABASE  : SYNCED\n"
                    "🧰 MODULES   : ONLINE\n"
                    "</b></pre>"
                )

                # FINAL — OWNER
                final_caption_owner = (
                    "**🚀 Mrs.UC • Reboot Complete**\n\n"
                    "<pre><b>"
                    "👑 MODE      : OWNER\n"
                    "⚙️ CORE      : ONLINE\n"
                    "📡 DATABASE  : SYNCED\n"
                    "🧰 MODULES   : READY\n"
                    "</b></pre>\n"
                    "\n<b>■ Use /uc then send your .txt file.</b>"
                )

                # FINAL — AUTH USER
                final_caption_auth = (
                    "**Reboot Complete • You’re Ready**\n\n"
                    "<pre><b>"
                    "👤 MODE      : AUTH USER\n"
                    "⚙️ CORE      : ONLINE\n"
                    "📡 DATABASE  : SYNCED\n"
                    "🧰 MODULES   : READY\n"
                    "</b></pre>\n"
                    "\n<b>■ Use /uc then send your .txt file.</b>"
                )

                # Get all authorized users for this bot
                try:
                    users = db.list_users(client.me.username)
                except Exception as db_err:
                    print(f"Error fetching auth users for boot notify: {db_err}")
                    users = []

                target_ids = set()
                try:
                    if OWNER_ID:
                        target_ids.add(int(OWNER_ID))
                except Exception:
                    pass

                for u in users:
                    try:
                        uid = u.get("user_id")
                        if isinstance(uid, int):
                            target_ids.add(uid)
                    except Exception:
                        continue

                # Animated boot for owner
                if OWNER_ID in target_ids:
                    try:
                        msg = await client.send_photo(
                            OWNER_ID,
                            photo_url,
                            caption=caption_step1,
                        )
                        await asyncio.sleep(1.2)
                        await msg.edit_caption(caption_step2)
                        await asyncio.sleep(1.2)
                        await msg.edit_caption(caption_step3)
                        await asyncio.sleep(1.2)
                        await msg.edit_caption(final_caption_owner)
                    except Exception as e:
                        print(f"Failed to send owner reboot notification: {e}")
                    finally:
                        # avoid sending auth version to owner again
                        target_ids.discard(OWNER_ID)

                # Static boot info for all authorized users
                for uid in target_ids:
                    try:
                        await client.send_photo(
                            uid,
                            photo_url,
                            caption=final_caption_auth,
                        )
                        await asyncio.sleep(0.2)
                    except Exception as e:
                        print(f"Failed to send auth reboot notification to {uid}: {e}")

            except Exception as e:
                print(f"Boot notification error: {e}")

            await idle()

        except (AuthKeyUnregistered, SessionExpired, AuthKeyDuplicated) as e:
            print(f"⚠️ Session error: {str(e)}")
            print("🔄 Removing session and retrying in 5 seconds...")
            try:
                await client.stop()
                if os.path.exists("ug.session"):
                    os.remove("ug.session")
            except:
                pass
            await asyncio.sleep(5)

        except (BadRequest, Unauthorized) as e:
            print(f"⚠️ Connection error: {str(e)}")
            print("🔄 Retrying in 3 seconds...")
            try:
                await client.stop()
            except:
                pass
            await asyncio.sleep(3)

        except Exception as e:
            print(f"❌ Critical error: {str(e)}")
            print("🔄 Retrying in 5 seconds...")
            try:
                await client.stop()
            except:
                pass
            await asyncio.sleep(5)
# Add error handler for flood waits
@bot.on_message(filters.command(["start"]) & (filters.private | filters.channel))
async def start_handler(client, message):
    try:
        # Simple fallback start response (rarely used now that main /start is custom)
        await message.reply_text("Hello! Bot is running...")
    except FloodWait as e:
        print(f"FloodWait: sleeping for {e.value} seconds")
        await asyncio.sleep(e.value)
        await message.reply_text("Hello! Bot is running...")
    except Exception as e:
        print(f"Error in start handler: {str(e)}")
        await message.reply_text("An error occurred, please try again later.")
if __name__ == "__main__":
    print("Starting Bot...")
    while True:  # Keep trying to restart
        try:
            # Run the bot with the restart mechanism
            bot.run(restart_on_error(bot))
        except Exception as e:
            print(f"Failed to start bot: {str(e)}")
            # If bot fails to start, try to restart after delay
            time.sleep(10)
            # Try to stop the client if it's running
            try:
                bot.stop()
            except:
                pass
            continue  # Try again