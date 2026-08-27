import os
from typing import Optional
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

def _sanitize_cookies(cookie_content: str) -> str:
    """Strip volatile IP-bound session tokens that trigger 'page needs to be reloaded' on cloud IPs."""
    volatile_keys = {"__Secure-1PSIDTS", "__Secure-3PSIDTS", "SIDCC", "__Secure-1PSIDCC", "__Secure-3PSIDCC", "LOGIN_INFO"}
    clean_lines = []
    for line in cookie_content.splitlines():
        if not any(k in line for k in volatile_keys):
            clean_lines.append(line)
    return "\n".join(clean_lines)

# yt-dlp cookies (Netscape cookies.txt format) used to pass YouTube's region & bot checks.
cookies_text = os.getenv("YTDLP_COOKIES_TEXT")
raw_cookie_file = None
if cookies_text:
    raw_cookie_content = cookies_text.strip()
else:
    raw_cookie_file = os.getenv("YTDLP_COOKIES_FILE") or next(
        (p for p in ("/etc/secrets/cookies.txt", str(BASE_DIR / "cookies.txt")) if os.path.exists(p)),
        None,
    )
    if raw_cookie_file and os.path.exists(raw_cookie_file):
        try:
            with open(raw_cookie_file, "r", encoding="utf-8", errors="ignore") as f:
                raw_cookie_content = f.read()
        except Exception:
            raw_cookie_content = None
    else:
        raw_cookie_content = None

def save_custom_cookies(cookie_content: str) -> Optional[str]:
    """Save user-provided cookies content from Streamlit UI after sanitizing."""
    if not cookie_content or not cookie_content.strip():
        return None
    clean_content = _sanitize_cookies(cookie_content.strip())
    cookies_path = TEMP_DIR / "clean_cookies.txt"
    with open(cookies_path, "w", encoding="utf-8") as f:
        f.write(clean_content)
    return str(cookies_path)

if raw_cookie_content:
    save_custom_cookies(raw_cookie_content)

def get_active_cookies_file() -> Optional[str]:
    """Dynamically return the active sanitized cookies file path if available."""
    cookies_path = TEMP_DIR / "clean_cookies.txt"
    if cookies_path.exists() and cookies_path.stat().st_size > 0:
        return str(cookies_path)
    return os.getenv("YTDLP_COOKIES_FILE")



