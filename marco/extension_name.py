from marco.authdb import set_extension_name, get_extension_name
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
import asyncio

# User cancel flags (user_id: bool)
user_cancel_flags = {}

async def extension_name_flow(client, callback_query):
    userid = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    user_cancel_flags[userid] = False  # Reset cancel flag

    existing_name = get_extension_name(userid) or ""
    photo_url = "https://envs.sh/T8Z.jpg"

    back_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Setting", callback_data="set_command")]
    ])

    await callback_query.message.edit_media(
        media=InputMediaPhoto(
            media=photo_url,
            caption=(
                f"📎 Your Extension Name: `{existing_name}`\n\n"
                "Please send a new Extension Name:\n\n"
                "_Or click 'Back to Setting'_"
            )
        ),
        reply_markup=back_keyboard
    )

    try:
        input_msg = await client.listen(chat_id, timeout=60)
    except asyncio.TimeoutError:
        await callback_query.message.reply_text("⏰ Timeout! Please try again.")
        user_cancel_flags.pop(userid, None)
        return

    # Cancel if user pressed the back button while waiting
    if user_cancel_flags.get(userid):
        await input_msg.delete()
        user_cancel_flags.pop(userid, None)
        return

    # Cancel if user sends 'back' or '🔙'
    if input_msg.text and input_msg.text.lower() in ["back", "🔙"]:
        await callback_query.message.reply_text("❌ Cancelled. Back to settings.")
        await input_msg.delete()
        user_cancel_flags.pop(userid, None)
        return

    new_extension_name = input_msg.text.strip()
    set_extension_name(userid, new_extension_name)

    await callback_query.message.edit_media(
        media=InputMediaPhoto(
            media=photo_url,
            caption=f"✅ Your **Extension Name** has been updated to:\n\n`{new_extension_name}`"
        ),
        reply_markup=back_keyboard
    )
    await input_msg.delete()
    user_cancel_flags.pop(userid, None)
