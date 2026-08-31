import os
import re
import time
import uuid
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List
import httpx
import aiofiles

from backend.config import TEMP_DIR
from backend.database import get_setting, add_history_item
from backend.ffmpeg_utils import is_ffmpeg_available, process_video_ffmpeg

def sanitize_filename(filename: str) -> str:
    """
    Sanitizes string to be valid Windows filename and prevents path traversal.
    """
    # Strip invalid Windows filename characters
    cleaned = re.sub(r'[\\/*?:"<>|]', '_', filename)
    # Remove leading/trailing periods or spaces
    cleaned = cleaned.strip('. ')
    if not cleaned:
        cleaned = "telegram_video"
    # Ensure reasonable length
    if len(cleaned) > 120:
        base, ext = os.path.splitext(cleaned)
        cleaned = base[:110] + ext
    return cleaned

def get_unique_filepath(directory: Path, filename: str) -> Path:
    """
    Ensures safe unique filename without overwriting existing files:
    e.g., video.mp4 -> video (1).mp4 -> video (2).mp4
    """
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    if not target.exists():
        return target

    base = target.stem
    ext = target.suffix
    counter = 1
    while True:
        new_filename = f"{base} ({counter}){ext}"
        new_target = directory / new_filename
        if not new_target.exists():
            return new_target
        counter += 1

def format_bytes(size_bytes: Optional[int]) -> str:
    if not size_bytes or size_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {units[i]}"

def format_eta(seconds: Optional[int]) -> str:
    if seconds is None or seconds < 0 or seconds > 86400:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

class DownloadTask:
    def __init__(
        self,
        task_id: str,
        source_url: str,
        direct_url: str,
        title: str,
        filename: str,
        quality: str = "original",
        preset: str = "balanced",
        total_bytes: int = 0,
        duration: int = 0,
        resolution: str = "",
        user_id: str = "default",
        custom_settings: Optional[Dict[str, Any]] = None
    ):
        self.id = task_id
        self.user_id = user_id or "default"
        self.source_url = source_url
        self.direct_url = direct_url
        self.title = title
        self.filename = sanitize_filename(filename)
        self.quality = quality
        self.preset = preset
        self.total_bytes = total_bytes
        self.duration = duration
        self.resolution = resolution
        self.custom_settings = custom_settings or {}

        # Runtime status
        self.status = "queued" # queued, downloading, processing, completed, paused, cancelled, failed
        self.downloaded_bytes = 0
        self.progress_percent = 0.0
        self.speed = 0.0 # bytes/sec
        self.eta = None # seconds
        self.error_message: Optional[str] = None
        self.final_filepath: Optional[str] = None
        self.created_at = time.time()
        self.completed_at: Optional[float] = None

        # Internal control
        self.temp_filepath = TEMP_DIR / f"{self.id}_{self.filename}"
        self._cancel_requested = False
        self._pause_requested = False
        self._async_task: Optional[asyncio.Task] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "filename": self.filename,
            "source_url": self.source_url,
            "quality": self.quality,
            "preset": self.preset,
            "status": self.status,
            "progress_percent": round(self.progress_percent, 1),
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "formatted_downloaded": format_bytes(self.downloaded_bytes),
            "formatted_total": format_bytes(self.total_bytes) if self.total_bytes > 0 else "Unknown",
            "speed": self.speed,
            "formatted_speed": f"{format_bytes(int(self.speed))}/s" if self.speed > 0 else "0 B/s",
            "eta": self.eta,
            "formatted_eta": format_eta(self.eta),
            "error_message": self.error_message,
            "final_filepath": self.final_filepath,
            "created_at": self.created_at,
            "duration": self.duration,
            "resolution": self.resolution
        }

class DownloadManager:
    def __init__(self):
        self.tasks: Dict[str, DownloadTask] = {}
        self.queue: asyncio.Queue = asyncio.Queue()
        self.worker_tasks: List[asyncio.Task] = []
        self._running = False

    def start(self):
        if not self._running:
            self._running = True
            # Spawn worker loop
            max_workers = int(get_setting("max_concurrent_downloads", "3"))
            for _ in range(max_workers):
                self.worker_tasks.append(asyncio.create_task(self._worker_loop()))

    async def _worker_loop(self):
        while self._running:
            try:
                task = await self.queue.get()
                if task.id in self.tasks and task.status == "queued":
                    await self._execute_download(task)
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    def create_task(
        self,
        source_url: str,
        direct_url: str,
        title: str,
        filename: str,
        quality: str = "original",
        preset: str = "balanced",
        total_bytes: int = 0,
        duration: int = 0,
        resolution: str = "",
        user_id: str = "default",
        custom_settings: Optional[Dict[str, Any]] = None
    ) -> DownloadTask:
        task_id = str(uuid.uuid4())[:8]
        task = DownloadTask(
            task_id=task_id,
            source_url=source_url,
            direct_url=direct_url,
            title=title,
            filename=filename,
            quality=quality,
            preset=preset,
            total_bytes=total_bytes,
            duration=duration,
            resolution=resolution,
            user_id=user_id,
            custom_settings=custom_settings
        )
        self.tasks[task_id] = task
        self.queue.put_nowait(task)
        return task

    async def _execute_download(self, task: DownloadTask):
        task.status = "downloading"
        task._cancel_requested = False
        task._pause_requested = False

        download_dir_str = get_setting("download_dir") or str(Path.home() / "Downloads")
        download_dir = Path(download_dir_str)
        download_dir.mkdir(parents=True, exist_ok=True)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "*/*"
        }

        # Check existing partial downloaded file
        start_byte = 0
        if task.temp_filepath.exists() and task.temp_filepath.stat().st_size > 0:
            start_byte = task.temp_filepath.stat().st_size
            task.downloaded_bytes = start_byte
            headers["Range"] = f"bytes={start_byte}-"

        try:
            proxy_url = get_setting("proxy", user_id=task.user_id) or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or None
            client_kwargs = {"timeout": 30.0, "follow_redirects": True}
            if proxy_url:
                client_kwargs["proxy"] = proxy_url

            async with httpx.AsyncClient(**client_kwargs) as client:
                async with client.stream("GET", task.direct_url, headers=headers) as response:
                    # Handle Range headers
                    if response.status_code == 206: # Partial Content
                        content_range = response.headers.get("Content-Range")
                        if content_range and "/" in content_range:
                            task.total_bytes = int(content_range.split("/")[1])
                    elif response.status_code == 200:
                        # Server does not support resume, restart from 0
                        start_byte = 0
                        task.downloaded_bytes = 0
                        cl = response.headers.get("Content-Length")
                        if cl and cl.isdigit():
                            task.total_bytes = int(cl)
                    else:
                        raise RuntimeError(f"Server returned HTTP {response.status_code}")

                    file_mode = "ab" if start_byte > 0 else "wb"
                    last_time = time.time()
                    bytes_since_last = 0

                    async with aiofiles.open(task.temp_filepath, file_mode) as f:
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            if task._cancel_requested:
                                task.status = "cancelled"
                                break
                            if task._pause_requested:
                                task.status = "paused"
                                break

                            await f.write(chunk)
                            task.downloaded_bytes += len(chunk)
                            bytes_since_last += len(chunk)

                            # Calculate speed & ETA every 0.5s
                            current_time = time.time()
                            elapsed = current_time - last_time
                            if elapsed >= 0.5:
                                task.speed = bytes_since_last / elapsed
                                if task.total_bytes > 0:
                                    task.progress_percent = min(100.0, (task.downloaded_bytes / task.total_bytes) * 100)
                                    remaining_bytes = max(0, task.total_bytes - task.downloaded_bytes)
                                    if task.speed > 0:
                                        task.eta = int(remaining_bytes / task.speed)
                                else:
                                    task.progress_percent = 50.0 # Indeterminate

                                last_time = current_time
                                bytes_since_last = 0

            # Handle post-download or pause/cancel
            if task.status in ["paused", "cancelled"]:
                if task.status == "cancelled" and task.temp_filepath.exists():
                    try:
                        task.temp_filepath.unlink()
                    except Exception:
                        pass
                return

            # Download completed to temp file
            task.progress_percent = 100.0
            task.speed = 0
            task.eta = 0

            # Determine whether FFmpeg post-processing / compression is needed
            needs_ffmpeg = (task.quality != "original") or (task.preset in ["balanced", "smallest"])
            final_target_path = get_unique_filepath(download_dir, task.filename)

            if needs_ffmpeg and is_ffmpeg_available():
                task.status = "processing"
                processed_temp = TEMP_DIR / f"proc_{task.id}_{task.filename}"
                
                await process_video_ffmpeg(
                    input_path=str(task.temp_filepath),
                    output_path=str(processed_temp),
                    target_resolution=task.quality if task.quality != "original" else None,
                    preset=task.preset,
                    custom_crf=task.custom_settings.get("crf"),
                    custom_fps=task.custom_settings.get("fps")
                )

                # Move processed file to destination
                if task.temp_filepath.exists():
                    task.temp_filepath.unlink()
                if processed_temp.exists():
                    import shutil
                    shutil.move(str(processed_temp), str(final_target_path))
            else:
                # Direct move original without re-encoding
                import shutil
                shutil.move(str(task.temp_filepath), str(final_target_path))

            task.final_filepath = str(final_target_path)
            task.status = "completed"
            task.completed_at = time.time()

            # Record in SQLite history
            actual_size = final_target_path.stat().st_size if final_target_path.exists() else task.downloaded_bytes
            add_history_item({
                "id": task.id,
                "title": task.title,
                "filename": final_target_path.name,
                "file_path": str(final_target_path),
                "source_url": task.source_url,
                "file_size": actual_size,
                "formatted_size": format_bytes(actual_size),
                "duration": task.duration,
                "resolution": task.resolution or (task.quality if task.quality != "original" else "Original"),
                "quality": task.quality,
                "status": "completed"
            }, user_id=task.user_id)

        except Exception as e:
            if not task._cancel_requested:
                task.status = "failed"
                task.error_message = f"Download error: {str(e)}"
            if task.temp_filepath.exists() and task.status == "failed":
                try:
                    task.temp_filepath.unlink()
                except Exception:
                    pass

    def pause_task(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)
        if task and task.status == "downloading":
            task._pause_requested = True
            return True
        return False

    def resume_task(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)
        if task and task.status in ["paused", "failed"]:
            task.status = "queued"
            task._pause_requested = False
            task._cancel_requested = False
            self.queue.put_nowait(task)
            return True
        return False

    def cancel_task(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)
        if task:
            task._cancel_requested = True
            task.status = "cancelled"
            if task.temp_filepath.exists():
                try:
                    task.temp_filepath.unlink()
                except Exception:
                    pass
            return True
        return False

    def retry_task(self, task_id: str) -> bool:
        return self.resume_task(task_id)

    def delete_task(self, task_id: str) -> bool:
        self.cancel_task(task_id)
        if task_id in self.tasks:
            del self.tasks[task_id]
            return True
        return False

# Global instance
manager = DownloadManager()
