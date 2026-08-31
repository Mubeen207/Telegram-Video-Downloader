# 🎬 Telegram Video Downloader

A modern, fast, and lightweight web application to download public Telegram videos directly without needing a Telegram account, phone number, OTP, or session login.

---

## ✨ Key Features

- **Zero Credentials / No Login**: No Telegram phone number, 2FA, OTP, or QR login needed. Directly analyzes and downloads public Telegram video links.
- **Dynamic Quality Selection**: Shows actual source resolutions (`Original`, `1080p`, `720p`, `480p`, `360p`) without claiming fake upscaled options.
- **Size & Compression Presets**:
  - `Best Quality` (Original stream / minimal loss)
  - `Balanced` (~50% size reduction with H.264 optimization)
  - `Smallest Size` (Maximum compression for tight bandwidth/storage)
- **Advanced Options**: Custom CRF, target FPS, container format (MP4/MKV), and filename sanitization.
- **Multi-Task Download Queue**: Real-time progress bar, percent, download speed, ETA, pause, resume, retry, and cancellation.
- **Local Download History**: SQLite-backed history tracking with search, clear, and one-click open in Windows Explorer.
- **Modern Responsive UI**: Dark & Light mode, glassmorphism aesthetics, responsive layouts, and instant toast notifications.
- **Windows Optimized**: Path sanitization, collision renaming (`video (1).mp4`), and Explorer integration.

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Start Application
```bash
python app.py
```
*(Or double-click `run.bat` on Windows)*

The application will start on **`http://127.0.0.1:8000`** and automatically open in your default browser (e.g. Google Chrome).

---

## ⚡ Supported URL Formats

- `https://t.me/channel_name/123`
- `https://t.me/channel_name/123?single`
- `https://telegram.me/channel_name/123`
- `https://t.me/s/channel_name/123`

---

## 🛠️ Technology Stack

- **Backend**: Python 3.12, FastAPI, Uvicorn, yt-dlp, HTTPX, AsyncIO, SQLite
- **Video Processing**: FFmpeg integration (optional for compression/transcoding; direct stream for original)
- **Frontend**: Modern Vanilla JS, HTML5, CSS3 with dynamic theme switching and glassmorphism styling
