import json
import re
from typing import List, Dict, Any, Optional, Tuple
from google import genai
from google.genai import errors as genai_errors
from config import GEMINI_API_KEY
from core.utils import seconds_to_hms, hms_to_seconds

def analyze_transcript_with_gemini(transcript_chunks: List[Dict[str, Any]], video_title: str, n_clips: int = 5, custom_prompt: str = "") -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """Use Gemini AI to analyze transcript and identify top highlight clips.

    Returns (clips, status) where status is "quota" if the API key hit its rate/usage
    limit, otherwise None.
    """
    api_key = GEMINI_API_KEY
    if not api_key:
        return None, None

    try:
        client = genai.Client(api_key=api_key)

        full_text = "\n".join([f"[{chunk['timestamp_str']}] {chunk['text']}" for chunk in transcript_chunks])

        focus_line = f"\nAdditional focus: {custom_prompt.strip()}" if custom_prompt.strip() else ""

        prompt = f"""
You are an expert video editor & viral content strategist for YouTube Shorts, TikTok, and Instagram Reels.
Below is the transcript of a YouTube video titled: "{video_title}" with timestamps.{focus_line}

Analyze the transcript and identify exactly {n_clips} of the most engaging, valuable, entertaining, or viral highlight clips.
Each clip should be self-contained, interesting, and typically 20 to 60 seconds long.

TRANSCRIPT:
{full_text[:30000]}

Respond ONLY with a valid JSON array of exactly {n_clips} objects with the exact schema below (no extra text, no markdown block quotes):
[
  {{
    "title": "Catchy Short Title for Clip",
    "start_time": "01:23",
    "end_time": "02:10",
    "viral_score": 92,
    "hook": "Why this segment captures attention immediately.",
    "category": "Key Insight / Funny Moment / Story / How-To"
  }}
]
"""
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        content = response.text.strip()
        
        # Clean JSON markdown if wrapped in ```json ... ```
        content = re.sub(r"^```json\s*", "", content, flags=re.MULTILINE)
        content = re.sub(r"^```\s*", "", content, flags=re.MULTILINE)
        content = re.sub(r"```$", "", content, flags=re.MULTILINE)
        
        clips = json.loads(content)
        
        # Normalize and validate clips
        validated_clips = []
        for c in clips:
            start_sec = hms_to_seconds(str(c.get("start_time", "00:00")))
            end_sec = hms_to_seconds(str(c.get("end_time", "00:30")))
            if end_sec <= start_sec:
                end_sec = start_sec + 30
            
            validated_clips.append({
                "title": c.get("title", "Highlighted Clip"),
                "start_time": seconds_to_hms(start_sec),
                "end_time": seconds_to_hms(end_sec),
                "start_sec": start_sec,
                "end_sec": end_sec,
                "duration_sec": end_sec - start_sec,
                "viral_score": min(100, max(50, int(c.get("viral_score", 85)))),
                "hook": c.get("hook", "High engagement video highlight."),
                "category": c.get("category", "Highlight"),
                "source": "Gemini AI"
            })
        return validated_clips, None
    except genai_errors.APIError as e:
        print(f"Gemini API error: {e}")
        if e.code == 429:
            return None, "quota"
        return None, None
    except Exception as e:
        print(f"Gemini analysis error: {e}")
        return None, None

def heuristic_highlight_finder(transcript_chunks: List[Dict[str, Any]], video_duration: float, n_clips: int = 5) -> List[Dict[str, Any]]:
    """Smart fallback heuristic highlight engine when Gemini API key is not present."""
    if not transcript_chunks:
        # Fallback to fixed interval clips if no transcript available
        interval = min(45, max(20, int(video_duration / 4))) if video_duration > 0 else 30
        clips = []
        for i in range(min(n_clips, max(1, int(video_duration // 60)))):
            start = i * 60 + 15
            end = min(video_duration, start + interval)
            if start < video_duration:
                clips.append({
                    "title": f"Highlight Segment {i+1}",
                    "start_time": seconds_to_hms(start),
                    "end_time": seconds_to_hms(end),
                    "start_sec": start,
                    "end_sec": end,
                    "duration_sec": end - start,
                    "viral_score": 80 - i * 5,
                    "hook": "Auto-detected video interval highlight.",
                    "category": "Segment",
                    "source": "Smart Timeline"
                })
        return clips

    VIRAL_KEYWORDS = [
        "secret", "amazing", "how to", "never", "always", "best", "worst",
        "why", "stop", "key", "important", "truth", "money", "mistake",
        "hack", "trick", "future", "ai", "think", "problem", "solution"
    ]
    
    scored_chunks = []
    for chunk in transcript_chunks:
        text = chunk["text"].lower()
        word_count = len(text.split())
        keyword_hits = sum(1 for kw in VIRAL_KEYWORDS if kw in text)
        question_bonus = text.count("?") * 3
        exclamation_bonus = text.count("!") * 2
        
        # Calculate raw engagement score
        score = (word_count * 0.5) + (keyword_hits * 10) + question_bonus + exclamation_bonus
        scored_chunks.append({
            "chunk": chunk,
            "score": score
        })
        
    # Sort chunks by score descending
    scored_chunks.sort(key=lambda x: x["score"], reverse=True)
    
    # Pick top non-overlapping segments (combine adjacent chunks to form ~30-50s clips)
    selected_clips = []
    used_timestamps = set()
    
    for item in scored_chunks:
        c = item["chunk"]
        start_sec = c["start"]
        end_sec = min(c["end"] + 15, c["start"] + 45)  # Make a 30-45s clip
        
        # Check overlap
        overlap = False
        for t in range(int(start_sec), int(end_sec)):
            if t in used_timestamps:
                overlap = True
                break
        if overlap:
            continue
            
        for t in range(int(start_sec), int(end_sec)):
            used_timestamps.add(t)
            
        title_words = c["text"].split()[:6]
        short_title = " ".join(title_words).strip(".,!?").capitalize() + "..." if title_words else "Top Moment"
        
        score_val = min(98, max(70, int(75 + item["score"] / 2)))
        selected_clips.append({
            "title": short_title,
            "start_time": seconds_to_hms(start_sec),
            "end_time": seconds_to_hms(end_sec),
            "start_sec": start_sec,
            "end_sec": end_sec,
            "duration_sec": end_sec - start_sec,
            "viral_score": score_val,
            "hook": f"High speech density moment: '{c['text'][:80]}...'",
            "category": "Key Moment",
            "source": "Smart Heuristic"
        })
        
        if len(selected_clips) >= n_clips:
            break
            
    # Sort selected clips chronologically
    selected_clips.sort(key=lambda x: x["start_sec"])
    return selected_clips

def find_best_clips(transcript_chunks: List[Dict[str, Any]], video_title: str, video_duration: float, n_clips: int = 5, custom_prompt: str = "") -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Main entry point: tries Gemini AI first, falls back to smart heuristic finder.

    Returns (clips, notice) where notice is a user-facing message to display, or None.
    """
    ai_results, status = analyze_transcript_with_gemini(transcript_chunks, video_title, n_clips=n_clips, custom_prompt=custom_prompt)
    if ai_results:
        return ai_results, None

    fallback_clips = heuristic_highlight_finder(transcript_chunks, video_duration, n_clips=n_clips)
    if status == "quota":
        return fallback_clips, "⚠️ Service Temporarily not available — Gemini AI usage limit reached. Showing smart fallback highlights instead."
    return fallback_clips, None
