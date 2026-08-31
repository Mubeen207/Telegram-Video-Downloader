import re
import math
from typing import Dict, Any, Optional, List
import httpx
from bs4 import BeautifulSoup
import yt_dlp

def validate_and_normalize_telegram_url(url: str) -> Dict[str, Any]:
    """
    Validates Telegram link and extracts channel/post information.
    """
    url = url.strip()
    if not url:
        return {"valid": False, "error": "Please provide a Telegram video link."}

    # Match public telegram post patterns:
    # https://t.me/channel_name/123
    # https://telegram.me/channel_name/123
    # https://t.me/s/channel_name/123
    # https://t.me/c/123456/789 (private group/channel - not publicly accessible)
    
    private_pattern = r"(?:https?:\/\/)?(?:www\.)?(?:t\.me|telegram\.me)\/c\/(\d+)\/(\d+)"
    if re.search(private_pattern, url):
        return {
            "valid": False,
            "error": "This Telegram link is from a private channel/group and is not publicly accessible without authentication."
        }

    public_pattern = r"(?:https?:\/\/)?(?:www\.)?(?:t\.me|telegram\.me)\/(?:s\/)?([a-zA-Z0-9_+]+)\/(\d+)"
    match = re.search(public_pattern, url)
    
    if not match:
        return {
            "valid": False,
            "error": "Invalid Telegram link format. Please provide a link like: https://t.me/channel_name/123"
        }

    channel, msg_id = match.groups()
    normalized_url = f"https://t.me/{channel}/{msg_id}"
    embed_url = f"https://t.me/{channel}/{msg_id}?embed=1"
    
    return {
        "valid": True,
        "channel": channel,
        "msg_id": msg_id,
        "normalized_url": normalized_url,
        "embed_url": embed_url
    }

def format_bytes(size_bytes: Optional[int]) -> str:
    if not size_bytes or size_bytes <= 0:
        return "Unknown size"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {units[i]}"

def format_duration(seconds: Optional[int]) -> str:
    if not seconds or seconds <= 0:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

async def extract_telegram_video_info(url: str) -> Dict[str, Any]:
    """
    Extracts video metadata from public Telegram URL using yt-dlp with HTML embed fallback.
    """
    validation = validate_and_normalize_telegram_url(url)
    if not validation["valid"]:
        return {"success": False, "error": validation["error"]}

    normalized_url = validation["normalized_url"]
    embed_url = validation["embed_url"]
    channel = validation["channel"]
    msg_id = validation["msg_id"]

    # 1. Primary extraction using yt-dlp (in-process)
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'nocheckcertificate': True,
        'socket_timeout': 10,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(normalized_url, download=False)
            
            if info:
                # Direct video URL
                direct_url = info.get('url')
                title = info.get('title') or f"telegram_{channel}_{msg_id}"
                duration = info.get('duration') or 0
                width = info.get('width')
                height = info.get('height')
                filesize = info.get('filesize') or info.get('filesize_approx')
                thumbnail = info.get('thumbnail')
                ext = info.get('ext') or 'mp4'

                # If direct filesize is not in info, query via HEAD request
                if (not filesize or filesize == 0) and direct_url:
                    try:
                        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                            head_res = await client.head(direct_url)
                            cl = head_res.headers.get("Content-Length")
                            if cl and cl.isdigit():
                                filesize = int(cl)
                    except Exception:
                        pass

                return build_video_response(
                    direct_url=direct_url,
                    source_url=normalized_url,
                    title=title,
                    channel=channel,
                    msg_id=msg_id,
                    duration=duration,
                    width=width,
                    height=height,
                    filesize=filesize,
                    thumbnail=thumbnail,
                    ext=ext
                )
    except Exception as e:
        # Fallback to direct HTML widget scraping
        pass

    # 2. Fallback: Direct Scraping of Telegram Web Embed
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        }
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
            res = await client.get(embed_url)
            if res.status_code != 200:
                return {
                    "success": False,
                    "error": "The Telegram media could not be retrieved. The message may have been deleted or the channel is private."
                }

            html = res.text
            soup = BeautifulSoup(html, "html.parser")

            # Check for error or missing message
            error_el = soup.select_one(".tgme_widget_message_error")
            if error_el:
                error_text = error_el.get_text(strip=True)
                if "not found" in error_text.lower():
                    return {"success": False, "error": "Telegram post not found. Check if the link is correct."}
                return {"success": False, "error": f"Telegram restriction: {error_text}"}

            # Search for video element
            video_el = soup.select_one("video.tgme_widget_message_video, video")
            if not video_el:
                # Check if it's a photo or text-only post
                photo_el = soup.select_one(".tgme_widget_message_photo_wrap")
                if photo_el:
                    return {"success": False, "error": "This Telegram link contains an image, not a video."}
                return {"success": False, "error": "No public video found at this Telegram URL. The media might be protected or private."}

            direct_url = video_el.get("src")
            if not direct_url:
                return {"success": False, "error": "Could not extract direct video stream URL from Telegram."}

            # Extract thumbnail
            thumbnail = None
            thumb_el = soup.select_one(".tgme_widget_message_video_thumb")
            if thumb_el and "style" in thumb_el.attrs:
                style = thumb_el["style"]
                match = re.search(r"background-image:\s*url\('(.*?)'\)", style)
                if match:
                    thumbnail = match.group(1)

            # Extract duration
            duration = 0
            time_el = soup.select_one(".tgme_widget_message_video_duration, time")
            if time_el:
                time_str = time_el.get_text(strip=True)
                parts = time_str.split(":")
                if len(parts) == 2:
                    duration = int(parts[0]) * 60 + int(parts[1])
                elif len(parts) == 3:
                    duration = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])

            # Extract message text as title
            text_el = soup.select_one(".tgme_widget_message_text")
            title = text_el.get_text(strip=True)[:60] if text_el else f"Telegram_{channel}_{msg_id}"
            if not title:
                title = f"Telegram_{channel}_{msg_id}"

            # Get Content-Length
            filesize = None
            try:
                head_res = await client.head(direct_url)
                cl = head_res.headers.get("Content-Length")
                if cl and cl.isdigit():
                    filesize = int(cl)
            except Exception:
                pass

            return build_video_response(
                direct_url=direct_url,
                source_url=normalized_url,
                title=title,
                channel=channel,
                msg_id=msg_id,
                duration=duration,
                width=None,
                height=None,
                filesize=filesize,
                thumbnail=thumbnail,
                ext='mp4'
            )

    except Exception as ex:
        return {
            "success": False,
            "error": f"Failed to analyze Telegram video: {str(ex)}"
        }

def build_video_response(
    direct_url: str,
    source_url: str,
    title: str,
    channel: str,
    msg_id: str,
    duration: int,
    width: Optional[int],
    height: Optional[int],
    filesize: Optional[int],
    thumbnail: Optional[str],
    ext: str = 'mp4'
) -> Dict[str, Any]:
    """
    Constructs normalized response with dynamic quality and compression options.
    """
    # Clean filename title
    safe_title = re.sub(r'[\\/*?:"<>|]', '', title).strip() or f"telegram_{channel}_{msg_id}"
    filename = f"{safe_title}.{ext}"

    # Determine resolution label
    resolution_label = "HD"
    if width and height:
        resolution_label = f"{width} × {height}"
    elif height:
        resolution_label = f"{height}p"

    # Dynamic available qualities (strictly what's available without false upscaling)
    qualities = [{"id": "original", "name": "Original", "is_default": True}]
    
    source_height = height or 1080 # default assumed source max if not specified
    if source_height >= 1080:
        qualities.append({"id": "1080p", "name": "1080p (Full HD)", "height": 1080})
    if source_height >= 720:
        qualities.append({"id": "720p", "name": "720p (HD)", "height": 720})
    if source_height >= 480:
        qualities.append({"id": "480p", "name": "480p (SD)", "height": 480})
    if source_height >= 360:
        qualities.append({"id": "360p", "name": "360p (Low)", "height": 360})

    # Compression presets with estimated sizes
    compression_presets = [
        {
            "id": "best",
            "name": "Best Quality",
            "description": "Maximum practical quality with minimal compression",
            "estimated_size": format_bytes(int(filesize * 0.85)) if filesize else "Estimated ~85%"
        },
        {
            "id": "balanced",
            "name": "Balanced",
            "description": "Good visual quality with significantly reduced file size",
            "estimated_size": format_bytes(int(filesize * 0.55)) if filesize else "Estimated ~55%"
        },
        {
            "id": "smallest",
            "name": "Smallest Size",
            "description": "Maximum compression for lowest bandwidth and storage",
            "estimated_size": format_bytes(int(filesize * 0.30)) if filesize else "Estimated ~30%"
        }
    ]

    return {
        "success": True,
        "data": {
            "source_url": source_url,
            "direct_url": direct_url,
            "title": safe_title,
            "filename": filename,
            "channel": channel,
            "msg_id": msg_id,
            "duration": duration,
            "formatted_duration": format_duration(duration),
            "width": width,
            "height": height,
            "resolution": resolution_label,
            "format": ext.upper(),
            "filesize": filesize or 0,
            "formatted_filesize": format_bytes(filesize),
            "thumbnail": thumbnail,
            "available_qualities": qualities,
            "compression_presets": compression_presets
        }
    }
