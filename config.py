import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "output"

# Create necessary directories
TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Default processing settings
DEFAULT_MAX_DURATION_SEC = 3600  # 1 hour max video processing limit

# yt-dlp cookies (Netscape cookies.txt format) used to pass YouTube's region & bot checks.
cookies_text = os.getenv("YTDLP_COOKIES_TEXT")
if cookies_text:
    cookies_path = TEMP_DIR / "cookies.txt"
    with open(cookies_path, "w", encoding="utf-8") as f:
        f.write(cookies_text.strip())
    YTDLP_COOKIES_FILE = str(cookies_path)
else:
    YTDLP_COOKIES_FILE = os.getenv("YTDLP_COOKIES_FILE") or next(
        (p for p in ("/etc/secrets/cookies.txt", str(BASE_DIR / "cookies.txt")) if os.path.exists(p)),
        None,
    )

if YTDLP_COOKIES_FILE:
    print(f"[config] Using yt-dlp cookies file: {YTDLP_COOKIES_FILE} ({os.path.getsize(YTDLP_COOKIES_FILE)} bytes)")
else:
    print("[config] No yt-dlp cookies file found (checked YTDLP_COOKIES_TEXT env, YTDLP_COOKIES_FILE env, /etc/secrets/cookies.txt, ./cookies.txt)")

