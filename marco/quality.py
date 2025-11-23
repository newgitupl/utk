from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from marco.authdb import get_user_quality, set_user_quality

QUALITY_LIST = [144, 240, 360, 480, 720, 1080]
DEFAULT_QUALITY = 480
SETTINGS_IMAGE = "https://envs.sh/T8Z.jpg"

def get_quality_keyboard(selected_quality):
    keys = []
    row = []
    for idx, q in enumerate(QUALITY_LIST):
        text = f"{q}✅" if q == selected_quality else str(q)
        row.append(InlineKeyboardButton(text, callback_data=f"set_quality_{q}"))
        if (idx + 1) % 2 == 0:
            keys.append(row)
            row = []
    if row:
        keys.append(row)
    keys.append([InlineKeyboardButton("⬅️ Back to Setting", callback_data="set_command")])
    return InlineKeyboardMarkup(keys)

async def quality_menu(client, callback_query):
    userid = callback_query.from_user.id
    quality = get_user_quality(userid)
    if quality is None:
        quality = DEFAULT_QUALITY
    keyboard = get_quality_keyboard(quality)
    caption = f"**Current Quality: {quality}**\n\nChoose Video Quality."
    await callback_query.message.edit_media(
        media=InputMediaPhoto(
            media=SETTINGS_IMAGE,
            caption=caption
        ),
        reply_markup=keyboard
    )

async def set_quality_callback(client, callback_query, quality):
    userid = callback_query.from_user.id
    set_user_quality(userid, int(quality))
    await quality_menu(client, callback_query)
