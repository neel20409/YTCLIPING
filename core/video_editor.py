import os
import re
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from config import OUTPUT_DIR, TEMP_DIR
from core.utils import seconds_to_hms, sanitize_filename

_OUT_TIME_RE = re.compile(r"out_time=(\d+):(\d+):(\d+)\.(\d+)")


def build_clip_srt(
    transcript_items: List[Dict[str, Any]],
    clip_start_sec: float,
    clip_end_sec: float,
    srt_path: str,
) -> bool:
    """Write an SRT file for the clip window, with timestamps relative to clip start."""

    def _srt_ts(secs: float) -> str:
        secs = max(0.0, secs)
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        s = int(secs % 60)
        ms = int(round((secs - int(secs)) * 1000))
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    entries = []
    idx = 1
    for item in transcript_items:
        i_start = float(item.get("start", 0))
        i_end = i_start + float(item.get("duration", 2.0))
        if i_end <= clip_start_sec or i_start >= clip_end_sec:
            continue
        rel_start = max(0.0, i_start - clip_start_sec)
        rel_end = min(clip_end_sec - clip_start_sec, i_end - clip_start_sec)
        text = item.get("text", "").strip().replace("\n", " ")
        if not text:
            continue
        entries.append(f"{idx}\n{_srt_ts(rel_start)} --> {_srt_ts(rel_end)}\n{text}\n")
        idx += 1

    if not entries:
        return False
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(entries))
    return True


def _escape_srt_path(path: str) -> str:
    """Escape a file path for use inside an FFmpeg filter string."""
    path = path.replace("\\", "/")
    # Escape the colon in Windows drive letters (C:/ -> C\:/)
    if len(path) > 1 and path[1] == ":":
        path = path[0] + "\\:" + path[2:]
    return path


def _hex_to_ass_color(hex_color: str) -> str:
    """Convert a #RRGGBB hex color into an ASS &H00BBGGRR& color code."""
    h = (hex_color or "#FBBF24").lstrip("#")
    if len(h) != 6:
        h = "FBBF24"
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}&".upper()


def _ass_ts(seconds: float) -> str:
    """Format seconds as an ASS timestamp: H:MM:SS.cc"""
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 0
        s += 1
        if s >= 60:
            s = 0
            m += 1
            if m >= 60:
                m = 0
                h += 1
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


# ASS numpad-style alignment: 2 = bottom-center, 5 = middle-center, 8 = top-center
# Separate margin fractions per style since word-by-word uses a much larger font
# than classic subtitle lines, and needs proportionally more clearance from the edge.
CAPTION_POSITIONS = {
    "word": {
        "top":    {"alignment": 8, "marginv_frac": 0.08},
        "middle": {"alignment": 5, "marginv_frac": 0.0},
        "bottom": {"alignment": 2, "marginv_frac": 0.12},
    },
    "classic": {
        "top":    {"alignment": 8, "marginv_frac": 0.045},
        "middle": {"alignment": 5, "marginv_frac": 0.0},
        "bottom": {"alignment": 2, "marginv_frac": 0.042},
    },
}


def _position_alignment(position: str, height: int, style: str = "word", custom_pct: Optional[float] = None) -> tuple:
    """Resolve a caption position name to an (alignment, marginv_px) pair.

    "custom" anchors captions from the top edge (alignment 8) and places them at
    custom_pct percent of the frame height, so 0% is the top edge and 100% is the
    bottom edge — an intuitive slider-friendly placement independent of font size.
    """
    if position == "custom" and custom_pct is not None:
        pct = max(0.0, min(100.0, custom_pct))
        return 8, int(height * pct / 100.0)

    presets = CAPTION_POSITIONS.get(style, CAPTION_POSITIONS["word"])
    cfg = presets.get(position, presets["bottom"])
    marginv = max(20, int(height * cfg["marginv_frac"])) if cfg["marginv_frac"] > 0 else 0
    return cfg["alignment"], marginv


def build_word_by_word_ass(
    transcript_items: List[Dict[str, Any]],
    clip_start_sec: float,
    clip_end_sec: float,
    ass_path: str,
    play_res: tuple = (1080, 1920),
    accent_color_hex: str = "#FBBF24",
    words_per_group: int = 1,
    position: str = "bottom",
    custom_pct: Optional[float] = None,
) -> bool:
    """
    Build an ASS subtitle track that shows one word (or small group) at a time,
    with a pop-in animation. Per-word timing is estimated by evenly splitting
    each transcript line's duration across its words, since YouTube transcripts
    only provide line-level timestamps.
    """
    width, height = play_res
    fontsize = max(36, int(height * 0.062))
    outline = max(2, fontsize // 16)
    alignment, marginv = _position_alignment(position, height, style="word", custom_pct=custom_pct)
    accent_ass = _hex_to_ass_color(accent_color_hex)

    events = []
    for item in transcript_items:
        i_start = float(item.get("start", 0))
        i_dur = float(item.get("duration", 2.0)) or 2.0
        i_end = i_start + i_dur
        if i_end <= clip_start_sec or i_start >= clip_end_sec:
            continue

        words = [w for w in item.get("text", "").replace("\n", " ").split(" ") if w.strip()]
        if not words:
            continue
        per_word = i_dur / len(words)

        for gi in range(0, len(words), words_per_group):
            group = words[gi:gi + words_per_group]
            w_start = i_start + gi * per_word
            w_end = w_start + per_word * len(group)

            rel_start = w_start - clip_start_sec
            rel_end = w_end - clip_start_sec
            rel_start = max(0.0, rel_start)
            rel_end = min(clip_end_sec - clip_start_sec, rel_end)
            if rel_end <= rel_start:
                continue

            text = " ".join(group).strip()
            text = text.replace("{", "(").replace("}", ")").replace("\\N", " ")
            if not text:
                continue

            tags = r"{\fad(40,60)\fscx78\fscy78\t(0,110,\fscx104\fscy104)\t(110,180,\fscx100\fscy100)}"
            events.append(
                f"Dialogue: 0,{_ass_ts(rel_start)},{_ass_ts(rel_end)},Word,,0,0,0,,{tags}{text}"
            )

    if not events:
        return False

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Word,Arial Black,{fontsize},{accent_ass},&H000000FF&,&H00000000&,&H00000000&,-1,0,0,0,100,100,0,0,1,{outline},1,{alignment},60,60,{marginv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write("\n".join(events))

    return True


def render_clip(
    input_video_path: str,
    start_sec: float,
    end_sec: float,
    output_name: str = "clip",
    aspect_ratio: str = "9:16",
    crop_mode: str = "blur_pad",
    transcript_items: Optional[List[Dict[str, Any]]] = None,
    burn_captions: bool = False,
    caption_style: str = "classic",
    accent_color: str = "#FBBF24",
    caption_position: str = "bottom",
    caption_custom_pct: Optional[float] = None,
    progress_callback: Optional[Callable[[float], None]] = None,
) -> Optional[str]:
    """
    Cut video segment using FFmpeg with aspect ratio formatting (9:16, 16:9, 1:1).
    Optionally burns subtitles from transcript_items into the output.
    """
    if not os.path.exists(input_video_path):
        print(f"Input video not found: {input_video_path}")
        return None

    duration = end_sec - start_sec
    if duration <= 0:
        print("Invalid start/end duration.")
        return None

    safe_name = sanitize_filename(output_name)
    output_filename = f"{safe_name}_{aspect_ratio.replace(':', 'x')}.mp4"
    output_file_path = str(OUTPUT_DIR / output_filename)

    start_hms = seconds_to_hms(start_sec)
    duration_str = str(duration)

    play_res = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)}.get(aspect_ratio, (1080, 1920))

    # Build caption overlay (classic SRT lines, or animated word-by-word ASS)
    srt_filter = ""
    if burn_captions and transcript_items:
        if caption_style == "word_by_word":
            ass_path = str(TEMP_DIR / f"{safe_name}_words.ass")
            wrote = build_word_by_word_ass(
                transcript_items, start_sec, end_sec, ass_path,
                play_res=play_res, accent_color_hex=accent_color, position=caption_position,
                custom_pct=caption_custom_pct,
            )
            if wrote:
                esc = _escape_srt_path(ass_path)
                srt_filter = f"ass='{esc}'"
        else:
            srt_path = str(TEMP_DIR / f"{safe_name}_subs.srt")
            wrote = build_clip_srt(transcript_items, start_sec, end_sec, srt_path)
            if wrote:
                esc = _escape_srt_path(srt_path)
                alignment, marginv = _position_alignment(caption_position, play_res[1], style="classic", custom_pct=caption_custom_pct)
                sub_style = (
                    "FontName=Arial,FontSize=22,Bold=1,"
                    "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                    f"Outline=2,Shadow=1,Alignment={alignment},MarginV={marginv}"
                )
                srt_filter = f"subtitles='{esc}':force_style='{sub_style}'"

    # Base FFmpeg command
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", start_hms,
        "-i", input_video_path,
        "-t", duration_str,
    ]

    # Select video filter based on aspect ratio
    if aspect_ratio == "9:16":
        if crop_mode == "blur_pad":
            # Blurred background pad with centered foreground video
            if srt_filter:
                filter_complex = (
                    "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];"
                    "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
                    f"[bg][fg]overlay=(W-w)/2:(H-h)/2[ov];"
                    f"[ov]{srt_filter}[v]"
                )
            else:
                filter_complex = (
                    "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];"
                    "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
                    "[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"
                )
            cmd.extend(["-filter_complex", filter_complex, "-map", "[v]", "-map", "0:a?"])
        else:
            # Direct Center Crop to 9:16
            vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
            if srt_filter:
                vf += f",{srt_filter}"
            cmd.extend(["-vf", vf])
    elif aspect_ratio == "1:1":
        # Square crop
        vf = "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080"
        if srt_filter:
            vf += f",{srt_filter}"
        cmd.extend(["-vf", vf])
    else:  # 16:9 Landscape
        vf = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
        if srt_filter:
            vf += f",{srt_filter}"
        cmd.extend(["-vf", vf])

    # Codecs and output parameters
    cmd.extend([
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "192k",
        "-avoid_negative_ts", "make_zero",
        "-progress", "pipe:1",
        "-nostats",
        output_file_path
    ])

    stderr_log_path = str(TEMP_DIR / f"{safe_name}_ffmpeg_err.log")
    try:
        print(f"Running FFmpeg: {' '.join(cmd)}")
        with open(stderr_log_path, "w", encoding="utf-8", errors="replace") as err_f:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err_f,
                                     text=True, encoding="utf-8", errors="replace")
            for line in proc.stdout:
                if not progress_callback:
                    continue
                m = _OUT_TIME_RE.search(line)
                if m:
                    h, mi, se, frac = m.groups()
                    elapsed = int(h) * 3600 + int(mi) * 60 + int(se) + int(frac) / (10 ** len(frac))
                    progress_callback(max(0.0, min(1.0, elapsed / duration)))
                elif line.strip() == "progress=end":
                    progress_callback(1.0)
            proc.wait()

        if proc.returncode == 0 and os.path.exists(output_file_path) and os.path.getsize(output_file_path) > 0:
            return output_file_path

        with open(stderr_log_path, encoding="utf-8", errors="replace") as f:
            stderr_text = f.read()
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=None, stderr=stderr_text)
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg render error: {e.stderr}")
        # Fallback to direct stream copy without filter if complex filter fails
        try:
            fallback_cmd = [
                "ffmpeg", "-y",
                "-ss", start_hms,
                "-i", input_video_path,
                "-t", duration_str,
                "-c", "copy",
                output_file_path
            ]
            subprocess.run(fallback_cmd, check=True)
            if os.path.exists(output_file_path):
                if progress_callback:
                    progress_callback(1.0)
                return output_file_path
        except Exception:
            pass
        return None
