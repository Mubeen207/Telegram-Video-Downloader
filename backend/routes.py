import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from backend.telegram_scraper import extract_telegram_video_info
from backend.downloader import manager
from backend.database import (
    get_all_settings, save_setting, get_history,
    delete_history_item, clear_all_history, get_setting
)
from backend.ffmpeg_utils import get_ffmpeg_version_info, is_ffmpeg_available

router = APIRouter(prefix="/api")

# Pydantic models for request validation
class AnalyzeRequest(BaseModel):
    url: str = Field(..., description="Telegram video post URL")

class DownloadRequest(BaseModel):
    source_url: str
    direct_url: str
    title: str
    filename: str
    quality: str = "original"
    preset: str = "balanced"
    total_bytes: Optional[int] = 0
    duration: Optional[int] = 0
    resolution: Optional[str] = ""
    custom_settings: Optional[Dict[str, Any]] = None

class SettingsUpdateRequest(BaseModel):
    settings: Dict[str, str]

class OpenFolderRequest(BaseModel):
    path: Optional[str] = None

@router.post("/analyze")
async def analyze_url(req: AnalyzeRequest):
    result = await extract_telegram_video_info(req.url)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Unable to analyze Telegram video link."))
    return result

@router.post("/download")
async def create_download(req: DownloadRequest):
    # Ensure manager worker loops are active
    manager.start()

    task = manager.create_task(
        source_url=req.source_url,
        direct_url=req.direct_url,
        title=req.title,
        filename=req.filename,
        quality=req.quality,
        preset=req.preset,
        total_bytes=req.total_bytes or 0,
        duration=req.duration or 0,
        resolution=req.resolution or "",
        custom_settings=req.custom_settings
    )
    return {"success": True, "task": task.to_dict()}

@router.get("/downloads")
async def get_all_downloads():
    tasks = [task.to_dict() for task in manager.tasks.values()]
    # Return reverse chronological order
    tasks.sort(key=lambda t: t.get("created_at", 0), reverse=True)
    return {"tasks": tasks}

@router.post("/downloads/{task_id}/pause")
async def pause_download(task_id: str):
    success = manager.pause_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot pause this download task.")
    return {"success": True}

@router.post("/downloads/{task_id}/resume")
async def resume_download(task_id: str):
    success = manager.resume_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot resume this download task.")
    return {"success": True}

@router.post("/downloads/{task_id}/retry")
async def retry_download(task_id: str):
    success = manager.retry_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot retry this download task.")
    return {"success": True}

@router.post("/downloads/{task_id}/cancel")
async def cancel_download(task_id: str):
    success = manager.cancel_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel this download task.")
    return {"success": True}

@router.delete("/downloads/{task_id}")
async def delete_download(task_id: str):
    success = manager.delete_task(task_id)
    return {"success": success}

# History endpoints
@router.get("/history")
async def fetch_history():
    items = get_history()
    return {"history": items}

@router.delete("/history/{item_id}")
async def remove_history_item(item_id: str):
    delete_history_item(item_id)
    return {"success": True}

@router.delete("/history")
async def clear_history():
    clear_all_history()
    return {"success": True}

# Settings endpoints
@router.get("/settings")
async def fetch_settings():
    settings = get_all_settings()
    return {"settings": settings}

@router.post("/settings")
async def update_settings(req: SettingsUpdateRequest):
    for k, v in req.settings.items():
        save_setting(k, str(v))
    return {"success": True, "settings": get_all_settings()}

# System status endpoint
@router.get("/system/status")
async def system_status():
    ffmpeg_info = get_ffmpeg_version_info()
    download_dir = get_setting("download_dir")
    return {
        "ffmpeg": ffmpeg_info,
        "download_dir": download_dir,
        "os": "Windows"
    }

# Open download folder in Windows Explorer
@router.post("/open-folder")
async def open_download_folder(req: OpenFolderRequest):
    folder_path = req.path or get_setting("download_dir")
    if not folder_path:
        raise HTTPException(status_code=400, detail="Download directory is not set.")
    
    target = Path(folder_path)
    if not target.exists():
        target.mkdir(parents=True, exist_ok=True)

    try:
        if os.name == 'nt':
            os.startfile(str(target))
        else:
            subprocess.Popen(["xdg-open", str(target)])
        return {"success": True, "opened": str(target)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open directory: {str(e)}")
