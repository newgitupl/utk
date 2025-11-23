from pyrogram import Client
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from marco.authdb import is_authorized, get_thumbnail, set_thumbnail, remove_thumbnail
import logging

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default Images (replace with your working image URLs)
MAIN_MENU_IMAGE = "https://images.pexels.com/photos/546819/pexels-photo-546819.jpeg"
DEFAULT_THUMB = "https://images.pexels.com/photos/943096/pexels-photo-943096.jpeg"

async def send_menu_message(callback_query: CallbackQuery, photo: str, caption: str, keyboard: InlineKeyboardMarkup):
    """Utility function to send/edit menu messages"""
    try:
        await callback_query.message.edit_media(
            media=InputMediaPhoto(media=photo, caption=caption),
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error in send_menu_message: {str(e)}")
        try:
            await callback_query.message.reply_photo(
                photo=photo,
                caption=caption,
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Fallback also failed: {str(e)}")
            await callback_query.answer("Failed to update menu. Please try again.", show_alert=True)

async def thumbnail_menu(_, callback_query: CallbackQuery):
    """Main thumbnail settings menu"""
    if not is_authorized(callback_query.from_user.id):
        await callback_query.answer("You are not authorized!", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📽️ Video Thumbnail", callback_data="video_thumb_settings"),
            InlineKeyboardButton("📄 PDF Thumbnail", callback_data="pdf_thumb_settings")
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="set_command")]
    ])

    await send_menu_message(
        callback_query=callback_query,
        photo=MAIN_MENU_IMAGE,
        caption="**Thumbnail Settings**\n\nChoose which thumbnail you want to configure:",
        keyboard=keyboard
    )

async def thumb_type_menu(_, callback_query: CallbackQuery, thumb_type: str):
    """Show thumbnail type specific menu"""
    if not is_authorized(callback_query.from_user.id):
        await callback_query.answer("You are not authorized!", show_alert=True)
        return

    user_id = callback_query.from_user.id
    current_thumb = get_thumbnail(user_id, thumb_type)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Change Thumbnail", callback_data=f"change_{thumb_type}_thumb")],
        [InlineKeyboardButton("❌ Remove Thumbnail", callback_data=f"remove_{thumb_type}_thumb")],
        [InlineKeyboardButton("⬅️ Back", callback_data="thumb_command")]
    ])

    # Use current thumbnail if set, otherwise use default
    thumb_url = current_thumb if current_thumb else DEFAULT_THUMB
    caption = (
        f"**{thumb_type.upper()} THUMBNAIL**\n\n"
        f"Status: {'Set ✅' if current_thumb else 'Not Set ❌'}\n\n"
        "Choose an option:"
    )

    await send_menu_message(
        callback_query=callback_query,
        photo=thumb_url,
        caption=caption,
        keyboard=keyboard
    )

async def change_thumbnail(_, callback_query: CallbackQuery, thumb_type: str):
    """Show thumbnail change menu"""
    if not is_authorized(callback_query.from_user.id):
        await callback_query.answer("You are not authorized!", show_alert=True)
        return

    user_id = callback_query.from_user.id
    current_thumb = get_thumbnail(user_id, thumb_type)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back", callback_data=f"{thumb_type}_thumb_settings")]
    ])

    caption = (
        f"**SET {thumb_type.upper()} THUMBNAIL**\n\n"
        "Send me the thumbnail:\n"
        "• Send photo directly\n"
        "• Send image URL\n"
        "• Send /d to remove"
    )

    # Use current thumbnail if set, otherwise use default
    thumb_url = current_thumb if current_thumb else DEFAULT_THUMB
    
    await send_menu_message(
        callback_query=callback_query,
        photo=thumb_url,
        caption=caption,
        keyboard=keyboard
    )

async def handle_thumb_input(client: Client, message: Message, thumb_type: str):
    """Handle thumbnail input from user"""
    if not is_authorized(message.from_user.id):
        return

    user_id = message.from_user.id

    try:
        if message.text and message.text.lower() == "/d":
            remove_thumbnail(user_id, thumb_type)
            await message.reply_text(f"{thumb_type.title()} thumbnail removed ✅")
            return

        if message.photo:
            try:
                # Get photo file_id directly from message
                file_id = message.photo.file_id if hasattr(message.photo, 'file_id') else message.photo[-1].file_id
                
                # Save file_id as thumbnail
                set_thumbnail(user_id, file_id, thumb_type)
                await message.reply_text(f"{thumb_type.title()} thumbnail updated successfully ✅")
                
            except Exception as e:
                logger.error(f"Error processing photo: {str(e)}")
                await message.reply_text("❌ Failed to process photo. Please try again!")
            
        elif message.text and message.text.startswith(("http://", "https://")):
            thumb_url = message.text
            set_thumbnail(user_id, thumb_url, thumb_type)
            await message.reply_text(f"{thumb_type.title()} thumbnail updated successfully ✅")
            
        else:
            await message.reply_text("❌ Please send a valid image or URL!")

    except Exception as e:
        logger.error(f"Error in handle_thumb_input: {str(e)}")
        await message.reply_text("❌ Failed to update thumbnail. Please try again!")
                                    
