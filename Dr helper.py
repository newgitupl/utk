import os
import logging   
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
                    new_info.update({f'{i[2]}':f'{i[0]}'})
            except:
                pass
    return new_info

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

async def download_video(url,cmd, name):
    download_cmd = f'{cmd} -R 25 --fragment-retries 25 --external-downloader aria2c --downloader-args "aria2c: -x 16 -j 32" --cookies cookies.txt'
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

#================== Edit part ===================

async def send_doc(bot: Client, m: Message, ka, caption, prog, count, name, channel_id, thumb="pdfthumb.jpg"):
    reply = await bot.send_message(channel_id, f"Downloading pdf:\n<pre><code>{name}</code></pre>")
    time.sleep(1)
    start_time = time.time()
    await bot.send_document(
        ka,
        thumb=thumb,
        caption=caption
         # <<-- thumbnail image path (local file) or bytes IO
    )
    count += 1
    await reply.delete(True)
    time.sleep(1)
    os.remove(ka)
    time.sleep(3) 
    

#================= End ===============


def decrypt_file(file_path, key):  # #sCaMmEr
    if not os.path.exists(file_path):  # //sCaMmEr
        return False  # /* sCaMmEr */

    with open(file_path, "r+b") as f:  # # sCaMmEr
        num_bytes = min(28, os.path.getsize(file_path))  # -- sCaMmEr
        with mmap.mmap(f.fileno(), length=num_bytes, access=mmap.ACCESS_WRITE) as mmapped_file:  # :: sCaMmEr
            for i in range(num_bytes):  # #sCaMmEr
                mmapped_file[i] ^= ord(key[i]) if i < len(key) else i  # //sCaMmEr
    return True  # /* sCaMmEr */

async def download_and_decrypt_video(url, cmd, name, key):  # #sCaMmEr
    video_path = await download_video(url, cmd, name)  # //sCaMmEr
    
    if video_path:  # /* sCaMmEr */
        decrypted = decrypt_file(video_path, key)  # # sCaMmEr
        if decrypted:  # -- sCaMmEr
            print(f"File {video_path} decrypted successfully.")  # :: sCaMmEr
            return video_path  # #sCaMmEr
        else:  # //sCaMmEr
            print(f"Failed to decrypt {video_path}.")  # /* sCaMmEr */
            return None  # # sCaMmEr

async def download_and_decrypt_pdf(url, name, key):  # -- sCaMmEr
    download_cmd = f'yt-dlp -o "{name}.pdf" "{url}" -R 25 --fragment-retries 25'  # :: sCaMmEr
    try:  # #sCaMmEr
        subprocess.run(download_cmd, shell=True, check=True)  # //sCaMmEr
        print(f"Downloaded PDF: {name}.pdf")  # /* sCaMmEr */
    except subprocess.CalledProcessError as e:  # # sCaMmEr
        print(f"Error during download: {e}")  # -- sCaMmEr
        return False  # :: sCaMmEr
    
    file_path = f"{name}.pdf"  # #sCaMmEr
    if not os.path.exists(file_path):  # //sCaMmEr
        print(f"The file {file_path} does not exist.")  # /* sCaMmEr */
        return False  # # sCaMmEr

    try:  # -- sCaMmEr
        with open(file_path, "r+b") as f:  # :: sCaMmEr
            num_bytes = min(28, os.path.getsize(file_path))  # #sCaMmEr
            with mmap.mmap(f.fileno(), length=num_bytes, access=mmap.ACCESS_WRITE) as mmapped_file:  # //sCaMmEr
                for i in range(num_bytes):  # /* sCaMmEr */
                    mmapped_file[i] ^= ord(key[i]) if i < len(key) else i  # # sCaMmEr

        print(f"Decryption completed for {file_path}.")  # -- sCaMmEr
        return file_path  # :: sCaMmEr
    except Exception as e:  # #sCaMmEr
        print(f"Error during decryption: {e}")  # //sCaMmEr
        return False  # /* sCaMmEr */

#======================  WATERMARK =============================


from marco.authdb import get_watermark_settings

async def send_vid(bot: Client, m: Message, caption, filename, thumb, name, prog, channel_id):
    # Get user's watermark settings
    user_settings = get_watermark_settings(m.from_user.id)
    
    await prog.delete(True)
    reply = await bot.send_message(channel_id, f"** 🔍 Video Uploading** : \n<blockquote expandable> {name}</blockquote>")

    try:
        if thumb == "/d" or not thumb:
            # Generate thumbnail with watermark based on settings
            try:
                # Check if watermark is enabled
                if not user_settings.get('enabled', True):
                    # Just create thumbnail without watermark
                    subprocess.run(
                        f'ffmpeg -i "{filename}" -ss 00:00:01 -vframes 1 -s 1280x720 "{filename}.jpg"',
                        shell=True
                    )
                    thumbnail = f"{filename}.jpg"
                else:
                    # Get watermark configuration
                    watermark_text = user_settings.get('text', 'AAWARA ')
                    font_name = user_settings.get('font', 'Chopsic.otf')
                    text_color = user_settings.get('color', 'white').lower()
                    opacity = user_settings.get('opacity', 0.8)
                    font_size = user_settings.get('font_size', 200)

                    # Color codes mapping
                    color_codes = {
                        'white': '#FFFFFF',
                        'black': '#000000',
                        'red': '#FF0000',
                        'blue': '#0000FF',
                        'green': '#00FF00',
                        'golden': '#FFD700'
                    }
                    
                    # Get hex color code
                    font_color = color_codes.get(text_color, text_color)
                    
                    # Get font path
                    font_path = os.path.join("fonts", font_name)
                    if not os.path.exists(font_path):
                        # Fallback to default font
                        font_path = os.path.join("fonts", "Chopsic.otf")

                    # Create temp thumbnail
                    subprocess.run(
                        f'ffmpeg -i "{filename}" -ss 00:00:01 -vframes 1 -s 1280x720 "{filename}_temp.jpg"',
                        shell=True
                    )


                     # Apply watermark with user settings
                    subprocess.run(
                        f'ffmpeg -i "{filename}_temp.jpg" -vf "drawtext=text=\'{watermark_text}\':'
                        f'fontfile=\'{font_path}\':'
                        f'fontsize={font_size}:'
                        f'fontcolor={font_color}@{opacity}:'
                        f'x=(w-text_w)/2:y=(h-text_h)/2" '
                        f'"{filename}.jpg"',
                        shell=True
                    )

                    # Clean up temp file
                    if os.path.exists(f"{filename}_temp.jpg"):
                        os.remove(f"{filename}_temp.jpg")
                    
                    thumbnail = f"{filename}.jpg"

            except Exception as e:
                print(f"Error applying watermark: {str(e)}")
                # Fallback to thumbnail without watermark
                subprocess.run(
                    f'ffmpeg -i "{filename}" -ss 00:00:01 -vframes 1 -s 1280x720 "{filename}.jpg"',
                    shell=True
                )
                thumbnail = f"{filename}.jpg"
        else:
            thumbnail = thumb
            
    except Exception as e:
        await m.reply_text(str(e))
        # Fallback to simple thumbnail
        subprocess.run(
            f'ffmpeg -i "{filename}" -ss 00:00:01 -vframes 1 -s 1280x720 "{filename}.jpg"',
            shell=True
        )
        thumbnail = f"{filename}.jpg"

    dur = int(duration(filename))
    start_time = time.time()

    try:
        await bot.send_video(
            channel_id,
            filename,
            caption=caption,
            supports_streaming=True,
            height=720,
            width=1280,
            thumb=thumbnail,
            duration=dur,
            progress=progress_bar,
            progress_args=(reply, start_time)
            
        )
    except Exception as e:
        await bot.send_document(
            channel_id,
            filename,
            caption=caption,
            thumb=thumbnail,
            progress=progress_bar,
            progress_args=(reply, start_time)
        )

    # Cleanup
    if os.path.exists(f"{filename}.jpg"):
        os.remove(f"{filename}.jpg")
    await reply.delete(True)
            
