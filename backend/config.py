import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TEMP_DIR = DATA_DIR / "temp"

# Default Downloads Folder (Windows Downloads or fallback to User directory / downloads)
def get_default_download_dir() -> str:
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        win_downloads = Path(user_profile) / "Downloads"
        if win_downloads.exists():
            return str(win_downloads)
    return str(BASE_DIR / "downloads")

# Ensure required directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
Path(get_default_download_dir()).mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "downloader.db"
