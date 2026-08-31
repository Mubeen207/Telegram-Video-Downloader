import os
import shutil
import subprocess
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Callable

# Check for ffmpeg binary
def get_ffmpeg_path() -> Optional[str]:
    # Check PATH
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        return ffmpeg_bin
    
    # Check common Windows locations / local bin
    local_bin = Path(__file__).resolve().parent.parent / "bin" / "ffmpeg.exe"
    if local_bin.exists():
        return str(local_bin)
        
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        winget_path = Path(local_app_data) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
        if winget_path.exists():
            return str(winget_path)
            
    program_files = os.environ.get("ProgramFiles", "")
    if program_files:
        common_ffmpeg = Path(program_files) / "ffmpeg" / "bin" / "ffmpeg.exe"
        if common_ffmpeg.exists():
            return str(common_ffmpeg)

    return None

def is_ffmpeg_available() -> bool:
    return get_ffmpeg_path() is not None

def get_ffmpeg_version_info() -> Dict[str, Any]:
    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        return {"available": False, "version": None, "path": None}
    try:
        output = subprocess.check_output([ffmpeg_path, "-version"], stderr=subprocess.STDOUT, text=True)
        first_line = output.splitlines()[0] if output.splitlines() else "ffmpeg version unknown"
        return {"available": True, "version": first_line, "path": ffmpeg_path}
    except Exception as e:
        return {"available": False, "version": None, "error": str(e)}

async def process_video_ffmpeg(
    input_path: str,
    output_path: str,
    target_resolution: Optional[str] = None, # e.g. "1080p", "720p", "480p", "360p"
    preset: str = "balanced", # "best", "balanced", "smallest"
    video_codec: str = "libx264",
    audio_codec: str = "aac",
    custom_crf: Optional[int] = None,
    custom_fps: Optional[int] = None,
    progress_callback: Optional[Callable[[float], None]] = None
) -> bool:
    """
    Process video using FFmpeg with resolution scaling and compression presets.
    """
    ffmpeg_bin = get_ffmpeg_path()
    if not ffmpeg_bin:
        raise RuntimeError("FFmpeg is not installed or not found on the system.")

    # Target resolution mapping (height)
    height_map = {
        "1080p": 1080,
        "720p": 720,
        "480p": 480,
        "360p": 360
    }

    # Preset configurations: CRF & x264 preset
    preset_configs = {
        "best": {"crf": 18, "preset": "slow", "audio_bitrate": "192k"},
        "balanced": {"crf": 23, "preset": "medium", "audio_bitrate": "128k"},
        "smallest": {"crf": 28, "preset": "fast", "audio_bitrate": "96k"}
    }
    
    cfg = preset_configs.get(preset.lower(), preset_configs["balanced"])
    crf = custom_crf if custom_crf is not None else cfg["crf"]
    
    vf_filters = []
    if target_resolution and target_resolution in height_map:
        target_h = height_map[target_resolution]
        # Keep aspect ratio and ensure even dimensions for h264
        vf_filters.append(f"scale=-2:{target_h}")

    if custom_fps:
        vf_filters.append(f"fps={custom_fps}")

    cmd = [
        ffmpeg_bin,
        "-y", # Overwrite output
        "-i", input_path,
        "-c:v", video_codec,
        "-preset", cfg["preset"],
        "-crf", str(crf),
        "-c:a", audio_codec,
        "-b:a", cfg["audio_bitrate"],
        "-movflags", "+faststart"
    ]

    if vf_filters:
        cmd.extend(["-vf", ",".join(vf_filters)])

    cmd.append(output_path)

    # Run FFmpeg asynchronously
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        err_msg = stderr.decode('utf-8', errors='ignore')
        raise RuntimeError(f"FFmpeg processing failed: {err_msg[:400]}")

    return True
