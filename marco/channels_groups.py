from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Message
from pyrogram.errors import MessageNotModified
from marco.authdb import add_allowed_cg, remove_allowed_cg, get_allowed_cg, is_authorized
import re
import asyncio

# Store active operations
active_operations = {}

def auth_check(user_id, owner_id):
    """Check if user is authorized or owner"""
    return is_authorized(user_id) or user_id == owner_id

async def cancel_operation(client: Client, callback_query: CallbackQuery, owner_id: int):
    """Handle cancel operation"""
    user_id = callback_query.from_user.id
    
    # Cancel any active operation for this user
    if user_id in active_operations:
        active_operations[user_id].set()
        active_operations.pop(user_id)
    
    try:
        await callback_query.answer("✅ Operation cancelled!", show_alert=True)
        await show_cg_menu(client, callback_query, owner_id)
    except MessageNotModified:
        pass

async def show_cg_menu(client: Client, callback_query: CallbackQuery, owner_id: int):
    """Show channels and groups menu"""
    user_id = callback_query.from_user.id
    
    # Clear any active operations for this user
    if user_id in active_operations:
        active_operations[user_id].set()
        active_operations.pop(user_id)
    
    if not auth_check(user_id, owner_id):
        await callback_query.answer("⚠️ Only authorized users can access this!", show_alert=True)
        return

    allowed_cg = get_allowed_cg(user_id)
    
    text = "**📢 Allowed Channels & Groups:**\n\n"
    for chat_id in allowed_cg:
        try:
            chat = await client.get_chat(chat_id)
            chat_type = "📢 Channel" if chat.type == "channel" else "👥 Group"
            username = f"@{chat.username}" if chat.username else "Private Chat"
            text += f"{chat_type}: {chat.title}\n💠 ID: `{chat_id}`\n🔗 {username}\n\n"
        except:
            text += f"❌ Unknown Chat\n💠 ID: `{chat_id}`\n\n"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add", callback_data="add_cg"),
         InlineKeyboardButton("➖ Remove", callback_data="remove_cg")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_main_menu")]
    ])

    try:
        await callback_query.message.edit_media(
            InputMediaPhoto(
                media="https://i.ibb.co/N6Xxd8b5/temp.jpg",
                caption=text
            ),
            reply_markup=keyboard
        )
    except MessageNotModified:
        pass
    except Exception as e:
        print(f"Error in show_cg_menu: {str(e)}")

async def handle_add_cg(client: Client, callback_query: CallbackQuery, owner_id: int):
    """Handle adding channel/group"""
    user_id = callback_query.from_user.id
    
    if not auth_check(user_id, owner_id):
        await callback_query.answer("⚠️ Only authorized users can access this!", show_alert=True)
        return

    # Create cancel event for this user
    cancel_event = asyncio.Event()
    active_operations[user_id] = cancel_event

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Process", callback_data="cancel_cg")],
        [InlineKeyboardButton("🔙 Back", callback_data="channels_groups_command")]
    ])

    try:
        await callback_query.message.edit_text(
            "**Send Channel/Group ID or Username:**\n\n"
            "✅ Accepted formats:\n"
            "• Channel/Group ID (`-100xxxxxxxxxx`)\n"
            "• Username (`@username`)\n"
            "• Public link (`t.me/username`)\n"
            "• Private link (`t.me/c/xxxxxxxxxx`)\n\n"
            "⚠️ Bot must be member of the Channel/Group\n"
            "📝 Click Cancel to abort",
            reply_markup=keyboard
        )
    except MessageNotModified:
        pass

    try:
        # Wait for user input or cancel
        task = client.listen(callback_query.message.chat.id, filters=~filters.regex("^/"))
        msg = await asyncio.wait_for(task, timeout=60)
        
        # Check if operation was cancelled
        if cancel_event.is_set():
            return
        
        if msg.text:
            if msg.text.startswith('/'):
                await callback_query.message.reply_text("❌ Operation cancelled due to command.")
                return
                
            chat_id = None
            chat = None
            
            # Direct ID format
            if msg.text.startswith('-100'):
                try:
                    chat_id = int(msg.text)
                    chat = await client.get_chat(chat_id)
                except:
                    pass
                    
            # Username format
            elif msg.text.startswith('@'):
                try:
                    chat = await client.get_chat(msg.text)
                    chat_id = chat.id
                except:
                    pass
                    
            # t.me link formats
            elif 't.me/' in msg.text:
                if 't.me/c/' in msg.text:
                    try:
                        chat_id = int(f"-100{msg.text.split('t.me/c/')[1].split('/')[0]}")
                        chat = await client.get_chat(chat_id)
                    except:
                        pass
                else:
                    try:
                        username = msg.text.split('t.me/')[1].split('/')[0]
                        chat = await client.get_chat(username)
                        chat_id = chat.id
                    except:
                        pass
            
            if not chat_id or not chat:
                await callback_query.message.reply_text(
                    "❌ Invalid input! Make sure:\n"
                    "• Input format is correct\n"
                    "• Bot is member of the Channel/Group\n"
                    "• Channel/Group exists"
                )
            else:
                add_allowed_cg(user_id, chat_id)
                chat_type = "Channel" if chat.type == "channel" else "Group"
                await callback_query.message.reply_text(
                    f"✅ Successfully added {chat_type}!\n\n"
                    f"📝 Name: {chat.title}\n"
                    f"🆔 ID: `{chat_id}`\n"
                    f"🔗 Link: {f'@{chat.username}' if chat.username else 'Private Chat'}"
                )
    except asyncio.TimeoutError:
        if not cancel_event.is_set():
            await callback_query.message.reply_text("⏳ Timeout! Operation cancelled.")
    except Exception as e:
        if not cancel_event.is_set():
            await callback_query.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        # Clean up
        if user_id in active_operations:
            active_operations.pop(user_id)
        await show_cg_menu(client, callback_query, owner_id)

async def handle_remove_cg(client: Client, callback_query: CallbackQuery, owner_id: int):
    """Handle removing channel/group"""
    user_id = callback_query.from_user.id
    
    if not auth_check(user_id, owner_id):
        await callback_query.answer("⚠️ Only authorized users can access this!", show_alert=True)
        return

    # Create cancel event for this user
    cancel_event = asyncio.Event()
    active_operations[user_id] = cancel_event

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel Process", callback_data="cancel_cg")],
        [InlineKeyboardButton("🔙 Back", callback_data="channels_groups_command")]
    ])

    try:
        await callback_query.message.edit_text(
            "**Send Channel/Group ID to remove:**\n\n"
            "• Copy ID from the list above\n"
            "• ID format: `-100xxxxxxxxxx`\n"
            "📝 Click Cancel to abort",
            reply_markup=keyboard
        )
    except MessageNotModified:
        pass

    try:
        # Wait for user input or cancel
        task = client.listen(callback_query.message.chat.id, filters=~filters.regex("^/"))
        msg = await asyncio.wait_for(task, timeout=60)
        
        # Check if operation was cancelled
        if cancel_event.is_set():
            return
        
        if msg.text:
            if msg.text.startswith('/'):
                await callback_query.message.reply_text("❌ Operation cancelled due to command.")
                return
                
            if msg.text.strip().startswith('-100'):
                chat_id = int(msg.text.strip())
                remove_allowed_cg(user_id, chat_id)
                await callback_query.message.reply_text("✅ Successfully removed!")
            else:
                await callback_query.message.reply_text("❌ Invalid ID format!")
    except asyncio.TimeoutError:
        if not cancel_event.is_set():
            await callback_query.message.reply_text("⏳ Timeout! Operation cancelled.")
    except Exception as e:
        if not cancel_event.is_set():
            await callback_query.message.reply_text(f"❌ Error: {str(e)}")
    finally:
        # Clean up
        if user_id in active_operations:
            active_operations.pop(user_id)
        await show_cg_menu(client, callback_query, owner_id)
