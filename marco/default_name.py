from marco.authdb import set_default_name, get_default_name, remove_default_name
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

async def default_name_menu(client, callback_query):
    await callback_query.answer()  # ✅ Required to prevent stale callback issue
    
    userid = callback_query.from_user.id
    default_name = get_default_name(userid)
    if not default_name:
        default_name = "None"
    caption = f"Your Default Name : {default_name}"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✍️ Change Name", callback_data="change_default_name")],
        [InlineKeyboardButton("🗑️ Remove Name", callback_data="remove_default_name")],
        [InlineKeyboardButton("🔙 Back to Setting", callback_data="set_command")]
    ])
    await callback_query.message.edit_caption(caption, reply_markup=keyboard)

async def change_default_name(client, callback_query):
    await callback_query.answer()  # ✅ Required to prevent stale callback issue
    
    userid = callback_query.from_user.id
    msg = await callback_query.message.reply_text("📝 Send me the new Default Name you want to set :")
    input_msg = await client.listen(callback_query.message.chat.id)
    await msg.delete()
    await input_msg.delete()
    new_name = input_msg.text
    set_default_name(userid, new_name)
    await callback_query.message.reply_text("✅ Your Default Name has been Updated Successfully!")
    await default_name_menu(client, callback_query)  # Return to the menu

async def remove_default_name(client, callback_query):
    userid = callback_query.from_user.id  # ✅ User ID extract karo
    remove_default_name(userid)  # ✅ Sirf `userid` pass karo
    await callback_query.answer("✅ Default name removed!")
    await default_name_menu(client, callback_query)  # Menu pe wapas jao
