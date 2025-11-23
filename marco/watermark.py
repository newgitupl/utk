from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from marco.authdb import is_authorized, get_watermark_settings, update_watermark_settings
import os
from PIL import Image, ImageDraw, ImageFont
import tempfile
from datetime import datetime
import pytz

# Track active processes - Using simple dict instead of typing.Dict
active_processes = {}

# Get the absolute path to the marco directory
MARCO_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_IMAGE = os.path.join(MARCO_DIR, "settings.jpg")

# Add at the top with other constants
MIN_FONT_SIZE = 50
MAX_FONT_SIZE = 200

# Color options with emojis
COLORS = {
    "Black": "🖤",
    "White": "🤍", 
    "Red": "❤️",
    "Blue": "💙",
    "Green": "💚",
    "Golden": "💛"
}

# Status emojis
STATUS_EMOJI = {
    True: "✅",
    False: "❌" 
}

def start_process(user_id: int, process_type: str):
    """Start a process for user"""
    if user_id not in active_processes:
        active_processes[user_id] = {}
    active_processes[user_id][process_type] = True

def end_process(user_id: int, process_type: str):
    """End a process for user"""
    if user_id in active_processes and process_type in active_processes[user_id]:
        active_processes[user_id][process_type] = False

def is_process_active(user_id: int, process_type: str) -> bool:
    """Check if process is active"""
    return active_processes.get(user_id, {}).get(process_type, False)

def get_formatted_datetime():
    """Get current UTC datetime formatted"""
    utc_now = datetime.now(pytz.UTC)
    formatted_datetime = utc_now.strftime("%Y-%m-%d %H:%M:%S")
    return formatted_datetime

def get_user_login():
    """Get current user login"""
    return "mjxmeenaji"
        
async def watermark_settings(_, callback_query: CallbackQuery):
    if not is_authorized(callback_query.from_user.id):
        await callback_query.answer("You are not authorized!", show_alert=True)
        return

    user_id = callback_query.from_user.id
    settings = get_watermark_settings(user_id)
    
    # Get current settings
    current_text = settings.get('text', 'MARCO')
    current_color = settings.get('color', 'white')
    current_font = settings.get('font', 'DejaVuSans-Bold.ttf').split('.')[0]
    current_fontsize = settings.get('font_size', 80)
    current_opacity = settings.get('opacity', 0.8)
    is_enabled = settings.get('enabled', True)

    text = (
        "**Your Current Overlay Details:**\n\n"
        f"✒️ Overlay Text: {current_text}\n"
        f"🎨 Text Colour: {current_color}\n"
        f"📝 Font Style: {current_font}\n"
        f"📐 Font Size: {current_fontsize}\n"
        f"💧 Opacity: {current_opacity}\n"
        f"⚡️ Status: {STATUS_EMOJI[is_enabled]} {'Enabled' if is_enabled else 'Disabled'}\n\n"
        "**Choose the Text WaterMark Settings Preference**"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Change Text", callback_data="change_wm_text"),
         InlineKeyboardButton("🎨 Change Colour", callback_data="change_wm_color")],
        [InlineKeyboardButton("📝 Change Font", callback_data="change_wm_font"),
         InlineKeyboardButton("💧 Change Opacity", callback_data="change_wm_opacity")],
        [InlineKeyboardButton("📏 Change Font Size", callback_data="change_wm_size"),
        InlineKeyboardButton(
            f"{'Disable' if is_enabled else 'Enable'} Watermark {STATUS_EMOJI[is_enabled]}", 
            callback_data="toggle_watermark"
        )],
        [InlineKeyboardButton("↩️ Back to Setting", callback_data="back_to_st")]
    ])

    try:
        # Check if SETTINGS_IMAGE exists, else fallback to online image
        img = SETTINGS_IMAGE if os.path.exists(SETTINGS_IMAGE) else DEFAULT_SETTINGS_IMAGE

        await callback_query.message.edit_media(
            media=InputMediaPhoto(
                media=img,
                caption=text
            ),
            reply_markup=keyboard
        )
    except Exception as e:
        print(f"Error in watermark_settings: {str(e)}")
        # Fallback: Show text-only message if image fails
        await callback_query.message.edit_text(
            text=text,
            reply_markup=keyboard
        )

async def change_watermark_text(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    start_process(user_id, "text")
    
    try:
        await callback_query.message.edit_media(
            media=InputMediaPhoto(
                media=SETTINGS_IMAGE,
                caption="**Send me the new watermark text:**\n• Send /cancel to cancel"
            ),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔙 Back", callback_data="watermark_marco"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel_wm_text")
                ]
            ])
        )

        try:
            response = await client.listen(user_id, timeout=30)
            
            if not is_process_active(user_id, "text"):
                return
            
            if response.text == "/cancel":
                await callback_query.message.edit_caption("Process cancelled!")
                await watermark_settings(client, callback_query)
                return
            
            update_watermark_settings(user_id, {"text": response.text})
            await callback_query.message.edit_caption(f"✅ Watermark text updated to: **{response.text}**")
            await watermark_settings(client, callback_query)
            
        except asyncio.TimeoutError:
            if is_process_active(user_id, "text"):
                await callback_query.message.edit_text("❌ Process timed out. Please try again.")
                await callback_query.answer(f"Please Try Again.🔁")
                await watermark_settings(client, callback_query)
        except asyncio.CancelledError:
            if is_process_active(user_id, "text"):
                await callback_query.message.edit_text("❌ Process cancelled.")
                await callback_query.answer(f"Please Try Again.🔁")
                await watermark_settings(client, callback_query)
            
    except Exception as e:
        print(f"Error in change_watermark_text: {str(e)}")
        await callback_query.message.edit_caption("❌ An error occurred. Please try again.")
        await callback_query.answer(f"Please Try Again.🔁")
        await watermark_settings(client, callback_query)
    finally:
        end_process(user_id, "text")

async def change_watermark_opacity(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    start_process(user_id, "opacity")
    
    try:
        await callback_query.message.edit_media(
            media=InputMediaPhoto(
                media=SETTINGS_IMAGE,
                caption=(
                    "**Send me the new opacity value:**\n\n"
                    "• Value should be between 0.1 and 1.0\n"
                    "• Format: Use decimal (e.g., 0.8)\n"
                    "• Example: 0.7 for 70% opacity\n\n"
                    "Send /cancel to cancel"
                )
            ),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔙 Back", callback_data="watermark_marco"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel_wm_opacity")
                ]
            ])
        )

        try:
            response = await client.listen(user_id, timeout=30)
            
            if not is_process_active(user_id, "opacity"):
                return
                
            if response.text == "/cancel":
                await callback_query.message.edit_caption("Process cancelled!")
                await watermark_settings(client, callback_query)
                return

            try:
                opacity = float(response.text)
                if 0.1 <= opacity <= 1.0:
                    update_watermark_settings(user_id, {"opacity": opacity})
                    await callback_query.message.edit_caption(f"✅ Opacity updated to: **{opacity}**")
                    await watermark_settings(client, callback_query)
                else:
                    await callback_query.message.edit_caption(
                        "❌ Invalid value! Opacity must be between 0.1 and 1.0"
                    )
                    await callback_query.answer(f"Please Try Again.🔁")
                    await watermark_settings(client, callback_query)
                
            except ValueError:
                await callback_query.message.edit_caption(
                    "❌ Invalid format! Please send a decimal number"
                )
                await callback_query.answer(f"Please Try Again.🔁")
                await watermark_settings(client, callback_query)
                
        except asyncio.TimeoutError:
            if is_process_active(user_id, "opacity"):
                await callback_query.message.edit_text("❌ Process timed out. Please try again.")
                await callback_query.answer(f"Please Try Again.🔁")
                await watermark_settings(client, callback_query)
        except asyncio.CancelledError:
            if is_process_active(user_id, "opacity"):
                await callback_query.message.edit_text("❌ Process cancelled.")
                await callback_query.answer(f"Please Try Again.🔁")
                await watermark_settings(client, callback_query)
            
    except Exception as e:
        print(f"Error in change_opacity: {str(e)}")
        await callback_query.message.edit_caption("❌ An error occurred. Please try again.")
        await callback_query.answer(f"Please Try Again.🔁")
        await watermark_settings(client, callback_query)
    finally:
        end_process(user_id, "opacity")

from typing import Dict
import asyncio

# Store active listen tasks instead of futures
listen_tasks: Dict[int, asyncio.Task] = {}

# Constants
DEFAULT_SETTINGS_IMAGE = "https://telegra.ph/file/bed7cb2dfafb6401351ab-bb15674c16e39c22b5.jpg"  # Fallback image URL

async def change_font_size(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    start_process(user_id, "font_size")
    
    try:
        settings = get_watermark_settings(user_id)
        current_size = settings.get('font_size', 100)
        
        try:
            # Try to use settings image if exists
            if os.path.exists(SETTINGS_IMAGE):
                media = InputMediaPhoto(
                    media=SETTINGS_IMAGE,
                    caption=(
                        "**Send me the new font size:**\n\n"
                        f"• Current size: {current_size}\n"
                        f"• Minimum size: {MIN_FONT_SIZE}\n"
                        f"• Maximum size: {MAX_FONT_SIZE}\n"
                        "• Must be a whole number\n\n"
                        "Send /cancel to cancel"
                    )
                )
            else:
                # Use fallback image
                media = InputMediaPhoto(
                    media=DEFAULT_SETTINGS_IMAGE,
                    caption=(
                        "**Send me the new font size:**\n\n"
                        f"• Current size: {current_size}\n"
                        f"• Minimum size: {MIN_FONT_SIZE}\n"
                        f"• Maximum size: {MAX_FONT_SIZE}\n"
                        "• Must be a whole number\n\n"
                        "Send /cancel to cancel"
                    )
                )

            await callback_query.message.edit_media(
                media=media,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🔙 Back", callback_data="watermark_marco"),
                        InlineKeyboardButton("❌ Cancel", callback_data="cancel_wm_size")
                    ],
                    [
                        InlineKeyboardButton("-10", callback_data="font_size_minus_10"),
                        InlineKeyboardButton("-5", callback_data="font_size_minus_5"),
                        InlineKeyboardButton(f"{current_size}", callback_data="current_size"),
                        InlineKeyboardButton("+5", callback_data="font_size_plus_5"),
                        InlineKeyboardButton("+10", callback_data="font_size_plus_10")
                    ]
                ])
            )

        except Exception as e:
            print(f"Error editing message: {str(e)}")
            # Fallback to simple message if media edit fails
            await callback_query.message.edit_text(
                text=(
                    "**Send me the new font size:**\n\n"
                    f"• Current size: {current_size}\n"
                    f"• Minimum size: {MIN_FONT_SIZE}\n"
                    f"• Maximum size: {MAX_FONT_SIZE}\n"
                    "• Must be a whole number\n\n"
                    "Send /cancel to cancel"
                ),
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🔙 Back", callback_data="watermark_marco"),
                        InlineKeyboardButton("❌ Cancel", callback_data="cancel_wm_size")
                    ]
                ])
            )

        # Create task from coroutine
        listen_task = asyncio.create_task(client.listen(user_id, timeout=30))
        listen_tasks[user_id] = listen_task

        try:
            response = await listen_task
            
            if not is_process_active(user_id, "font_size"):
                return
                
            if response.text == "/cancel":
                await callback_query.message.edit_text("Process cancelled!")
                await watermark_settings(client, callback_query)
                return

            try:
                size = int(response.text)
                if MIN_FONT_SIZE <= size <= MAX_FONT_SIZE:
                    update_watermark_settings(user_id, {"font_size": size})
                    await callback_query.message.edit_text(f"✅ Font size updated to: **{size}**")
                    await watermark_settings(client, callback_query)
                else:
                    await callback_query.message.edit_text(
                        f"❌ Invalid value! Size must be between {MIN_FONT_SIZE} and {MAX_FONT_SIZE}"
                    )
                    await callback_query.answer(f"Please Try Again.🔁")
                    await watermark_settings(client, callback_query)
                
            except ValueError:
                await callback_query.message.edit_text(
                    "❌ Invalid format! Please send a whole number"
                )
                await callback_query.answer(f"Please Try Again.🔁")
                await watermark_settings(client, callback_query)
                
        except asyncio.TimeoutError:
            if is_process_active(user_id, "font_size"):
                await callback_query.message.edit_text("❌ Process timed out. Please try again.")
                await callback_query.answer(f"Please Try Again.🔁")
                await watermark_settings(client, callback_query)
        except asyncio.CancelledError:
            if is_process_active(user_id, "font_size"):
                await callback_query.message.edit_text("❌ Process cancelled.")
                await callback_query.answer(f"Please Try Again.🔁")
                await watermark_settings(client, callback_query)
            
    except Exception as e:
        print(f"Error in change_font_size: {str(e)}")
        await callback_query.message.edit_text("❌ An error occurred. Please try again.")
        await callback_query.answer(f"Please Try Again.🔁")
        await watermark_settings(client, callback_query)
    finally:
        # Clean up
        end_process(user_id, "font_size")
        if user_id in listen_tasks:
            task = listen_tasks.pop(user_id)
            if not task.done():
                task.cancel()
                
async def change_watermark_color(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    settings = get_watermark_settings(user_id)
    current_color = settings.get('color', 'white')
    
    buttons = []
    row = []
    for i, (color, emoji) in enumerate(COLORS.items()):
        check = "✅" if current_color.lower() == color.lower() else ""
        row.append(InlineKeyboardButton(
            f"{color} {emoji}{check}",
            callback_data=f"set_wm_color_{color.lower()}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton("↩️ Back to Setting", callback_data="watermark_marco")])
    
    await callback_query.message.edit_media(
        media=InputMediaPhoto(
            media=SETTINGS_IMAGE,
            caption=f"**Current Text Colour: {current_color}**\n\nChoose Text WaterMark Colour."
        ),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def show_font_list(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    settings = get_watermark_settings(user_id)
    current_font = settings.get('font', 'Vampire Wars.ttf')
    
    fonts_dir = os.path.join(MARCO_DIR, "..", "fonts")
    fonts = [f for f in os.listdir(fonts_dir) if f.endswith(('.ttf', '.otf'))]
    
    buttons = []
    row = []
    for i, font in enumerate(fonts):
        check = "✅ " if font == current_font else ""
        font_name = font.split('.')[0].split('-')[0]
        row.append(InlineKeyboardButton(
            f"{check}{font_name}",
            callback_data=f"preview_font_{font}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
        
    buttons.append([InlineKeyboardButton("↩️ Back to Setting", callback_data="watermark_marco")])
    
    await callback_query.message.edit_media(
        media=InputMediaPhoto(
            media=SETTINGS_IMAGE,
            caption="**🔤 Choose your preferred font style:**"
        ),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

def generate_preview_image(text: str, font_path: str, color: str):
    """Generate a preview image with the given text and font"""
    # Create a white background image
    img = Image.new('RGB', (800, 400), '#efe4ff')
    draw = ImageDraw.Draw(img)
    
    # Load font with a large size
    try:
        font = ImageFont.truetype(font_path, 120)
    except Exception:
        font = ImageFont.load_default()
    
    # Get text size
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # Calculate center position
    x = (800 - text_width) / 2
    y = (400 - text_height) / 2
    
    # Draw text
    draw.text((x, y), text, font=font, fill=color)
    
    # Save to temporary file
    temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    img.save(temp_file.name)
    return temp_file.name


async def preview_font(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    settings = get_watermark_settings(user_id)
    
    font = callback_query.data.split("_")[-1]
    font_path = os.path.join(MARCO_DIR, "..", "fonts", font)
    
    # Get current watermark text and color
    text = settings.get('text', 'MARCO')
    color = settings.get('color', 'black')
    
    # Generate preview image
    preview_image = generate_preview_image(text, font_path, color)
    
    try:
        await callback_query.message.edit_media(
            media=InputMediaPhoto(
                media=preview_image,
                caption=f"**Font Preview**\n\n"
                f"Text: {text}\n"
                f"Font: {font.split('.')[0]}\n"
                f"Color: {color}\n\n"
                "If you like it, tap confirm below."
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Confirm", callback_data=f"set_wm_font_{font}")],
                [InlineKeyboardButton("🔙 Back", callback_data="change_wm_font")]
            ])
        )
    finally:
        # Cleanup temporary file
        if os.path.exists(preview_image):
            os.remove(preview_image)

async def set_font(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    font = callback_query.data.split("_")[-1]
    
    update_watermark_settings(user_id, {"font": font})
    await callback_query.answer("Font updated successfully!✅")
    await watermark_settings(client, callback_query)
        
async def toggle_watermark(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    settings = get_watermark_settings(user_id)
    
    current_status = settings.get('enabled', True)
    new_status = not current_status
    
    update_watermark_settings(user_id, {"enabled": new_status})
    
    await callback_query.answer(
        f"Watermark {('Enabled' if new_status else 'Disabled')}!", 
        show_alert=True
    )
    
    await watermark_settings(client, callback_query)
