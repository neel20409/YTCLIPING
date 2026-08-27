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

# yt-dlp cookies (Netscape cookies.txt format) used to pass YouTube's "sign in to
# confirm you're not a bot" challenge, which cloud/datacenter IPs trigger even for
# plain metadata requests. Never committed to git — supplied at runtime as a Render
# Secret File (mounted under /etc/secrets/) or a local, gitignored file for testing.
YTDLP_COOKIES_FILE = os.getenv("YTDLP_COOKIES_FILE") or next(
    (p for p in ("/etc/secrets/cookies.txt", str(BASE_DIR / "cookies.txt")) if os.path.exists(p)),
    None,
)
