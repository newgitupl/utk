from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
import pytz
from marco.authdb import get_auto_topic_settings, update_auto_topic_settings

# Constants
SETTINGS_IMAGE = "https://graph.org/file/6de54ed442030750a6295-a83c3e598c805ff2cb.jpg"


async def auto_topic_settings_menu(client, callback_query):
    """Show auto topic settings menu"""
    try:
        user_id = callback_query.from_user.id
        settings = get_auto_topic_settings(user_id)
        is_enabled = settings.get('enabled', False)
        

        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    f"Enable {' ✅' if is_enabled else ''}", 
                    callback_data="auto_topic_toggle_enable"
                ),
                InlineKeyboardButton(
                    f"Disable {' ✅' if not is_enabled else ''}", 
                    callback_data="auto_topic_toggle_disable"
                )
            ],
            [InlineKeyboardButton("🔙 Back", callback_data="back_to_st")]
        ])
        
        caption = (
            "**🔄 Auto Topic Uploader Settings**\n\n"
            f"Current Status: **{'Enabled ✅' if is_enabled else 'Disabled ❌'}**\n\n"
            "• Choose an option to enable or disable auto topic uploading.\n"
            "• When enabled, topics will be automatically uploaded.\n"
            "• When disabled, manual topic selection will be required.\n\n"
        )
        
        await callback_query.message.edit_media(
            media=InputMediaPhoto(
                media=SETTINGS_IMAGE,
                caption=caption
            ),
            reply_markup=keyboard
        )
    
    except Exception as e:
        print(f"Error in auto_topic_settings_menu: {str(e)}")
        await callback_query.answer("Error loading settings", show_alert=True)

async def toggle_auto_topic_status(client, callback_query):
    """Toggle auto topic status (enable/disable)"""
    try:
        user_id = callback_query.from_user.id
        action = callback_query.data.split("_")[-1]
        
        # Update settings in database
        new_settings = {"enabled": action == "enable"}
        update_auto_topic_settings(user_id, new_settings)
        
        # Show confirmation
        await callback_query.answer(
            f"Auto Topic Uploader {action}d successfully!", 
            show_alert=True
        )
        
        # Refresh menu
        await auto_topic_settings_menu(client, callback_query)
        
    except Exception as e:
        print(f"Error in toggle_auto_topic_status: {str(e)}")
        await callback_query.answer("Error updating settings", show_alert=True)

def is_auto_topic_enabled(user_id: int) -> bool:
    """Check if auto topic is enabled for user"""
    settings = get_auto_topic_settings(user_id)
    return settings.get('enabled', False)
  
