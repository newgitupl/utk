import os
import logging 
logger = logging.getLogger(__name__)
import subprocess   
import datetime   
import asyncio   
import os
import mmap
import requests   
import time
import base64
from io import BytesIO
from p_bar import progress_bar
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import aiohttp   
import aiofiles   
import tgcrypto   
import concurrent.futures   
import subprocess   
from pyrogram.types import Message   
from pyrogram import Client, filters
from pathlib import Path
import re
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64decode

def duration(filename):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of",
                             "default=noprint_wrappers=1:nokey=1", filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)
    return float(result.stdout)

def get_mps_and_keys(api_url):
    response = requests.get(api_url)
    response_json = response.json()
    mpd = response_json.get('MPD')
    keys = response_json.get('KEYS')
    return mpd, keys



async def decrypt_and_merge_video(mpd_url, keys_string, output_path, output_name, quality="720"):
    try:
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        cmd1 = f'yt-dlp -f "bv[height<={quality}]+ba/b" -o "{output_path}/file.%(ext)s" --allow-unplayable-format --no-check-certificate --external-downloader aria2c "{mpd_url}"'
        print(f"Running command: {cmd1}")
        os.system(cmd1)
        
        avDir = list(output_path.iterdir())
        print(f"Downloaded files: {avDir}")
        print("Decrypting")

        video_decrypted = False
        audio_decrypted = False

        for data in avDir:
            if data.suffix == ".mp4" and not video_decrypted:
                cmd2 = f'mp4decrypt {keys_string} --show-progress "{data}" "{output_path}/video.mp4"'
                print(f"Running command: {cmd2}")
                os.system(cmd2)
                if (output_path / "video.mp4").exists():
                    video_decrypted = True
                data.unlink()
            elif data.suffix == ".m4a" and not audio_decrypted:
                cmd3 = f'mp4decrypt {keys_string} --show-progress "{data}" "{output_path}/audio.m4a"'
                print(f"Running command: {cmd3}")
                os.system(cmd3)
                if (output_path / "audio.m4a").exists():
                    audio_decrypted = True
                data.unlink()

        if not video_decrypted or not audio_decrypted:
            raise FileNotFoundError("Decryption failed: video or audio file not found.")

        cmd4 = f'ffmpeg -i "{output_path}/video.mp4" -i "{output_path}/audio.m4a" -c copy "{output_path}/{output_name}.mp4"'
        print(f"Running command: {cmd4}")
        os.system(cmd4)
        if (output_path / "video.mp4").exists():
            (output_path / "video.mp4").unlink()
        if (output_path / "audio.m4a").exists():
            (output_path / "audio.m4a").unlink()
        
        filename = output_path / f"{output_name}.mp4"

        if not filename.exists():
            raise FileNotFoundError("Merged video file not found.")

        cmd5 = f'ffmpeg -i "{filename}" 2>&1 | grep "Duration"'
        duration_info = os.popen(cmd5).read()
        print(f"Duration info: {duration_info}")

        return str(filename)

    except Exception as e:
        print(f"Error during decryption and merging: {str(e)}")
        raise
       
async def run(cmd):   
    proc = await asyncio.create_subprocess_shell(   
        cmd,   
        stdout=asyncio.subprocess.PIPE,   
        stderr=asyncio.subprocess.PIPE)   
   
    stdout, stderr = await proc.communicate()   
   
    print(f'[{cmd!r} exited with {proc.returncode}]')   
    if proc.returncode == 1:   
        return False   
    if stdout:   
        return f'[stdout]\n{stdout.decode()}'   
    if stderr:   
        return f'[stderr]\n{stderr.decode()}'   
   
    
def decrypt_file(file_path, key):  
    if not os.path.exists(file_path): 
        return False  

    with open(file_path, "r+b") as f:  
        num_bytes = min(28, os.path.getsize(file_path))  
        with mmap.mmap(f.fileno(), length=num_bytes, access=mmap.ACCESS_WRITE) as mmapped_file:  
            for i in range(num_bytes):  
                mmapped_file[i] ^= ord(key[i]) if i < len(key) else i 
    return True


async def download_and_decrypt_video(url, cmd, name, key):  
    video_path = await download_video(url, cmd, name)  
    
    if video_path:  
        decrypted = decrypt_file(video_path, key)  
        if decrypted:  
            print(f"File {video_path} decrypted successfully.")  
            return video_path  
        else:  
            print(f"Failed to decrypt {video_path}.")  
            return None  

async def download_and_decrypt_pdf(url, name, key):  
    download_cmd = f'yt-dlp -o "{name}.pdf" "{url}" -R 25 --fragment-retries 25'  
    try:  
        subprocess.run(download_cmd, shell=True, check=True)  
        print(f"Downloaded PDF: {name}.pdf")  
    except subprocess.CalledProcessError as e:  
        print(f"Error during download: {e}")  
        return False  
    
    file_path = f"{name}.pdf"  
    if not os.path.exists(file_path):  
        print(f"The file {file_path} does not exist.")  
        return False  

    try:  
        with open(file_path, "r+b") as f: 
            num_bytes = min(28, os.path.getsize(file_path))  
            with mmap.mmap(f.fileno(), length=num_bytes, access=mmap.ACCESS_WRITE) as mmapped_file:  
                for i in range(num_bytes):  
                    mmapped_file[i] ^= ord(key[i]) if i < len(key) else i  

        print(f"Decryption completed for {file_path}.") 
        return file_path 
    except Exception as e:  
        print(f"Error during decryption: {e}")  
        return False

#==========================Megatron helper====================================

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def create_or_get_topic(bot: Client, chat_id: int, topic_name: str):
    """
    Create a new topic if it doesn't exist, or get existing topic ID with better error handling
    """
    try:
        logger.info(f"Attempting to create/get topic: {topic_name} in chat: {chat_id}")
        
        # First check if the chat is a forum
        chat = await bot.get_chat(chat_id)
        if not chat.is_forum:
            logger.warning(f"Chat {chat_id} is not a forum. Topics cannot be created.")
            return None

        # Get existing topics
        try:
            topics = await bot.get_forum_topics(chat_id)
            for topic in topics:
                if topic.title.lower() == topic_name.lower():
                    logger.info(f"Found existing topic: {topic_name} with ID: {topic.id}")
                    return topic.id
        except Exception as e:
            logger.error(f"Error getting forum topics: {str(e)}")
            topics = []

        # Create new topic
        try:
            new_topic = await bot.create_forum_topic(
                chat_id=chat_id,
                title=topic_name,
                icon_color=0x6FB9F0  # Light blue color
            )
            logger.info(f"Created new topic: {topic_name} with ID: {new_topic.id}")
            return new_topic.id
        except Exception as e:
            logger.error(f"Error creating forum topic: {str(e)}")
            return None

    except Exception as e:
        logger.error(f"Error in create_or_get_topic: {str(e)}")
        return None
        

#==========================  MEGATRON HELPER   ====================================




def duration(filename):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of",
                             "default=noprint_wrappers=1:nokey=1", filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)
    return float(result.stdout)
    
def exec(cmd):
        process = subprocess.run(cmd, stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        output = process.stdout.decode()
        print(output)
        return output
        #err = process.stdout.decode()
def pull_run(work, cmds):
    with concurrent.futures.ThreadPoolExecutor(max_workers=work) as executor:
        print("Waiting for tasks to complete")
        fut = executor.map(exec,cmds)
async def aio(url,name):
    k = f'{name}.pdf'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(k, mode='wb')
                await f.write(await resp.read())
                await f.close()
    return k


async def download(url,name):
    ka = f'{name}.pdf'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(ka, mode='wb')
                await f.write(await resp.read())
                await f.close()
    return ka



def parse_vid_info(info):
    info = info.strip()
    info = info.split("\n")
    new_info = []
    temp = []
    for i in info:
        i = str(i)
        if "[" not in i and '---' not in i:
            while "  " in i:
                i = i.replace("  ", " ")
            i.strip()
            i = i.split("|")[0].split(" ",2)
            try:
                if "RESOLUTION" not in i[2] and i[2] not in temp and "audio" not in i[2]:
                    temp.append(i[2])
                    new_info.append((i[0], i[2]))
            except:
                pass
    return new_info


def vid_info(info):
    info = info.strip()
    info = info.split("\n")
    new_info = dict()
    temp = []
    for i in info:
        i = str(i)
        if "[" not in i and '---' not in i:
            while "  " in i:
                i = i.replace("  ", " ")
            i.strip()
            i = i.split("|")[0].split(" ",3)
            try:
                if "RESOLUTION" not in i[2] and i[2] not in temp and "audio" not in i[2]:
                    temp.append(i[2])
                    
                    # temp.update(f'{i[2]}')
                    # new_info.append((i[2], i[0]))
                    #  mp4,mkv etc ==== f"({i[1]})" 
                    
                    new_info.update({f'{i[2]}':f'{i[0]}'})

            except:
                pass
    return new_info



async def run(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()

    print(f'[{cmd!r} exited with {proc.returncode}]')
    if proc.returncode == 1:
        return False
    if stdout:
        return f'[stdout]\n{stdout.decode()}'
    if stderr:
        return f'[stderr]\n{stderr.decode()}'

    

def old_download(url, file_name, chunk_size = 1024 * 10):
    if os.path.exists(file_name):
        os.remove(file_name)
    r = requests.get(url, allow_redirects=True, stream=True)
    with open(file_name, 'wb') as fd:
        for chunk in r.iter_content(chunk_size=chunk_size):
            if chunk:
                fd.write(chunk)
    return file_name


def human_readable_size(size, decimal_places=2):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if size < 1024.0 or unit == 'PB':
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f} {unit}"


def time_name():
    date = datetime.date.today()
    now = datetime.datetime.now()
    current_time = now.strftime("%H%M%S")
    return f"{date} {current_time}.mp4"

# helper.py
async def download_and_send_video(url, name, chat_id, bot, log_channel_id, accept_logs, caption, m):
    """
    Downloads a video from a URL and sends it to the specified chat.
    Handles encrypted video URLs differently if needed.
    """
    try:
        # Check if the URL is for an encrypted video
        if "encrypted" in url:
            # Add specific handling for encrypted videos here if necessary
            print("Handling encrypted video...")
        
        # Download the video
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    video_data = await response.read()
                    video_path = f"{name}.mp4"
                    
                    # Save video to a file
                    with open(video_path, 'wb') as f:
                        f.write(video_data)
                    
                    # Send the video to the user
                    message = await bot.send_video(chat_id=chat_id, video=video_path, caption=caption)
                    
                    # Log the video to a specific channel if required
                    if accept_logs == 1:
                        file_id = message.video.file_id
                        await bot.send_video(chat_id=log_channel_id, video=file_id, caption=caption)
                    
                    # Cleanup: Remove the video file after sending
                    os.remove(video_path)
                else:
                    await m.reply_text(f"Failed to download video. Status code: {response.status}")
    except Exception as e:
        await m.reply_text(f"An error occurred: {str(e)}")



async def download_video(url,cmd, name):
    download_cmd = f'{cmd} -R 25 --fragment-retries 25 --external-downloader aria2c --downloader-args "aria2c: -x 16 -j 32"'
    global failed_counter  
    print(download_cmd)
    logging.info(download_cmd)
    k = subprocess.run(download_cmd, shell=True)
    if "visionias" in cmd and k.returncode != 0 and failed_counter <= 10:
        failed_counter += 1
        await asyncio.sleep(5)
        await download_video(url, cmd, name)
    failed_counter = 0
    try:
        if os.path.isfile(name):
            return name
        elif os.path.isfile(f"{name}.webm"):
            return f"{name}.webm"
        name = name.split(".")[0]
        if os.path.isfile(f"{name}.mkv"):
            return f"{name}.mkv"
        elif os.path.isfile(f"{name}.mp4"):
            return f"{name}.mp4"
        elif os.path.isfile(f"{name}.mp4.webm"):
            return f"{name}.mp4.webm"

        return name
    except FileNotFoundError as exc:
        return os.path.isfile.splitext[0] + "." + "mp4"


import requests

async def send_doc(bot: Client, m: Message, ka, caption, prog, count, name, channel_id, thumb="pdfthumb.jpg"):
    try:
        topic_name = None
        # Extract topic name from caption
        if "🏷️" in caption:
            try:
                topic_start = caption.find("🏷️") + 2
                topic_end = caption.find("─ ⋅", topic_start)
                if topic_end != -1:
                    topic_name = caption[topic_start:topic_end].strip()
                    logger.info(f"Extracted topic name: {topic_name}")
            except Exception as e:
                logger.error(f"Error extracting topic name: {str(e)}")

        # Create/get topic
        topic_id = None
        if topic_name:
            topic_id = await create_or_get_topic(bot, channel_id, topic_name)
            if topic_id:
                logger.info(f"Using topic ID: {topic_id} for upload")
            else:
                logger.warning("Failed to get/create topic. Uploading without topic.")

        # Send message and document
        reply = await bot.send_message(channel_id, f"Downloading pdf:\n<pre><code>{name}</code></pre>")
        time.sleep(1)
        start_time = time.time()
        
        await bot.send_document(
            ka,
            thumb=thumb,
            caption=caption,
            message_thread_id=topic_id if topic_id else None
        )
        
        count += 1
        await reply.delete(True)
        time.sleep(1)
        os.remove(ka)
        time.sleep(3)

    except Exception as e:
        logger.error(f"Error in send_doc: {str(e)}")
        if m:
            await m.reply_text(f"Failed to send document: {str(e)}")



async def send_doc(bot: Client, m: Message, cc, ka, cc1, prog, count, name, channel_id, thumb="pdfthumb.jpg"):
    # Similar changes as send_vid
    topic_name = None
    if "🏷️" in caption:
        try:
            topic_start = caption.find("🏷️") + 2 
            topic_end = caption.find("─ ⋅", topic_start)
            topic_name = caption[topic_start:topic_end].strip()
        except:
            pass

    topic_id = None    
    if topic_name:
        topic_id = await create_or_get_topic(bot, channel_id, topic_name)

    
    
    reply = await bot.send_message(channel_id, f"Downloading pdf:\n<pre><code>{name}</code></pre>")
    time.sleep(1)
    start_time = time.time()
    await bot.send_document(
        ka,
        thumb=thumb,
        caption=caption,
        message_thread_id=topic_id,
           # <<-- thumbnail image path (local file) or bytes IO
    )
    count += 1
    await reply.delete(True)
    time.sleep(1)
    os.remove(ka)
    time.sleep(3)
    




#======================  WATERMARK =============================

from marco.authdb import get_watermark_settings

async def send_vid(bot: Client, m: Message, caption, filename, thumb, name, prog, channel_id):
    try:
        # Step 1: Extract topic name from caption
        topic_name, topic_id = None, None
        if "🏷️" in caption:
            try:
                topic_start = caption.find("🏷️") + 2
                topic_end = caption.find("─ ⋅", topic_start)
                if topic_end != -1:
                    topic_name = caption[topic_start:topic_end].strip()
                    logger.info(f"Extracted topic name: {topic_name}")
            except Exception as e:
                logger.error(f"Error extracting topic name: {e}")
        
        # Step 2: Get or create topic in channel
        if topic_name:
            try:
                topic_id = await create_or_get_topic(bot, channel_id, topic_name)
                if topic_id:
                    logger.info(f"Using topic ID: {topic_id} for upload")
            except Exception as e:
                logger.warning(f"Failed to create topic: {e}")

        # Step 3: Watermark Settings
        user_settings = get_watermark_settings(m.from_user.id)

        # Step 4: Notify upload start
        await prog.delete(True)
        reply = await bot.send_message(channel_id, f"**⚡ Video Uploading ** : \n<blockquote>{name}</blockquote>")

        # Step 5: Thumbnail Generation
        thumbnail = thumb
        if not thumb or thumb == "/d":
            try:
                thumb_path = f"{filename}.jpg"

                if not user_settings.get("enabled", True):
                    subprocess.run(
                        f'ffmpeg -i "{filename}" -ss 00:00:01 -vframes 1 -s 1280x720 "{thumb_path}"',
                        shell=True,
                        check=True
                    )
                else:
                    # Watermark details
                    wm_text = user_settings.get("text", "AAWARA")
                    font_file = user_settings.get("font", "Chopsic.otf")
                    font_color = user_settings.get("color", "white").lower()
                    opacity = user_settings.get("opacity", 0.8)
                    font_size = user_settings.get("font_size", 200)

                    hex_colors = {
                        "white": "#FFFFFF", "black": "#000000", "red": "#FF0000",
                        "blue": "#0000FF", "green": "#00FF00", "golden": "#FFD700"
                    }
                    font_color_hex = hex_colors.get(font_color, font_color)

                    font_path = os.path.join("fonts", font_file)
                    if not os.path.exists(font_path):
                        font_path = os.path.join("fonts", "Chopsic.otf")

                    # Create temporary thumbnail
                    temp_thumb = f"{filename}_temp.jpg"
                    subprocess.run(
                        f'ffmpeg -i "{filename}" -ss 00:00:01 -vframes 1 -s 1280x720 "{temp_thumb}"',
                        shell=True,
                        check=True
                    )

                    # Apply watermark
                    subprocess.run(
                        f'ffmpeg -i "{temp_thumb}" -vf "drawtext=text=\'{wm_text}\':'
                        f'fontfile=\'{font_path}\':fontsize={font_size}:'
                        f'fontcolor={font_color_hex}@{opacity}:'
                        f'x=(w-text_w)/2:y=(h-text_h)/2" "{thumb_path}"',
                        shell=True,
                        check=True
                    )

                    if os.path.exists(temp_thumb):
                        os.remove(temp_thumb)

                thumbnail = thumb_path

            except Exception as e:
                logger.error(f"Watermark/thumbnail error: {e}")
                subprocess.run(
                    f'ffmpeg -i "{filename}" -ss 00:00:01 -vframes 1 -s 1280x720 "{filename}.jpg"',
                    shell=True
                )
                thumbnail = f"{filename}.jpg"

        # Step 6: Get video duration
        dur = int(duration(filename))
        start_time = time.time()

        # Step 7: Upload video
        try:
            await bot.send_video(
                chat_id=channel_id,
                video=filename,
                caption=caption,
                thumb=thumbnail,
                height=720,
                width=1280,
                duration=dur,
                supports_streaming=True,
                message_thread_id=topic_id,
                progress=progress_bar,
                progress_args=(reply, start_time)
            )
        except Exception as e:
            logger.warning(f"Sending video failed, sending as document: {e}")
            await bot.send_document(
                chat_id=channel_id,
                document=filename,
                caption=caption,
                thumb=thumbnail,
                message_thread_id=topic_id,
                progress=progress_bar,
                progress_args=(reply, start_time)
            )

        # Step 8: Cleanup
        if os.path.exists(f"{filename}.jpg"):
            os.remove(f"{filename}.jpg")
        await reply.delete(True)

    except Exception as e:
        logger.error(f"send_vid failed: {e}")
        if m:
            await m.reply_text(f"❌ Upload failed: {e}")

            
