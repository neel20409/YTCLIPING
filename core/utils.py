import re
from pathlib import Path
from config import TEMP_DIR, OUTPUT_DIR

def seconds_to_hms(seconds: float) -> str:
    """Convert seconds into HH:MM:SS or MM:SS format string."""
    seconds = int(seconds)
    hrs = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"

def hms_to_seconds(hms_str: str) -> float:
    """Convert HH:MM:SS or MM:SS or raw seconds string into float seconds."""
    if not hms_str:
        return 0.0
    hms_str = hms_str.strip()
    parts = hms_str.split(":")
    try:
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 1:
            return float(parts[0])
    except ValueError:
        return 0.0
    return 0.0

def sanitize_filename(filename: str) -> str:
    """Remove special characters for safe filesystem naming."""
    clean = re.sub(r'[\\/*?:"<>|]', "", filename)
    clean = clean.replace(" ", "_")
    return clean[:80]

def clean_directory(dir_path: Path):
    """Safely clear non-essential files from directory."""
    if dir_path.exists():
        for file in dir_path.glob("*"):
            if file.is_file():
                try:
                    file.unlink()
                except Exception:
                    pass
