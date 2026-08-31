# 🎬 TeleStream - Telegram Video Downloader with Firebase Google Auth

**TeleStream** is a lightweight, web-only application designed to analyze and download publicly available Telegram videos directly through your web browser with secure **Firebase Google Authentication**.

---

## ✨ Features

- **Firebase Google Sign-In**: Seamless authentication with your Google account via Firebase Auth (`maintainiq-e33d4`).
- **Zero Subscription / Zero Paywalls**: No pricing tiers, no credit limits, no license activations. Every authenticated user gets full access.
- **User-Isolated Storage**: Individual download history and settings are tied securely to the user's Firebase UID.
- **Dynamic Quality Selector**: Accurately displays source video resolutions (`Original`, `1080p`, `720p`, `480p`, `360p`) without artificial upscaling.
- **FFmpeg Size & Compression Presets**:
  - `Best Quality`: Direct stream with minimal loss.
  - `Balanced`: H.264 compression saving ~50% disk space while preserving visual quality.
  - `Smallest Size`: High-efficiency compression for low-bandwidth / storage constraints.
- **Asynchronous Download Queue**: Multi-task download manager with live speed, ETA countdown, chunk streaming, Pause, Resume, Retry, and Cancel.
- **Modern Responsive UI**: Dark & Light mode themes, glassmorphism cards, and instant toast notifications.

---

## 🔐 Firebase Authentication Setup

### 1. Frontend Configuration
The frontend connects directly to your Firebase project (`maintainiq-e33d4`) using Firebase Web SDK 10.x. Google Sign-In is initialized in [`static/js/firebase-config.js`](file:///d:/Telegram-Video-Downloader/static/js/firebase-config.js).

### 2. Backend Token Verification (Firebase Admin SDK)
The FastAPI backend verifies incoming Firebase ID tokens sent in the `Authorization: Bearer <ID_TOKEN>` header.

To configure private backend Admin credentials:
1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Set your `FIREBASE_SERVICE_ACCOUNT` path or JSON string in `.env`:
   ```env
   FIREBASE_PROJECT_ID=maintainiq-e33d4
   FIREBASE_SERVICE_ACCOUNT=./service-account.json
   ```
*(Never commit your private service-account credentials to Git. `.gitignore` is preconfigured to prevent accidental commits).*

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

The application starts on **`http://127.0.0.1:8000`** and automatically opens in your default browser (Google Chrome).

---

## 📱 User Workflow

```text
1. Open http://127.0.0.1:8000
       ↓
2. Click "Continue with Google"
       ↓
3. Paste public Telegram Video URL (e.g. https://t.me/channel/123)
       ↓
4. Select Quality / Compression Preset
       ↓
5. Download and track live progress
```

---

## ⚡ Supported Telegram URL Formats

- `https://t.me/channel_name/123`
- `https://t.me/channel_name/123?single`
- `https://telegram.me/channel_name/123`
- `https://t.me/s/channel_name/123`
- Supergroup topic threads: `https://t.me/channel_name/topic_id/123`

---

## ⚠️ Known Limitations & Responsible Use

- **Public Channels Only**: The media must be in a publicly accessible Telegram channel or group.
- **Content Protection**: Channels with "Restrict Saving Content" or private invite restrictions (`t.me/c/...`) cannot be retrieved. TeleStream reports these restrictions cleanly.
