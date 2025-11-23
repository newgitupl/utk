from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto

# Image file ka path ya URL (server pe ho to path, online ho to direct URL)
PLANS_IMAGE_PATH = "plans.jpg"  # ya apka image ka URL

PLANS_CAPTION = """
<b>Here are the pricing details for my NON-DRM Bots :</b>

<b>🗓️ Subscription Duration :</b> 30 Days

<b>📦 Pricing Packages :</b>
• <b>1 Bot:</b> ₹200 💰
• <b>2 Bots:</b> ₹400 💸
• <b>3 Bots:</b> ₹1200 💵

<b>🌟 Note :</b> If you purchase a single bot, the price will be higher.

<b>🗂 Supported Apps and Links:</b>

<blockquote expandable>
✅ All Appx m3u8 and mp4 links
✅ Appx Encrypted Videos + PDFs [mkv*13433, mp4*54225, pdf*MKjdc...]
✅ Some Special App Video + PDF (Expired Also)
✅ Physics Wallah [ID*Pass]
✅ Sherwill [NON DRM/DRM]✓
✅ Khan Sir 
✅ YouTube Links (cookies your) 
✅ KD CAMPUS
✅ Classplus (NON/DRM)
✅ Other Non-Drm and Non-Encrypted Links
</blockquote>
🚀 Unlock premium features and save with our flexible plans ! 🚀

<b>Register Your Bots Now :</b> <a href='https://t.me/DMAAWARABOT'>—͟͟͞͞ ɅɅWΛRΛ</a>
"""

plans_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="back_to_main_menu")]
])

async def plans_command_handler(client, callback_query):
    await callback_query.message.edit_media(
        media=InputMediaPhoto(PLANS_IMAGE_PATH, caption=PLANS_CAPTION),
        reply_markup=plans_keyboard
    )

# Back button handler (example, apne hisab se import ya logic laga lo)
async def back_to_main_menu_handler(client, callback_query):
    # Yahan aapka main menu function call karein
    await send_main_menu_ui(client, callback_query)
