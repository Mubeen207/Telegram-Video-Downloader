import os
import re
import math
import asyncio
from typing import Dict, Any, Optional, List
import httpx
from bs4 import BeautifulSoup
import yt_dlp
from backend.database import get_setting

def validate_and_normalize_telegram_url(url: str) -> Dict[str, Any]:
    """
    Validates Telegram link and extracts channel/post information.
    """
    url = url.strip()
    if not url:
        return {"valid": False, "error": "Please provide a Telegram video link."}

    # Match private channel/group links (e.g. t.me/c/123456/789)
    private_pattern = r"(?:https?:\/\/)?(?:www\.)?(?:t\.me|telegram\.me)\/c\/(\d+)\/(\d+)"
    if re.search(private_pattern, url):
        return {
            "valid": False,
            "error": "This Telegram link is from a private channel/group ('t.me/c/...') and is not publicly accessible without Telegram session authentication."
        }

    # Match public telegram post patterns including topic threads
    public_pattern = r"(?:https?:\/\/)?(?:www\.)?(?:t\.me|telegram\.me)\/(?:s\/)?([a-zA-Z0-9_+]+)(?:\/\d+)?\/(\d+)"
    match = re.search(public_pattern, url)
    
    if not match:
        simple_pattern = r"(?:https?:\/\/)?(?:www\.)?(?:t\.me|telegram\.me)\/(?:s\/)?([a-zA-Z0-9_+]+)\/(\d+)"
        match = re.search(simple_pattern, url)

    if not match:
        return {
            "valid": False,
            "error": "Invalid Telegram link format. Please provide a public link like: https://t.me/channel_name/123"
        }

    channel, msg_id = match.groups()
    normalized_url = f"https://t.me/{channel}/{msg_id}"
    embed_url = f"https://t.me/{channel}/{msg_id}?embed=1"
    s_url = f"https://t.me/s/{channel}/{msg_id}"
    
    return {
        "valid": True,
        "channel": channel,
        "msg_id": msg_id,
        "normalized_url": normalized_url,
        "embed_url": embed_url,
        "s_url": s_url
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

def parse_telegram_html(html: str, channel: str, msg_id: str, normalized_url: str) -> Optional[Dict[str, Any]]:
    """
    Fast synchronous DOM & regex parser for Telegram HTML preview pages.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Check for Telegram restriction notices
    error_el = soup.select_one(".tgme_widget_message_error")
    if error_el:
        error_text = error_el.get_text(strip=True).lower()
        if any(w in error_text for w in ["restrict", "protected", "private", "access denied", "forbidden", "saving"]):
            return {
                "restricted": True,
                "error": "This Telegram post has content protection enabled ('Restrict Saving Content'). Media cannot be downloaded from restricted channels."
            }

    target_container = soup.select_one(f'[data-post="{channel}/{msg_id}"]') or soup

    # Strategy 1: <video> element
    video_el = target_container.select_one(
        "video.tgme_widget_message_video, "
        "video.tgme_widget_message_roundvideo, "
        ".tgme_widget_message_video_player video, "
        ".tgme_widget_message_bubble video, "
        ".tgme_widget_message_wrap video, "
        "video"
    )
    direct_url = None
    if video_el:
        direct_url = video_el.get("src")
        if not direct_url:
            source_tag = video_el.select_one("source")
            if source_tag:
                direct_url = source_tag.get("src")

    # Strategy 2: Document video attachment
    if not direct_url:
        doc_video = target_container.select_one(
            "a.tgme_widget_message_document_wrap[href*='.mp4'], "
            "a.tgme_widget_message_document_wrap[href*='.mkv'], "
            "a.tgme_widget_message_document_wrap[href*='.mov'], "
            "a.tgme_widget_message_document_wrap[href*='.webm']"
        )
        if doc_video:
            direct_url = doc_video.get("href")

    # Strategy 3: Fast Regex scan for direct CDN video streams
    if not direct_url:
        video_url_matches = re.findall(
            r'(https?:\/\/[^"\'\s<>]+\.(?:mp4|m4v|mov|webm)(?:\?[^"\'\s<>]*)?)',
            html
        )
        for match_url in video_url_matches:
            if "telegram" in match_url or "telesco.pe" in match_url or "cdn" in match_url:
                direct_url = match_url
                break
        if not direct_url and video_url_matches:
            direct_url = video_url_matches[0]

    # Strategy 4: telesco.pe round video
    if not direct_url:
        telescope_match = re.search(r'(https?:\/\/telesco\.pe\/[^"\'\s<>]+\.mp4)', html)
        if telescope_match:
            direct_url = telescope_match.group(1)

    if not direct_url:
        # Check if post exists but is restricted
        has_message_bubble = bool(target_container.select_one(".tgme_widget_message, .tgme_widget_message_bubble, .tgme_widget_message_wrap"))
        has_video_placeholder = bool(target_container.select_one(".tgme_widget_message_video_thumb, .tgme_widget_message_video_player, .tgme_widget_message_roundvideo_thumb, .message_media_not_supported"))
        if has_message_bubble and has_video_placeholder:
            return {
                "restricted": True,
                "error": "This Telegram post has content protection enabled ('Restrict Saving Content'). Media cannot be downloaded."
            }
        return None

    if direct_url.startswith("//"):
        direct_url = "https:" + direct_url
    elif direct_url.startswith("/") and not direct_url.startswith("http"):
        direct_url = "https://t.me" + direct_url

    # Thumbnail
    thumbnail = None
    thumb_el = target_container.select_one(
        ".tgme_widget_message_video_thumb, "
        ".tgme_widget_message_roundvideo_thumb, "
        ".tgme_widget_message_photo_wrap"
    )
    if thumb_el and "style" in thumb_el.attrs:
        match = re.search(r"background-image:\s*url\(['\"]?(.*?)['\"]?\)", thumb_el["style"])
        if match:
            thumbnail = match.group(1)

    # Duration
    duration = 0
    time_el = target_container.select_one(
        ".tgme_widget_message_video_duration, "
        ".tgme_widget_message_roundvideo_duration, "
        "time"
    )
    if time_el:
        time_str = time_el.get_text(strip=True)
        parts = time_str.split(":")
        if len(parts) == 2:
            duration = int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            duration = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])

    # Title
    text_el = target_container.select_one(".tgme_widget_message_text")
    title = text_el.get_text(strip=True)[:60] if text_el else f"Telegram_{channel}_{msg_id}"
    if not title:
        title = f"Telegram_{channel}_{msg_id}"

    return {
        "direct_url": direct_url,
        "title": title,
        "duration": duration,
        "thumbnail": thumbnail
    }

async def extract_telegram_video_info(url: str, user_id: str = "default") -> Dict[str, Any]:
    """
    High-speed asynchronous video metadata extractor with optional Proxy support.
    """
    validation = validate_and_normalize_telegram_url(url)
    if not validation["valid"]:
        return {"success": False, "error": validation["error"]}

    normalized_url = validation["normalized_url"]
    embed_url = validation["embed_url"]
    s_url = validation["s_url"]
    channel = validation["channel"]
    msg_id = validation["msg_id"]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Referer": "https://t.me/"
    }

    # Proxy check (from settings or env)
    proxy_url = get_setting("proxy", user_id=user_id) or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or None

    # Step 1: Parallel scrape of embed_url, s_url, normalized_url, and mirror telegram.dog
    dog_url = f"https://telegram.dog/s/{channel}/{msg_id}"
    client_kwargs = {
        "timeout": 12.0,
        "follow_redirects": True,
        "headers": headers,
        "verify": False
    }
    if proxy_url:
        client_kwargs["proxy"] = proxy_url

    has_timeout = False
    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            scrape_tasks = [
                client.get(embed_url),
                client.get(s_url),
                client.get(dog_url),
                client.get(normalized_url)
            ]
            
            responses = await asyncio.gather(*scrape_tasks, return_exceptions=True)

            for res in responses:
                if isinstance(res, Exception):
                    has_timeout = True
                    continue
                if isinstance(res, httpx.Response) and res.status_code == 200:
                    parsed = parse_telegram_html(res.text, channel, msg_id, normalized_url)
                    if parsed:
                        if parsed.get("restricted"):
                            return {"success": False, "error": parsed["error"]}

                        direct_url = parsed["direct_url"]
                        title = parsed["title"]
                        duration = parsed["duration"]
                        thumbnail = parsed["thumbnail"]

                        # Quick HEAD request for file size (1.5s timeout)
                        filesize = None
                        try:
                            head_res = await client.head(direct_url, timeout=1.5)
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
    except Exception:
        has_timeout = True

    # Step 2: yt-dlp fallback with 12-second timeout
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'nocheckcertificate': True,
        'socket_timeout': 12,
    }
    if proxy_url:
        ydl_opts['proxy'] = proxy_url

    try:
        loop = asyncio.get_event_loop()
        def _run_ytdlp():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(normalized_url, download=False)
        
        info = await asyncio.wait_for(loop.run_in_executor(None, _run_ytdlp), timeout=14.0)
        
        if info and info.get('url'):
            direct_url = info.get('url')
            title = info.get('title') or f"telegram_{channel}_{msg_id}"
            duration = info.get('duration') or 0
            width = info.get('width')
            height = info.get('height')
            filesize = info.get('filesize') or info.get('filesize_approx')
            thumbnail = info.get('thumbnail')
            ext = info.get('ext') or 'mp4'

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
    except Exception:
        pass

    if has_timeout:
        return {
            "success": False,
            "error": "Telegram servers (t.me) are blocked or timed out on your internet network. Please turn on a VPN (e.g. Cloudflare 1.1.1.1 WARP / ProtonVPN) or configure a Proxy."
        }

    return {
        "success": False,
        "error": "No public video stream found for this Telegram link. The post may be restricted, from a private group, or deleted."
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
    safe_title = re.sub(r'[\\/*?:"<>|]', '', title).strip() or f"telegram_{channel}_{msg_id}"
    filename = f"{safe_title}.{ext}"

    resolution_label = "HD"
    if width and height:
        resolution_label = f"{width} × {height}"
    elif height:
        resolution_label = f"{height}p"

    qualities = [{"id": "original", "name": "Original", "is_default": True}]
    source_height = height or 1080
    if source_height >= 1080:
        qualities.append({"id": "1080p", "name": "1080p (Full HD)", "height": 1080})
    if source_height >= 720:
        qualities.append({"id": "720p", "name": "720p (HD)", "height": 720})
    if source_height >= 480:
        qualities.append({"id": "480p", "name": "480p (SD)", "height": 480})
    if source_height >= 360:
        qualities.append({"id": "360p", "name": "360p (Low)", "height": 360})

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
