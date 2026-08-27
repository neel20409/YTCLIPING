from typing import List, Dict, Any, Optional
from youtube_transcript_api import YouTubeTranscriptApi
from core.utils import seconds_to_hms

def fetch_transcript(video_id: str) -> Optional[List[Dict[str, Any]]]:
    """Fetch transcripts with start time & duration from YouTube API."""
    try:
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id)
        if fetched and hasattr(fetched, 'snippets'):
            return [
                {
                    "text": snippet.text,
                    "start": snippet.start,
                    "duration": snippet.duration
                }
                for snippet in fetched.snippets
            ]
        elif isinstance(fetched, list):
            return [
                {
                    "text": item.get('text', '') if isinstance(item, dict) else getattr(item, 'text', ''),
                    "start": item.get('start', 0) if isinstance(item, dict) else getattr(item, 'start', 0),
                    "duration": item.get('duration', 0) if isinstance(item, dict) else getattr(item, 'duration', 0)
                }
                for item in fetched
            ]
    except Exception as e:
        print(f"Direct fetch_transcript failed for {video_id}: {e}")
        try:
            api = YouTubeTranscriptApi()
            transcripts = api.list(video_id)
            for transcript in transcripts:
                try:
                    fetched = transcript.fetch()
                    if hasattr(fetched, 'snippets'):
                        return [
                            {"text": s.text, "start": s.start, "duration": s.duration}
                            for s in fetched.snippets
                        ]
                except Exception:
                    continue
        except Exception as ex:
            print(f"Could not retrieve transcript for video {video_id}: {ex}")
            return None
    return None

def format_transcript_chunks(transcript_items: List[Dict[str, Any]], chunk_seconds: int = 30) -> List[Dict[str, Any]]:
    """Group individual transcript snippets into cohesive ~30s timed text chunks."""
    if not transcript_items:
        return []
    
    chunks = []
    current_text = []
    current_start = transcript_items[0]['start']
    
    for item in transcript_items:
        text = item['text'].strip()
        start = item['start']
        
        if (start - current_start) >= chunk_seconds and current_text:
            chunks.append({
                "start": current_start,
                "end": start,
                "timestamp_str": f"{seconds_to_hms(current_start)} - {seconds_to_hms(start)}",
                "text": " ".join(current_text)
            })
            current_text = [text]
            current_start = start
        else:
            current_text.append(text)
            
    if current_text:
        last_end = transcript_items[-1]['start'] + transcript_items[-1].get('duration', 5)
        chunks.append({
            "start": current_start,
            "end": last_end,
            "timestamp_str": f"{seconds_to_hms(current_start)} - {seconds_to_hms(last_end)}",
            "text": " ".join(current_text)
        })
        
    return chunks
