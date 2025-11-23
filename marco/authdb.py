
from pymongo import MongoClient
import os
from datetime import datetime

client = MongoClient("mongodb+srv://BUDDY:p61DXx3AIPnrww0o@cluster0.7uw5gfn.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["Buddy"]
users = db["users"]

def add_or_update_user(userid: int, start_date: datetime, expire_date: datetime):
    users.update_one(
        {"userid": userid},
        {"$set": {"start_date": start_date, "expire_date": expire_date}},
        upsert=True
    )

def remove_user(userid: int):
    users.delete_one({"userid": userid})

def is_authorized(userid: int) -> bool:
    user = users.find_one({"userid": userid})
    if user and user.get("expire_date") and user["expire_date"] > datetime.now():
        return True
    return False

def cleanup_expired_users():
    users.delete_many({"expire_date": {"$lte": datetime.now()}})
    
def get_all_users():
    return list(users.find({}))

def get_user(userid: int):
    return users.find_one({"userid": userid})

# Default Name & Extension Name:

def set_default_name(userid: int, default_name: str):
    users.update_one(
        {"userid": userid},
        {"$set": {"default_name": default_name}},
        upsert=True
    )

def get_default_name(userid: int):
    user = users.find_one({"userid": userid})
    return user.get("default_name", None) if user else None

def remove_default_name(userid):  # ✅ Single parameter (no change needed)
    users.update_one(
        {'userid': userid},
        {'$unset': {'default_name': ""}},
        upsert=True
    )



def set_extension_name(userid: int, extension_name: str):
    users.update_one(
        {"userid": userid},
        {"$set": {"extension_name": extension_name}},
        upsert=True
    )

def get_extension_name(userid: int):
    user = users.find_one({"userid": userid})
    return user.get("extension_name", None) if user else None

def set_caption_style(userid: int, style: str):
    users.update_one(
        {"userid": userid},
        {"$set": {"caption_style": style}},
        upsert=True
    )

def get_caption_style(userid: int):
    user = users.find_one({"userid": userid})
    return user.get("caption_style", None) if user else None

# Quality Functions

def set_user_quality(userid: int, quality: int):
    users.update_one(
        {"userid": userid},
        {"$set": {"quality": quality}},
        upsert=True
    )

def get_user_quality(userid: int):
    user = users.find_one({"userid": userid})
    return user.get("quality", None) if user else None

# Thumbnail Functions
# Thumbnail Functions

def set_thumbnail(userid: int, thumb_url: str, thumb_type: str):
    """
    Set thumbnail URL for a user
    thumb_type: 'video' or 'pdf'
    """
    users.update_one(
        {"userid": userid},
        {"$set": {f"{thumb_type}_thumbnail": thumb_url}},
        upsert=True
    )

def get_thumbnail(userid: int, thumb_type: str):
    """
    Get thumbnail URL for a user
    thumb_type: 'video' or 'pdf'
    Returns None if no thumbnail set
    """
    user = users.find_one({"userid": userid})
    return user.get(f"{thumb_type}_thumbnail", None) if user else None

def remove_thumbnail(userid: int, thumb_type: str):
    """Remove thumbnail setting"""
    users.update_one(
        {"userid": userid},
        {"$unset": {f"{thumb_type}_thumbnail": ""}}
    )
# Watermark Color Functions

def get_watermark_settings(userid: int):
    user = users.find_one({"userid": userid})
    default_settings = {
        "text": "MARCO",
        "color": "white",
        "font": "DejaVuSans-Bold.ttf",
        "opacity": 0.8,
        "enabled": True
    }
    return user.get("watermark_settings", default_settings) if user else default_settings
    
def update_watermark_settings(userid: int, new_settings: dict):
    current = get_watermark_settings(userid)
    current.update(new_settings)
    users.update_one(
        {"userid": userid},
        {"$set": {"watermark_settings": current}},
        upsert=True
    )

# Allowed Channels & Groups

def add_allowed_cg(userid: int, chat_id: int):
    """Add channel or group ID to user's allowed list"""
    users.update_one(
        {"userid": userid},
        {"$addToSet": {"allowed_cg": chat_id}},
        upsert=True
    )

def remove_allowed_cg(userid: int, chat_id: int):
    """Remove channel or group ID from user's allowed list"""
    users.update_one(
        {"userid": userid},
        {"$pull": {"allowed_cg": chat_id}}
    )

def get_allowed_cg(userid: int):
    """Get list of allowed channels and groups"""
    user = users.find_one({"userid": userid})
    return user.get("allowed_cg", []) if user else []

# Add these functions in marco/authdb.py

def get_auto_topic_settings(userid: int):
    """Get auto topic settings for a user"""
    user = users.find_one({"userid": userid})
    default_settings = {
        "enabled": False  # Default is disabled
    }
    return user.get("auto_topic_settings", default_settings) if user else default_settings
    
def update_auto_topic_settings(userid: int, new_settings: dict):
    """Update auto topic settings for a user"""
    current = get_auto_topic_settings(userid)
    current.update(new_settings)
    users.update_one(
        {"userid": userid},
        {"$set": {"auto_topic_settings": current}},
        upsert=True
    )
    return current

# ---------------- UC Command Auth Helper ----------------
async def uc_command(client: Client, message: Message) -> bool:
    """Handle /uc auth with admin+DB checks.

    Rules:
    - PRIVATE: user must be authorized
    - GROUP / SUPERGROUP / FORUM / CHANNEL:
        ✅ Allowed if:
          (A) chat is authorized in DB (is_channel_authorized)
              OR
          (B) any human admin of that chat is an authorized user
    """
    try:
        user = message.from_user
        user_id = user.id if user else None

        bot = await client.get_me()
        bot_username = bot.username

        chat = message.chat
        chat_type = chat.type
        chat_id = chat.id

        print(f"📥 /uc received - user={user_id}, chat={chat_id}, type={chat_type}")

        chat_type_str = str(chat_type).lower()

        # 1️⃣ PRIVATE: simple user auth
        if "private" in chat_type_str:
            if user_id and db.is_user_authorized(user_id, bot_username):
                return True
            else:
                await message.reply_text("❌ You are not authorized. Contact admin to get access.")
                return False

        # 2️⃣ GROUP / SUPERGROUP / FORUM / CHANNEL: shared logic
        if any(t in chat_type_str for t in ("group", "forum", "channel")):
            # (A) DB-level chat auth (optional)
            try:
                if hasattr(db, "is_channel_authorized") and db.is_channel_authorized(chat_id, bot_username):
                    print(f"✅ Chat authorized for /uc via DB: {chat_id}")
                    return True
            except Exception as e:
                print(f"Error in is_channel_authorized: {str(e)}")

            # (B) Telegram admins-based auth
            try:
                admin_ids = []
                async for member in client.get_chat_members(chat_id, filter=ChatMembersFilter.ADMINISTRATORS):
                    u = getattr(member, "user", None)
                    if u and not u.is_bot:
                        admin_ids.append(u.id)

                print(f"📢 Chat admins: {admin_ids}")

                for admin_id in admin_ids:
                    try:
                        if db.is_user_authorized(admin_id, bot_username):
                            print(f"✅ Authorized admin found for chat: {admin_id}")
                            return True
                    except Exception as e:
                        print(f"Error checking admin {admin_id} auth: {str(e)}")

                print("❌ No authorized chat or admin found for /uc")

                # For channels: stay silent (can't always reply)
                if "channel" in chat_type_str:
                    return False

                # For groups / forums: tell them
                await message.reply_text(
                    "❌ No authorized admin found in this chat.\n\n"
                    "At least one admin must have an active subscription."
                )
                return False

            except Exception as e:
                print(f"Error fetching chat admins: {str(e)}")
                return False

        # 3️⃣ Any other chat type: unsupported
        print(f"❌ Unsupported chat type for /uc: {chat_type}")
        return False

    except Exception as e:
        print(f"❌ Error in uc_command: {str(e)}")
        try:
            await message.reply_text("❌ An error occurred. Please try again.")
        except Exception:
            pass
        return False
