# 🎬 TeleStream - Web Video Downloader

**TeleStream** is a lightweight, high-performance, web-only application designed to analyze and download publicly available Telegram videos directly through your web browser without requiring a Telegram account, login, or any browser extensions.

---

## ✨ Features

- **Web-Only & Zero Auth**: Operates completely in a standard browser (e.g. Google Chrome at `http://127.0.0.1:8000`). No extensions, logins, OTPs, or API keys needed.
- **Dynamic Quality Selector**: Accurately displays source video resolutions (`Original`, `1080p`, `720p`, `480p`, `360p`) without artificial upscaling.
- **FFmpeg Size & Compression Presets**:
  - `Best Quality`: Near-lossless direct download with light container packaging.
  - `Balanced`: H.264 compression saving ~50% disk space while preserving visual quality.
  - `Smallest Size`: High-efficiency compression for low-bandwidth / storage constraints.
- **Advanced Encoding Options**: Customizable CRF (Constant Rate Factor), FPS limiting, and MP4/MKV format selectors.
- **Asynchronous Download Manager**: Multi-task download queue with live download speed, ETA countdown, chunk streaming, Pause, Resume, Retry, and Cancel.
- **Local History & Settings**: Persistent SQLite storage for downloaded files with one-click opening in Windows Explorer.
- **Safety & Performance**: Chunk-based streaming prevents loading entire videos into memory; automatic Windows filename sanitization and collision prevention (`video (1).mp4`).
- **Modern UI**: Dark/Light mode, glassmorphic card design, and responsive layouts.

---

## 📋 Requirements

- **Operating System**: Windows 10/11, Linux, or macOS (Windows optimized).
- **Python**: Python 3.10+ (Python 3.12 recommended).
- **Web Browser**: Google Chrome, Microsoft Edge, Firefox, Brave, etc.
- **FFmpeg (Optional)**: Required only if you wish to use compression presets or resolution downscaling. Direct original video downloads work out of the box without FFmpeg.

---

## 📦 Installation

1. **Clone or Open the Repository**:
   ```bash
   cd Telegram-Video-Downloader
   ```

2. **Install Python Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## 🎥 FFmpeg Setup (Optional)

If you want to use the **Balanced** or **Smallest Size** compression presets:

- **Windows (winget)**:
  ```powershell
  winget install Gyan.FFmpeg
  ```
- **Manual**: Download `ffmpeg.exe` from [ffmpeg.org](https://ffmpeg.org/download.html) and either add it to your system `PATH` or place `ffmpeg.exe` inside a `bin/` folder in the project root.

TeleStream automatically detects FFmpeg on startup and indicates its availability in the top-right header and Settings tab.

---

## 🚀 Running the Application

Start the web server with a single command:

```powershell
python app.py
```

*(On Windows, you can also double-click `run.bat`)*

### Browser Usage

Once started, TeleStream will automatically launch in your default web browser at:
```text
http://127.0.0.1:8000
```

### Workflow

1. Paste a public Telegram video URL (e.g. `https://t.me/channel_name/123`).
2. Click **Analyze Video**.
3. View video dimensions, duration, format, and estimated size.
4. Select your preferred resolution quality and compression preset.
5. Click **Download Video**. Progress and speed will be tracked in the **Downloads** queue.

---

## ⚡ Supported Telegram URL Formats

TeleStream supports publicly accessible Telegram post links, including:

- `https://t.me/channel_name/123`
- `https://t.me/channel_name/123?single`
- `https://telegram.me/channel_name/123`
- `https://t.me/s/channel_name/123`
- Supergroup topic threads: `https://t.me/channel_name/topic_id/123`

---

## ⚠️ Known Limitations

- **Public Channels Only**: The media must be hosted in a public Telegram channel or group accessible via Telegram web preview.
- **Protected Content**: Content protected by channel owners with "Restrict Saving Content" or messages requiring membership authentication cannot be retrieved. TeleStream reports these restrictions cleanly.
- **Private Invite Links**: Links containing `t.me/c/...` or `t.me/+joinchat` are private and require user credentials, which TeleStream intentionally does not request or store.

---

## ⚖️ Legal & Responsible Use

TeleStream is designed for downloading public domain, freely shared, or user-owned media from public Telegram channels. Users are responsible for complying with Telegram's Terms of Service and applicable copyright laws in their jurisdiction. Do not use this tool to infringe upon intellectual property rights.
