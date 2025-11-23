from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from marco.authdb import get_caption_style, set_caption_style

CAPTIONS = {
    "default": "**——— ✦ 001 ✦ ———**\n\n**🎥 Title :** `New Topic GK 2025`\n├── **Extension** : —͟͟͞͞ ɅɅWΛRΛ.mkv\n├── **Resolution** : [1280x720]\n**📒 Course :** New Update GK\n\n**🌟 Extracted By : —͟͟͞͞ ɅɅWΛRΛ**",
    "cap1": "╭━━━━━━━━━━━╮\n🎥 VIDEO ID : 003\n╰━━━━━━━━━━━╯\n\n📄 **Title** : English foundation batch.mkv\n\n📒 **Batch Name** : **English foundation's**\n\n🌟 **Extracted By** : —͟͟͞͞ ɅɅWΛRΛ\n\n",
    "cap2": "**🎥 VIDEO ID : **001 \n\n**Video Title :** New Topic GK 2025 \n\n<blockquote><b>📒 Batch Name :</b> NEW GK TOPIC 2025 </blockquote>\n\n**🌟 Extracted by ➤** —͟͟͞͞ ɅɅWΛRΛ\n",
    "cap3": "📝 Notes: Important Chapter\n✔️ Completed: Yes",
    "cap4": "📝 Notes: Important Chapter\n✔️ Completed: Yes"
}

async def caption_menu(client, callback_query):
    await callback_query.answer()
    userid = callback_query.from_user.id
    current_style = get_caption_style(userid) or "default"

    caption = f"*Current Caption Styling :* `{current_style}`\n\n{CAPTIONS[current_style]}\n\nYou can Choose anyone from these."

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Default" + (" ✅" if current_style == "default" else ""), callback_data="set_caption_default")],
        [InlineKeyboardButton("Caption 1" + (" ✅" if current_style == "cap1" else ""), callback_data="set_caption_cap1"),
         InlineKeyboardButton("Caption 2" + (" ✅" if current_style == "cap2" else ""), callback_data="set_caption_cap2")],
        [InlineKeyboardButton("Caption 3" + (" ✅" if current_style == "cap3" else ""), callback_data="set_caption_cap3"),
         InlineKeyboardButton("Caption 4" + (" ✅" if current_style == "cap4" else ""), callback_data="set_caption_cap4")],
        [InlineKeyboardButton("Caption 5" + (" ✅" if current_style == "cap5" else ""), callback_data="set_caption_cap5")],
        [InlineKeyboardButton("🔙 Back", callback_data="set_command")]
    ])

    await callback_query.message.edit_media(
        InputMediaPhoto(
            media="https://envs.sh/T8Z.jpg",
            caption=caption
        ),
        reply_markup=keyboard
    )

async def set_caption_style_callback(client, callback_query, style):
    await callback_query.answer()
    userid = callback_query.from_user.id
    set_caption_style(userid, style)
    await caption_menu(client, callback_query)
