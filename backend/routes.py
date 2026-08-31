import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from backend.telegram_scraper import extract_telegram_video_info
from backend.downloader import manager
from backend.database import (
    get_all_settings, save_setting, get_history,
    delete_history_item, clear_all_history, get_setting
)
from backend.ffmpeg_utils import get_ffmpeg_version_info, is_ffmpeg_available
from backend.firebase_auth import get_current_user

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

# Public endpoint for system status diagnostics
@router.get("/system/status")
async def system_status():
    ffmpeg_info = get_ffmpeg_version_info()
    download_dir = get_setting("download_dir")
    return {
        "ffmpeg": ffmpeg_info,
        "download_dir": download_dir,
        "os": "Windows",
        "auth": "Firebase Google Auth"
    }

# Protected application endpoints
@router.post("/analyze")
async def analyze_url(
    req: AnalyzeRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    result = await extract_telegram_video_info(req.url)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Unable to analyze Telegram video link."))
    return result

@router.post("/download")
async def create_download(
    req: DownloadRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    manager.start()
    user_id = current_user["uid"]

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
        user_id=user_id,
        custom_settings=req.custom_settings
    )
    return {"success": True, "task": task.to_dict()}

@router.get("/downloads")
async def get_all_downloads(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    user_id = current_user["uid"]
    # Only return tasks belonging to this user
    tasks = [task.to_dict() for task in manager.tasks.values() if task.user_id == user_id]
    tasks.sort(key=lambda t: t.get("created_at", 0), reverse=True)
    return {"tasks": tasks}

@router.post("/downloads/{task_id}/pause")
async def pause_download(
    task_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    task = manager.tasks.get(task_id)
    if not task or task.user_id != current_user["uid"]:
        raise HTTPException(status_code=404, detail="Task not found.")
    success = manager.pause_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot pause this download task.")
    return {"success": True}

@router.post("/downloads/{task_id}/resume")
async def resume_download(
    task_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    task = manager.tasks.get(task_id)
    if not task or task.user_id != current_user["uid"]:
        raise HTTPException(status_code=404, detail="Task not found.")
    success = manager.resume_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot resume this download task.")
    return {"success": True}

@router.post("/downloads/{task_id}/retry")
async def retry_download(
    task_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    task = manager.tasks.get(task_id)
    if not task or task.user_id != current_user["uid"]:
        raise HTTPException(status_code=404, detail="Task not found.")
    success = manager.retry_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot retry this download task.")
    return {"success": True}

@router.post("/downloads/{task_id}/cancel")
async def cancel_download(
    task_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    task = manager.tasks.get(task_id)
    if not task or task.user_id != current_user["uid"]:
        raise HTTPException(status_code=404, detail="Task not found.")
    success = manager.cancel_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel this download task.")
    return {"success": True}

@router.delete("/downloads/{task_id}")
async def delete_download(
    task_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    task = manager.tasks.get(task_id)
    if not task or task.user_id != current_user["uid"]:
        raise HTTPException(status_code=404, detail="Task not found.")
    success = manager.delete_task(task_id)
    return {"success": success}

# History endpoints (User-isolated)
@router.get("/history")
async def fetch_history(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    items = get_history(user_id=current_user["uid"])
    return {"history": items}

@router.delete("/history/{item_id}")
async def remove_history_item(
    item_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    delete_history_item(item_id, user_id=current_user["uid"])
    return {"success": True}

@router.delete("/history")
async def clear_history(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    clear_all_history(user_id=current_user["uid"])
    return {"success": True}

# Settings endpoints (User-isolated)
@router.get("/settings")
async def fetch_settings(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    settings = get_all_settings(user_id=current_user["uid"])
    return {"settings": settings}

@router.post("/settings")
async def update_settings(
    req: SettingsUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    for k, v in req.settings.items():
        save_setting(k, str(v), user_id=current_user["uid"])
    return {"success": True, "settings": get_all_settings(user_id=current_user["uid"])}

# Open download folder in Windows Explorer
@router.post("/open-folder")
async def open_download_folder(
    req: OpenFolderRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    folder_path = req.path or get_setting("download_dir", user_id=current_user["uid"])
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
