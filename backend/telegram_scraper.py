import re
import math
from typing import Dict, Any, Optional, List
import httpx
from bs4 import BeautifulSoup
import yt_dlp

def validate_and_normalize_telegram_url(url: str) -> Dict[str, Any]:
    """
    Validates Telegram link and extracts channel/post information.
    Supports standard messages, forwarded messages, non-forwarded messages,
    topic threads (t.me/channel/topic_id/msg_id), and URLs with query parameters.
    """
    url = url.strip()
    if not url:
        return {"valid": False, "error": "Please provide a Telegram video link."}

    # Match private channel/group links (e.g. t.me/c/123456/789)
    private_pattern = r"(?:https?:\/\/)?(?:www\.)?(?:t\.me|telegram\.me)\/c\/(\d+)\/(\d+)"
    if re.search(private_pattern, url):
        return {
            "valid": False,
            "error": "This Telegram link is from a private channel/group and is not publicly accessible without authentication."
        }

    # Match public telegram post patterns including topic threads:
    # https://t.me/channel_name/123
    # https://t.me/channel_name/topic_id/123
    # https://t.me/s/channel_name/123
    # https://telegram.me/channel_name/123
    public_pattern = r"(?:https?:\/\/)?(?:www\.)?(?:t\.me|telegram\.me)\/(?:s\/)?([a-zA-Z0-9_+]+)(?:\/\d+)?\/(\d+)"
    match = re.search(public_pattern, url)
    
    if not match:
        # Fallback simple channel/id match
        simple_pattern = r"(?:https?:\/\/)?(?:www\.)?(?:t\.me|telegram\.me)\/(?:s\/)?([a-zA-Z0-9_+]+)\/(\d+)"
        match = re.search(simple_pattern, url)

    if not match:
        return {
            "valid": False,
            "error": "Invalid Telegram link format. Please provide a link like: https://t.me/channel_name/123"
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

async def extract_telegram_video_info(url: str) -> Dict[str, Any]:
    """
    Extracts video metadata from public Telegram URL (both forwarded and non-forwarded videos,
    video notes, document video files, and channel posts).
    """
    validation = validate_and_normalize_telegram_url(url)
    if not validation["valid"]:
        return {"success": False, "error": validation["error"]}

    normalized_url = validation["normalized_url"]
    embed_url = validation["embed_url"]
    s_url = validation.get("s_url", f"https://t.me/s/{validation['channel']}/{validation['msg_id']}")
    channel = validation["channel"]
    msg_id = validation["msg_id"]

    # 1. Primary extraction using yt-dlp
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
            
            if info and info.get('url'):
                direct_url = info.get('url')
                title = info.get('title') or f"telegram_{channel}_{msg_id}"
                duration = info.get('duration') or 0
                width = info.get('width')
                height = info.get('height')
                filesize = info.get('filesize') or info.get('filesize_approx')
                thumbnail = info.get('thumbnail')
                ext = info.get('ext') or 'mp4'

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
    except Exception:
        pass

    # 2. Fallback: Direct Scraping of Telegram Web Embed and Public Channel Preview
    msg_num = int(msg_id) if msg_id.isdigit() else 0
    urls_to_try = [
        embed_url,
        s_url,
        normalized_url
    ]
    if msg_num > 0:
        urls_to_try.insert(2, f"https://t.me/s/{channel}?before={msg_num + 2}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://t.me/"
    }

    last_error = "No public video found at this Telegram URL. The media might be in a private channel, restricted group, or deleted."
    post_has_restricted_media = False

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers, verify=False) as client:
        for target_scrape_url in urls_to_try:
            try:
                res = await client.get(target_scrape_url)
                if res.status_code != 200:
                    continue

                html = res.text
                soup = BeautifulSoup(html, "html.parser")

                # Check for Telegram restriction / error notices
                error_el = soup.select_one(".tgme_widget_message_error")
                if error_el:
                    error_text = error_el.get_text(strip=True).lower()
                    if any(w in error_text for w in ["restrict", "protected", "private", "access denied", "forbidden", "saving"]):
                        return {
                            "success": False,
                            "error": "This Telegram post has content protection enabled ('Restrict Saving Content'). Media cannot be fetched from restricted channels."
                        }
                    if "not found" in error_text:
                        last_error = "Telegram post not found. Check if the message link is correct."
                        continue
                    last_error = f"Telegram restriction: {error_el.get_text(strip=True)}"
                    continue

                # Target specific post container if searching timeline
                target_container = soup.select_one(f'[data-post="{channel}/{msg_id}"]') or soup

                # Check if post exists and shows signs of media/video while suppressing direct <video> stream
                has_message_bubble = bool(target_container.select_one(".tgme_widget_message, .tgme_widget_message_bubble, .tgme_widget_message_wrap"))
                has_video_placeholder = bool(target_container.select_one(".tgme_widget_message_video_thumb, .tgme_widget_message_video_player, .tgme_widget_message_roundvideo_thumb, .message_media_not_supported"))

                # Strategy A: DOM video element search
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

                # Strategy B: Document video attachment
                if not direct_url:
                    doc_video = target_container.select_one(
                        "a.tgme_widget_message_document_wrap[href*='.mp4'], "
                        "a.tgme_widget_message_document_wrap[href*='.mkv'], "
                        "a.tgme_widget_message_document_wrap[href*='.mov'], "
                        "a.tgme_widget_message_document_wrap[href*='.webm']"
                    )
                    if doc_video:
                        direct_url = doc_video.get("href")

                # Strategy C: Deep Regex Search in HTML payload for direct CDN video streams
                if not direct_url:
                    video_url_matches = re.findall(
                        r'(https?:\/\/[^"\'\s<>]+\.(?:mp4|m4v|mov|webm)(?:\?[^"\'\s<>]*)?)',
                        html
                    )
                    if video_url_matches:
                        for match_url in video_url_matches:
                            if "telegram" in match_url or "telesco.pe" in match_url or "cdn" in match_url:
                                direct_url = match_url
                                break
                        if not direct_url and video_url_matches:
                            direct_url = video_url_matches[0]

                # Strategy D: Check telesco.pe video notes
                if not direct_url:
                    telescope_match = re.search(r'(https?:\/\/telesco\.pe\/[^"\'\s<>]+\.mp4)', html)
                    if telescope_match:
                        direct_url = telescope_match.group(1)

                # Fix relative URLs if any
                if direct_url:
                    if direct_url.startswith("//"):
                        direct_url = "https:" + direct_url
                    elif direct_url.startswith("/") and not direct_url.startswith("http"):
                        direct_url = "https://t.me" + direct_url

                if not direct_url:
                    # If the message exists and contains media indicator but direct stream was blocked
                    if has_message_bubble and has_video_placeholder:
                        post_has_restricted_media = True

                    photo_el = target_container.select_one(".tgme_widget_message_photo_wrap")
                    if photo_el:
                        last_error = "This Telegram post contains a photo/image, not a video."
                    continue

                # Extract thumbnail
                thumbnail = None
                thumb_el = target_container.select_one(
                    ".tgme_widget_message_video_thumb, "
                    ".tgme_widget_message_roundvideo_thumb, "
                    ".tgme_widget_message_photo_wrap"
                )
                if thumb_el and "style" in thumb_el.attrs:
                    style = thumb_el["style"]
                    match = re.search(r"background-image:\s*url\(['\"]?(.*?)['\"]?\)", style)
                    if match:
                        thumbnail = match.group(1)

                # Extract duration
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

                # Extract message text as title
                text_el = target_container.select_one(".tgme_widget_message_text")
                title = text_el.get_text(strip=True)[:60] if text_el else f"Telegram_{channel}_{msg_id}"
                if not title:
                    title = f"Telegram_{channel}_{msg_id}"

                # Query Content-Length via HEAD request
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
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException) as ex:
                last_error = "Connection to Telegram (t.me) timed out. Telegram servers may be restricted or blocked by your ISP/network. Try enabling a VPN or checking your internet connection."
                continue
            except Exception as ex:
                continue

    if post_has_restricted_media:
        return {
            "success": False,
            "error": "This Telegram post has content protection enabled ('Restrict Saving Content'). Media cannot be fetched from restricted channels."
        }

    return {
        "success": False,
        "error": last_error
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
