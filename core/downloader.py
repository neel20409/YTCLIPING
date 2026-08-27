import os
from typing import Dict, Any, Optional, Callable
import yt_dlp
from config import TEMP_DIR, get_active_cookies_file
from core.utils import sanitize_filename

def get_video_info(url: str) -> Optional[Dict[str, Any]]:
    """Extract metadata for a given YouTube URL without downloading content."""
    base_ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "socket_timeout": 15,
        "retries": 3,
        "source_address": "0.0.0.0",
        "geo_bypass": True,
        "geo_bypass_country": "IN",
        "extractor_args": {
            "youtube": {"player_client": ["tv", "android", "ios"]},
        },
    }
    proxy = os.getenv("YTDLP_PROXY")
    if proxy:
        base_ydl_opts["proxy"] = proxy

    opts_list = []
    active_cookies = get_active_cookies_file()
    if active_cookies:
        cookie_opts = dict(base_ydl_opts)
        cookie_opts["cookiefile"] = active_cookies
        opts_list.append(cookie_opts)
    opts_list.append(base_ydl_opts)

    last_error = None
    for opts in opts_list:
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise RuntimeError("yt-dlp returned no video info.")

                return {
                    "id": info.get("id", ""),
                    "title": info.get("title", "Untitled Video"),
                    "uploader": info.get("uploader", "Unknown Channel"),
                    "duration": info.get("duration", 0),
                    "thumbnail": info.get("thumbnail", ""),
                    "view_count": info.get("view_count", 0),
                    "description": info.get("description", ""),
                    "url": url,
                }
        except Exception as e:
            last_error = e
            if opts.get("cookiefile"):
                print(f"[downloader] Cookiefile extraction failed ({e}). Retrying without cookies...")

    print(f"Error extracting video info: {last_error}")
    raise RuntimeError(f"Failed to load video info: {last_error}") from last_error

def download_video(url: str, filename_prefix: str = "source_video",
                    progress_hook: Optional[Callable[[Dict[str, Any]], None]] = None) -> Optional[str]:
    """Download video locally to temp directory for slicing."""
    sanitized_name = sanitize_filename(filename_prefix)
    output_template = str(TEMP_DIR / f"{sanitized_name}_%(id)s.%(ext)s")

    for stale in TEMP_DIR.glob(f"{sanitized_name}_*"):
        try:
            stale.unlink()
        except OSError:
            pass

    base_ydl_opts = {
        "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "overwrites": True,
        "merge_output_format": "mp4",
        "socket_timeout": 15,
        "retries": 3,
        "fragment_retries": 3,
        "extractor_retries": 1,
        "geo_bypass": True,
        "geo_bypass_country": "IN",
        "extractor_args": {
            "youtube": {"player_client": ["tv", "android", "ios"]},
        },
    }
    proxy = os.getenv("YTDLP_PROXY")
    if proxy:
        base_ydl_opts["proxy"] = proxy

    opts_list = []
    active_cookies = get_active_cookies_file()
    if active_cookies:
        cookie_opts = dict(base_ydl_opts)
        cookie_opts["cookiefile"] = active_cookies
        opts_list.append(cookie_opts)
    opts_list.append(base_ydl_opts)

    last_error = None
    for opts in opts_list:
        try:
            current_opts = dict(opts)
            if progress_hook:
                current_opts["progress_hooks"] = [progress_hook]

            with yt_dlp.YoutubeDL(current_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise RuntimeError("yt-dlp returned no video info.")

                filename = ydl.prepare_filename(info)
                base, _ = os.path.splitext(filename)
                mp4_file = f"{base}.mp4"
                for candidate in (mp4_file, filename):
                    if os.path.exists(candidate):
                        if os.path.getsize(candidate) == 0:
                            raise RuntimeError("Downloaded file is empty (0 bytes).")
                        return candidate
                raise RuntimeError("Download reported success but no output file was found.")
        except Exception as e:
            last_error = e
            if opts.get("cookiefile"):
                print(f"[downloader] Cookiefile download failed ({e}). Retrying without cookies...")

    print(f"Error downloading video: {last_error}")
    raise RuntimeError(f"Failed to download video: {last_error}") from last_error
