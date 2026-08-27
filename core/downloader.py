import os
from typing import Dict, Any, Optional, Callable
import yt_dlp
from config import TEMP_DIR
from core.utils import sanitize_filename

def get_video_info(url: str) -> Optional[Dict[str, Any]]:
    """Extract metadata for a given YouTube URL without downloading content."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None
            
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
        print(f"Error extracting video info: {e}")
        return None

def download_video(url: str, filename_prefix: str = "source_video",
                    progress_hook: Optional[Callable[[Dict[str, Any]], None]] = None) -> Optional[str]:
    """Download video locally to temp directory for slicing."""
    sanitized_name = sanitize_filename(filename_prefix)
    output_template = str(TEMP_DIR / f"{sanitized_name}_%(id)s.%(ext)s")

    # A prior download for this same video may have been interrupted (network drop,
    # closed tab, app restart), leaving partial/merge-temp files behind that confuse
    # yt-dlp's "already downloaded" detection on retry. Always start from a clean slate.
    for stale in TEMP_DIR.glob(f"{sanitized_name}_*"):
        try:
            stale.unlink()
        except OSError:
            pass

    ydl_opts = {
        "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "overwrites": True,
        "merge_output_format": "mp4",
    }
    if progress_hook:
        ydl_opts["progress_hooks"] = [progress_hook]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return None
            
            # Find requested file
            filename = ydl.prepare_filename(info)
            # Ensure mp4 extension if merged
            base, _ = os.path.splitext(filename)
            mp4_file = f"{base}.mp4"
            if os.path.exists(mp4_file):
                return mp4_file
            elif os.path.exists(filename):
                return filename
            return None
    except Exception as e:
        print(f"Error downloading video: {e}")
        return None
