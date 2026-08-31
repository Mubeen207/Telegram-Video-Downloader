import sys
import os
import socket
import webbrowser
import threading
import time
import uvicorn

def is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0

def find_available_port(host: str, start_port: int = 8000, max_attempts: int = 10) -> int:
    port = start_port
    for _ in range(max_attempts):
        if not is_port_in_use(host, port):
            return port
        port += 1
    return start_port

def open_browser_delayed(url: str, delay: float = 1.2):
    def _open():
        time.sleep(delay)
        webbrowser.open(url)
    t = threading.Thread(target=_open, daemon=True)
    t.start()

def main():
    host = os.environ.get("HOST", "127.0.0.1")
    requested_port = int(os.environ.get("PORT", 8000))
    port = find_available_port(host, requested_port)
    
    url = f"http://localhost:{port}"
    
    print("=" * 60)
    print("  TeleStream - Telegram Video Downloader")
    print(f"  Server URL : {url}")
    print(f"  Auth Mode  : Firebase Google Authentication")
    print("=" * 60)

    # Open browser automatically if not in headless or no-browser mode
    if "--no-browser" not in sys.argv:
        open_browser_delayed(url)

    uvicorn.run("backend.main:app", host=host, port=port, log_level="info", reload=False)

if __name__ == "__main__":
    main()
