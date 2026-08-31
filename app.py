import sys
import os
import webbrowser
import threading
import time
import uvicorn

def open_browser_delayed(url: str, delay: float = 1.2):
    def _open():
        time.sleep(delay)
        webbrowser.open(url)
    t = threading.Thread(target=_open, daemon=True)
    t.start()

def main():
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "127.0.0.1")
    url = f"http://{host}:{port}"
    
    print("=" * 60)
    print("  Telegram Video Downloader - Web Application")
    print(f"  Server URL : {url}")
    print(f"  Status     : Ready (No Telegram Login Required)")
    print("=" * 60)

    # Open browser automatically if not in headless or no-browser mode
    if "--no-browser" not in sys.argv:
        open_browser_delayed(url)

    uvicorn.run("backend.main:app", host=host, port=port, log_level="info", reload=False)

if __name__ == "__main__":
    main()
