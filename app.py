import os
import sys
import time
import math
import datetime
from concurrent.futures import ThreadPoolExecutor
import streamlit as st

# Windows consoles often default to a legacy codepage (e.g. cp1252) that can't
# encode non-ASCII video titles/filenames, crashing any print() that includes them.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from config import OUTPUT_DIR, GEMINI_API_KEY
from core.downloader import get_video_info, download_video
from core.transcript import fetch_transcript, format_transcript_chunks
from core.ai_clipper import find_best_clips
from core.video_editor import render_clip
from core.utils import seconds_to_hms, clean_directory

def _sec_to_time(s: float) -> datetime.time:
    """Convert seconds into a datetime.time so st.slider can show a friendly mm:ss handle."""
    s = max(0, int(s))
    return datetime.time(hour=(s // 3600) % 24, minute=(s % 3600) // 60, second=s % 60)

def _time_to_sec(t: datetime.time) -> int:
    return t.hour * 3600 + t.minute * 60 + t.second

def _download_with_progress(bar, source_url, source_id):
    """Runs download_video() in a background thread and polls its progress from the main
    thread. yt-dlp calls progress_hooks from its own fragment-downloader worker threads —
    calling Streamlit UI updates directly from there stalls the session, so the hook only
    writes plain numbers into a shared dict and the main thread does the actual bar.progress()."""
    dl_state = {"downloaded": 0, "total": None}

    def _dl_hook(d):
        dl_state["downloaded"] = d.get("downloaded_bytes", 0)
        dl_state["total"] = d.get("total_bytes") or d.get("total_bytes_estimate")

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(download_video, source_url, source_id, progress_hook=_dl_hook)
        while not future.done():
            total, downloaded = dl_state["total"], dl_state["downloaded"]
            if total:
                pct = max(0, min(99, int(downloaded / total * 100)))
                bar.progress(pct / 100, text=f"⬇️ Downloading video… {pct}%")
            else:
                mb = downloaded / (1024 * 1024)
                bar.progress(0.05, text=f"⬇️ Downloading video… {mb:.1f} MB so far")
            time.sleep(0.3)
        return future.result()

def _cut_clip_with_progress(source_url, source_id, start_sec, end_sec, output_name, render_kwargs):
    """Downloads the source video (if not already cached) and cuts the clip, showing a live % progress bar."""
    bar = st.progress(0, text="Starting…")
    try:
        if not st.session_state.local_source_path or not os.path.exists(st.session_state.local_source_path):
            st.session_state.local_source_path = _download_with_progress(bar, source_url, source_id)
            if st.session_state.local_source_path:
                bar.progress(1.0, text="⬇️ Download complete — preparing to cut…")

        if not st.session_state.local_source_path:
            bar.empty()
            return None

        def _render_hook(frac):
            bar.progress(max(0.0, min(1.0, frac)), text=f"✂️ Cutting your clip… {int(frac * 100)}%")

        out = render_clip(st.session_state.local_source_path, start_sec, end_sec,
                           output_name=output_name, progress_callback=_render_hook, **render_kwargs)
        bar.empty()
        return out
    except Exception:
        bar.empty()
        raise

# ── Page Config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="YTCliping",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

:root {
  --bg0:       #090b13;
  --bg1:       #0f1221;
  --bg2:       #151929;
  --bg3:       #1c2035;
  --border:    rgba(255,255,255,0.07);
  --border-hi: rgba(139,92,246,0.45);
  --p1:        #8b5cf6;
  --p2:        #a78bfa;
  --p3:        #c4b5fd;
  --pink:      #ec4899;
  --green:     #10b981;
  --amber:     #f59e0b;
  --text0:     #f8fafc;
  --text1:     #cbd5e1;
  --text2:     #64748b;
  --r-sm:      10px;
  --r:         14px;
  --r-lg:      20px;
  --r-xl:      28px;
  --neo-out:   8px 8px 20px #04060f, -6px -6px 16px #1a1e33;
  --neo-in:    inset 5px 5px 12px #04060f, inset -4px -4px 10px #1a1e33;
  --glow-p:    0 0 28px rgba(139,92,246,.4);
  --t:         all .2s cubic-bezier(.4,0,.2,1);
}

*, *::before, *::after { box-sizing: border-box; }

html, body, [class*="css"], .stApp {
  font-family: 'Inter', sans-serif !important;
  background: var(--bg0) !important;
  color: var(--text0) !important;
}

/* ── Chrome ── */
#MainMenu, footer, header { visibility: hidden; }
.block-container {
  padding: 2rem 2rem 5rem !important;
  max-width: 1100px !important;
  margin: 0 auto !important;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: var(--bg0); }
::-webkit-scrollbar-thumb { background: var(--bg3); border-radius: 99px; }

/* ════════════ SIDEBAR ════════════ */
[data-testid="stSidebar"] {
  background: var(--bg1) !important;
  border-right: 1px solid var(--border) !important;
  box-shadow: 4px 0 40px rgba(0,0,0,.5) !important;
}
[data-testid="stSidebar"] > div:first-child { padding: 1.2rem !important; }

/* ════════════ INPUTS ════════════ */
.stTextInput > label { display: none !important; }
.stTextInput > div > div {
  background: var(--bg2) !important;
  border: 1px solid var(--border) !important;
  border-radius: 99px !important;
  box-shadow: var(--neo-in) !important;
  transition: var(--t) !important;
}
.stTextInput > div > div:focus-within {
  border-color: var(--border-hi) !important;
  box-shadow: var(--neo-in), var(--glow-p) !important;
}
.stTextInput > div > div > input {
  background: transparent !important;
  color: var(--text0) !important;
  border: none !important;
  border-radius: 99px !important;
  padding: 0.85rem 1.5rem !important;
  font-size: 0.95rem !important;
  font-family: 'Inter', sans-serif !important;
  box-shadow: none !important;
}
.stTextInput > div > div > input::placeholder { color: var(--text2) !important; }
.stTextInput > div > div > input:focus { box-shadow: none !important; outline: none !important; }

/* ════════════ BUTTONS ════════════ */
.stButton > button {
  font-family: 'Inter', sans-serif !important;
  font-weight: 600 !important;
  font-size: 0.88rem !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--r-sm) !important;
  background: var(--bg2) !important;
  color: var(--text1) !important;
  padding: 0.65rem 1.2rem !important;
  box-shadow: var(--neo-out) !important;
  transition: var(--t) !important;
  cursor: pointer !important;
}
.stButton > button:hover {
  border-color: var(--border-hi) !important;
  color: var(--p2) !important;
  transform: translateY(-1px) !important;
}
.stButton > button:active {
  box-shadow: var(--neo-in) !important;
  transform: translateY(0) !important;
}
.stButton > button[kind="primary"] {
  background: linear-gradient(135deg,#7c3aed,#a855f7) !important;
  color: #fff !important;
  border: none !important;
  box-shadow: 0 4px 22px rgba(124,58,237,.5) !important;
  border-radius: 99px !important;
  padding: 0.85rem 2rem !important;
  font-size: 0.95rem !important;
}
.stButton > button[kind="primary"]:hover {
  background: linear-gradient(135deg,#6d28d9,#9333ea) !important;
  box-shadow: 0 6px 30px rgba(124,58,237,.65) !important;
  color: #fff !important;
  transform: translateY(-2px) !important;
}

/* ════════════ SELECTS ════════════ */
.stSelectbox > label {
  color: var(--text2) !important;
  font-size: 0.75rem !important;
  font-weight: 600 !important;
  letter-spacing: .5px !important;
}
.stSelectbox > div > div {
  background: var(--bg2) !important;
  color: var(--text0) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--r-sm) !important;
  box-shadow: var(--neo-in) !important;
  font-family: 'Inter', sans-serif !important;
  font-size: 0.88rem !important;
}
.stSelectbox svg { color: var(--text2) !important; }

/* ════════════ NUMBER INPUTS ════════════ */
.stNumberInput > label {
  color: var(--text2) !important;
  font-size: 0.75rem !important;
  font-weight: 600 !important;
}
.stNumberInput > div > div {
  background: var(--bg2) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--r-sm) !important;
  box-shadow: var(--neo-in) !important;
}
.stNumberInput > div > div > input {
  background: transparent !important;
  color: var(--text0) !important;
  border: none !important;
  font-family: 'Inter', sans-serif !important;
  font-weight: 700 !important;
  font-size: 1.05rem !important;
  box-shadow: none !important;
}
.stNumberInput button {
  background: var(--bg3) !important;
  border: none !important;
  color: var(--text2) !important;
}

/* ════════════ TABS ════════════ */
.stTabs { margin-top: .4rem !important; }
.stTabs [data-baseweb="tab-list"] {
  background: var(--bg2) !important;
  border: 1px solid rgba(139,92,246,.25) !important;
  border-radius: var(--r-lg) !important;
  box-shadow: var(--neo-in) !important;
  padding: 6px !important;
  gap: 6px !important;
  display: flex !important;
  flex-wrap: wrap !important;
}
.stTabs [data-baseweb="tab"] {
  background: transparent !important;
  color: var(--text1) !important;
  border-radius: var(--r) !important;
  font-family: 'Inter', sans-serif !important;
  font-weight: 700 !important;
  font-size: 0.98rem !important;
  padding: 14px 20px !important;
  border: none !important;
  transition: var(--t) !important;
  flex: 1 1 0 !important;
  justify-content: center !important;
  min-width: 140px !important;
}
.stTabs [aria-selected="true"] {
  background: linear-gradient(135deg,#7c3aed,#a855f7) !important;
  color: #fff !important;
  box-shadow: 0 4px 18px rgba(124,58,237,.5) !important;
}
.stTabs [data-baseweb="tab-panel"] { padding-top: 1.5rem !important; }
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] { display: none !important; }
.tab-hint {
  font-size: .82rem; color: var(--text2); line-height: 1.5;
  margin: -.4rem 0 1.1rem; padding-bottom: .9rem;
  border-bottom: 1px solid var(--border);
}

/* ════════════ ALERTS ════════════ */
.stAlert > div {
  background: var(--bg2) !important;
  border-radius: var(--r-sm) !important;
  border: 1px solid var(--border) !important;
  font-family: 'Inter', sans-serif !important;
}

/* ════════════ MEDIA ════════════ */
.stVideo > div, .stVideo iframe, video {
  border-radius: var(--r) !important;
  box-shadow: 0 8px 32px rgba(0,0,0,.5) !important;
}
.stImage img {
  border-radius: var(--r-sm) !important;
  box-shadow: 0 4px 20px rgba(0,0,0,.4) !important;
}

/* ════════════ MISC ════════════ */
hr { border: none !important; height: 1px !important; background: var(--border) !important; margin: 1.2rem 0 !important; }
.stSpinner > div { border-top-color: var(--p1) !important; }
.stDownloadButton > button {
  background: linear-gradient(135deg,#0d9488,#14b8a6) !important;
  color: #fff !important; border: none !important;
  border-radius: var(--r-sm) !important;
  font-family: 'Inter', sans-serif !important;
  font-weight: 600 !important;
  box-shadow: 0 4px 16px rgba(20,184,166,.35) !important;
  transition: var(--t) !important;
}
.stDownloadButton > button:hover { transform: translateY(-1px) !important; box-shadow: 0 6px 22px rgba(20,184,166,.5) !important; }

h1,h2,h3,h4 { font-family: 'Inter', sans-serif !important; color: var(--text0) !important; }

/* ════════════ HERO ════════════ */
.hero {
  text-align: center;
  padding: 3rem 1rem 2rem;
  width: 100%;
}
.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: rgba(139,92,246,.12);
  border: 1px solid rgba(139,92,246,.3);
  border-radius: 99px;
  padding: 5px 16px;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 1.8px;
  text-transform: uppercase;
  color: var(--p2);
  margin-bottom: 1.5rem;
}
.hero-badge .dot { width:5px; height:5px; border-radius:50%; background:var(--p1); display:inline-block; }
.hero-h1 {
  font-size: clamp(2.6rem, 5.5vw, 4.2rem);
  font-weight: 900;
  letter-spacing: -2.5px;
  line-height: 1.05;
  background: linear-gradient(135deg, #fff 0%, var(--p3) 45%, var(--pink) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin: 0 0 1rem;
  display: block;
}
.hero-sub {
  font-size: clamp(0.88rem, 2vw, 1rem);
  color: var(--text2);
  max-width: 480px;
  margin: 0 auto 0.5rem;
  line-height: 1.7;
  display: block;
}
.hero-line {
  width: 180px;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--p1), transparent);
  margin: 1.8rem auto 0;
}

/* URL row */
.url-row {
  max-width: 700px;
  margin: 0 auto 2.5rem;
  display: flex;
  gap: 10px;
  align-items: center;
}

/* ════════════ COMPONENTS ════════════ */
.card {
  background: var(--bg1);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: 1.5rem;
  box-shadow: var(--neo-out);
  margin-bottom: 1.2rem;
  transition: var(--t);
}
.card:hover { border-color: rgba(139,92,246,.2); transform: translateY(-1px); }

.meta-card {
  background: var(--bg1);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: 1.4rem;
  box-shadow: var(--neo-out);
  margin-bottom: 1.8rem;
}
.meta-title {
  font-size: clamp(0.95rem,2.5vw,1.15rem);
  font-weight: 700;
  color: var(--text0);
  line-height: 1.4;
  margin: 0 0 0.5rem;
}
.meta-row { display:flex; flex-wrap:wrap; gap:0.5rem; margin-top:.8rem; }
.meta-chip {
  display: inline-flex; align-items: center; gap: 5px;
  background: var(--bg3); border: 1px solid var(--border);
  border-radius: 99px; padding: 4px 12px;
  font-size: 0.75rem; font-weight: 500; color: var(--text2);
}
.meta-chip b { color: var(--text1); }

.clip-card {
  background: var(--bg1);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: 1.4rem 1.5rem;
  box-shadow: var(--neo-out);
  margin-bottom: 1rem;
  transition: var(--t);
}
.clip-card:hover { border-color: rgba(139,92,246,.25); box-shadow: var(--neo-out), var(--glow-p); transform: translateY(-2px); }

.clip-num { font-size:.65rem; font-weight:700; letter-spacing:2.5px; text-transform:uppercase; color:var(--p2); margin-bottom:3px; }
.clip-title { font-size:clamp(.95rem,2.5vw,1.1rem); font-weight:700; color:var(--text0); margin:0 0 .75rem; line-height:1.35; }
.clip-hook { font-size:.84rem; color:var(--text2); line-height:1.65; margin-top:.6rem; padding-top:.6rem; border-top:1px solid var(--border); }

.pills { display:flex; flex-wrap:wrap; gap:5px; margin-bottom:.4rem; }
.pill { display:inline-flex; align-items:center; gap:3px; padding:3px 10px; border-radius:99px; font-size:.72rem; font-weight:600; white-space:nowrap; }
.p-fire { background:linear-gradient(135deg,#f59e0b,#ef4444); color:#fff; }
.p-cat  { background:rgba(139,92,246,.15); color:var(--p2); border:1px solid rgba(139,92,246,.3); }
.p-time { background:var(--bg3); color:var(--text2); border:1px solid var(--border); }
.p-src  { background:rgba(16,185,129,.12); color:#34d399; border:1px solid rgba(16,185,129,.25); }

.sec-head { display:flex; align-items:baseline; gap:10px; margin:1.8rem 0 1.2rem; }
.sec-lbl { font-size:.65rem; font-weight:700; letter-spacing:2px; text-transform:uppercase; color:var(--text2); }
.sec-cnt { font-size:1.6rem; font-weight:800; color:var(--text0); letter-spacing:-1px; line-height:1; }

.scan-box {
  background: var(--bg1);
  border: 1px solid rgba(139,92,246,.18);
  border-radius: var(--r-lg);
  padding: 1rem 1.2rem;
  display: flex;
  align-items: center;
  gap: .8rem;
  text-align: left;
  box-shadow: var(--neo-out);
  margin-bottom: 1rem;
}
.scan-icon { font-size:1.6rem; flex-shrink:0; }
.scan-box h3 { font-size:.95rem; font-weight:700; color:var(--text0); margin:0; }
.scan-box p { font-size:.8rem; color:var(--text2); line-height:1.4; margin:2px 0 0; }

.time-box {
  background: var(--bg2); border: 1px solid var(--border);
  border-radius: var(--r-sm); box-shadow: var(--neo-in);
  padding: .9rem 1rem; text-align: center;
  font-size: clamp(1.4rem,4vw,2rem); font-weight:800;
  font-variant-numeric: tabular-nums; letter-spacing:3px;
  color: var(--p2); margin-top:.4rem;
}
.dur-strip {
  background: var(--bg2); border: 1px solid var(--border);
  border-radius: var(--r-sm); box-shadow: var(--neo-in);
  padding: 1rem 1.4rem;
  display: flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:.75rem;
  margin: 1rem 0;
}
.di-lbl { font-size:.68rem; font-weight:600; letter-spacing:1px; text-transform:uppercase; color:var(--text2); display:block; }
.di-val { font-size:1rem; font-weight:700; color:var(--text0); display:block; }

.gallery-card {
  background: var(--bg1); border: 1px solid var(--border);
  border-radius: var(--r-lg); padding: 1.3rem;
  box-shadow: var(--neo-out); margin-bottom: 1.2rem;
}

.empty-state {
  text-align:center; padding:4rem 2rem; color:var(--text2);
}
.empty-icon { font-size:3.5rem; opacity:.15; display:block; margin-bottom:1rem; }
.empty-state h3 { font-size:1rem; font-weight:600; color:var(--text2); margin-bottom:.5rem; }
.empty-state p  { font-size:.88rem; line-height:1.7; max-width:340px; margin:0 auto; }

/* Sidebar helpers */
.sb-logo { text-align:center; padding:1.2rem 0 .8rem; }
.sb-logo .si { font-size:2.2rem; display:block; filter:drop-shadow(0 0 14px rgba(139,92,246,.8)); margin-bottom:5px; }
.sb-logo .sn { font-size:1.1rem; font-weight:800; background:linear-gradient(135deg,var(--p2),var(--pink)); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
.sb-logo .st { font-size:.65rem; font-weight:700; letter-spacing:2.5px; color:var(--text2); text-transform:uppercase; margin-top:2px; }
.sb-lbl { font-size:.65rem; font-weight:700; letter-spacing:2px; text-transform:uppercase; color:var(--text2); margin:1.2rem 0 .5rem; display:block; }
.status-badge { display:flex; align-items:center; gap:8px; background:var(--bg2); border:1px solid var(--border); border-radius:var(--r-sm); padding:.55rem .85rem; font-size:.82rem; font-weight:500; color:var(--text1); }
.s-dot { width:7px; height:7px; border-radius:50%; flex-shrink:0; }
.dot-g { background:var(--green); box-shadow:0 0 8px var(--green); }
.dot-a { background:var(--amber); box-shadow:0 0 8px var(--amber); }

/* ════════════ MOBILE ════════════ */
@media (max-width: 768px) {
  .block-container { padding: 1rem .75rem 5rem !important; }
  [data-testid="column"] { width:100% !important; flex:1 1 100% !important; min-width:100% !important; }
  .hero { padding: 2rem .5rem 1.5rem; }
  .scan-box { padding: 1.8rem 1.2rem; }
  .clip-card { padding: 1.1rem; }
  .time-box { font-size: 1.4rem; letter-spacing: 2px; }
  .dur-strip { flex-direction: column; align-items: flex-start; }
  .stTabs [data-baseweb="tab"] { padding: 6px 12px !important; font-size: .78rem !important; }
}
@media (max-width: 480px) {
  .hero-h1 { font-size: 2.1rem !important; letter-spacing: -1.5px !important; }
  .block-container { padding: .75rem .5rem 5rem !important; }
}
</style>
""", unsafe_allow_html=True)

# ── Session State ──────────────────────────────────────────────────────────────
for k, v in [("video_info", None), ("transcript_chunks", None), ("raw_transcript", []), ("ai_clips", []), ("local_source_path", None), ("clip_scan_id", 0)]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class="sb-logo">
        <span class="si">🎬</span>
        <div class="sn">YTCliping</div>
        <div class="st">AI Clip Studio</div>
    </div>""", unsafe_allow_html=True)
    st.divider()

    st.markdown('<span class="sb-lbl">Video Shape</span>', unsafe_allow_html=True)
    aspect_ratio = st.selectbox("AR", ["9:16","16:9","1:1"],
        format_func=lambda x: {"9:16":"📱 Tall — Shorts / Reels / TikTok","16:9":"🖥️ Wide — YouTube / TV","1:1":"🔳 Square — Feed Post"}[x],
        label_visibility="collapsed",
        help="Pick the shape that matches where you're posting. Tall (9:16) is best for phone apps like Shorts, Reels, and TikTok.")

    if aspect_ratio == "9:16":
        st.markdown('<span class="sb-lbl">When Video Doesn\'t Fit</span>', unsafe_allow_html=True)
        crop_mode = st.selectbox("CM", ["blur_pad","crop_center"],
            format_func=lambda x: "✨ Keep it all (blurred edges)" if x=="blur_pad" else "✂️ Zoom in (crop the sides)",
            label_visibility="collapsed",
            help="Wide videos need to be reshaped to fit a tall phone screen. 'Keep it all' shows the whole picture with blurred bars on the sides. 'Zoom in' fills the screen but crops off the edges.")
    else:
        crop_mode = "blur_pad"

    st.divider()
    st.markdown('<span class="sb-lbl">Subtitles</span>', unsafe_allow_html=True)
    caption_mode = st.selectbox("Caption Style", ["None", "Classic Subtitles", "Word-by-Word (Animated)"],
        index=2, label_visibility="collapsed",
        help="Add text on screen so viewers can follow along with the sound off. 'Word-by-Word' highlights each word as it's spoken.")
    burn_captions = caption_mode != "None"
    caption_style = "word_by_word" if caption_mode.startswith("Word") else "classic"
    accent_color = "#FBBF24"
    caption_position = "bottom"
    caption_custom_pct = 80.0
    if burn_captions:
        if caption_style == "word_by_word":
            accent_color = st.color_picker("Highlight Color", value="#FBBF24",
                help="The color used to highlight the word currently being spoken.")
        st.markdown('<span class="sb-lbl">Subtitle Position</span>', unsafe_allow_html=True)
        caption_position = st.selectbox("Caption Position", ["top", "middle", "bottom", "custom"], index=2,
            format_func=lambda x: {"top": "⬆️ Top", "middle": "◼️ Middle", "bottom": "⬇️ Bottom", "custom": "🎯 Custom"}[x],
            label_visibility="collapsed",
            help="Where the subtitles show up on the video.")
        if caption_position == "custom":
            caption_custom_pct = st.slider("How far down the screen (%)", 0, 100, 80, step=1)
    st.caption("Note: subtitles only work if the original YouTube video already has them.")

    st.divider()
    st.markdown('<span class="sb-lbl">How Clips Are Picked</span>', unsafe_allow_html=True)
    if GEMINI_API_KEY:
        st.markdown('<div class="status-badge"><span class="s-dot dot-g"></span>Smart AI&nbsp;<b style="color:#f1f5f9;margin-left:auto">Ready</b></div>', unsafe_allow_html=True)
        st.caption("An AI reads the video and finds the best moments for you.")
    else:
        st.markdown('<div class="status-badge"><span class="s-dot dot-a"></span>Basic Mode&nbsp;<b style="color:#f1f5f9;margin-left:auto">Active</b></div>', unsafe_allow_html=True)
        st.caption("Clips are picked using simple rules instead of AI. Ask whoever set this up to add an AI key for smarter results.")

    st.divider()
    if st.button("🗑️ Clear Output Clips", use_container_width=True):
        clean_directory(OUTPUT_DIR)
        st.success("Cleared!")

# ── Hero (single markdown block, no nested columns) ───────────────────────────
st.markdown("""
<div class="hero">
    <div class="hero-badge"><span class="dot"></span>AI-Powered &nbsp;·&nbsp; Free &nbsp;·&nbsp; Open Source</div>
    <span class="hero-h1">Clip Smarter.<br>Go Viral Faster.</span>
    <span class="hero-sub">Extract the best moments from any YouTube video — auto-detected by AI or trimmed manually. Export as Shorts, Reels, or TikToks instantly.</span>
    <div class="hero-line"></div>
</div>
""", unsafe_allow_html=True)

st.markdown(
    '<div style="text-align:center;color:var(--text2);font-size:.82rem;margin:-1.2rem 0 1.8rem;">'
    '⚙️ Video shape, subtitles, and other settings are in the sidebar on the left — tap '
    '<b style="color:var(--p2)">☰</b> in the top-left corner if you don\'t see it.</div>',
    unsafe_allow_html=True)

# ── URL Input (columns only for input + button, nothing else) ─────────────────
url_col, btn_col = st.columns([5, 1])
with url_col:
    youtube_url = st.text_input("url", placeholder="🔗  Paste a YouTube URL here…", label_visibility="collapsed")
with btn_col:
    fetch_btn = st.button("Load  →", use_container_width=True, type="primary")

st.markdown("<div style='margin-bottom:2rem'></div>", unsafe_allow_html=True)

# ── Load Video ─────────────────────────────────────────────────────────────────
if fetch_btn and youtube_url:
    with st.spinner("Fetching video metadata & subtitles…"):
        info = get_video_info(youtube_url)
        if info:
            st.session_state.video_info = info
            st.session_state.local_source_path = None
            st.session_state.ai_clips = []
            raw = fetch_transcript(info["id"])
            st.session_state.raw_transcript = raw or []
            st.session_state.transcript_chunks = format_transcript_chunks(raw) if raw else []
            st.toast("Video loaded!", icon="✅")
        else:
            st.error("Couldn't load video — check the URL and try again.")

# ── Main ───────────────────────────────────────────────────────────────────────
if st.session_state.video_info:
    info = st.session_state.video_info
    chunks = st.session_state.transcript_chunks or []

    # Meta banner
    st.markdown('<div class="meta-card">', unsafe_allow_html=True)
    ic, dc = st.columns([1, 2.6])
    with ic:
        if info.get("thumbnail"):
            st.image(info["thumbnail"], use_container_width=True)
    with dc:
        subs = f"Subtitles — {len(chunks)} segments" if chunks else "No subtitles"
        st.markdown(f"""
        <div class="meta-title">{info['title']}</div>
        <div class="meta-row">
            <span class="meta-chip">📺 <b>{info['uploader']}</b></span>
            <span class="meta-chip">⏱ <b>{seconds_to_hms(info['duration'])}</b></span>
            <span class="meta-chip">👁 <b>{info['view_count']:,}</b></span>
            <span class="meta-chip">🗒 <b>{subs}</b></span>
        </div>""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    tab_ai, tab_manual, tab_gallery = st.tabs(["🤖  AI Clipping", "✂️  Manual Trim", "📂  Gallery"])

    # ── AI Tab ────────────────────────────────────────────────────────────────
    with tab_ai:
        if not st.session_state.ai_clips:
            st.markdown("""
            <div class="scan-box">
                <span class="scan-icon">🤖</span>
                <div>
                    <h3>Let AI Find the Best Parts</h3>
                    <p>Click "Scan & Find Clips" below and AI will find the most interesting moments in this video for you — no editing skills needed.</p>
                </div>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown('<p class="tab-hint">🤖 Here\'s what AI found. For each clip below: read the highlight, optionally drag to change its start/end time, then press <b style="color:var(--p2)">Cut This Clip</b> to save it.</p>', unsafe_allow_html=True)

        # ── Scan controls ──────────────────────────────────────────────────────
        nc_col, prompt_col = st.columns([1, 3])
        with nc_col:
            st.markdown('<span class="sb-lbl" style="margin-top:0">How Many Clips</span>', unsafe_allow_html=True)
            n_clips = st.selectbox("nc", [3, 5, 7], index=1, label_visibility="collapsed",
                help="How many highlight clips should we look for?")
        with prompt_col:
            st.markdown('<span class="sb-lbl" style="margin-top:0">Tell the AI What to Look For (optional)</span>', unsafe_allow_html=True)
            custom_prompt = st.text_input("cp", placeholder="e.g. focus on funny moments, find product demos, highlight key stats…", label_visibility="collapsed",
                help="Leave this blank and AI will pick the most engaging moments on its own.")

        sc, _ = st.columns([1, 2])
        with sc:
            if st.button("⚡  Scan & Find Clips", type="primary", use_container_width=True):
                scan_bar = st.progress(0, text="🧠 Reading through the transcript… 0%")
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(find_best_clips, chunks, info["title"], info["duration"],
                                          n_clips=n_clips, custom_prompt=custom_prompt)
                    start_t = time.time()
                    while not future.done():
                        elapsed = time.time() - start_t
                        pct = min(0.92, 1 - math.exp(-elapsed / 8.0))
                        stage = "🧠 Reading through the transcript…" if pct < 0.5 else "✨ Picking the best moments…"
                        scan_bar.progress(pct, text=f"{stage} {int(pct * 100)}%")
                        time.sleep(0.2)
                    clips, notice = future.result()
                scan_bar.progress(1.0, text="Done! 100%")
                scan_bar.empty()
                st.session_state.ai_clips = clips
                st.session_state.clip_scan_id += 1
                if notice:
                    st.warning(notice)
                st.toast(f"{len(clips)} clips found!", icon="🔥")

        if st.session_state.ai_clips:
            scan_id = st.session_state.clip_scan_id

            def _clip_edit_range(orig_i, clip):
                val = st.session_state.get(f"edit_range_{scan_id}_{orig_i}")
                if val:
                    s, e = _time_to_sec(val[0]), _time_to_sec(val[1])
                    if e > s:
                        return s, e
                return int(clip["start_sec"]), int(clip["end_sec"])

            # ── Sort & Filter ──────────────────────────────────────────────────
            sf1, sf2 = st.columns([1, 2])
            with sf1:
                st.markdown('<span class="sb-lbl" style="margin-top:0">Order</span>', unsafe_allow_html=True)
                sort_mode = st.selectbox("sort", ["Best First", "Video Order"], label_visibility="collapsed",
                    help="'Best First' shows the clips most likely to perform well at the top. 'Video Order' shows them in the order they appear in the video.")
            with sf2:
                all_cats = sorted(set(c["category"] for c in st.session_state.ai_clips))
                st.markdown('<span class="sb-lbl" style="margin-top:0">Show Only</span>', unsafe_allow_html=True)
                cat_filter = st.multiselect("cat", all_cats, default=all_cats, label_visibility="collapsed",
                    help="Uncheck a type to hide those clips.")

            display_clips = [(i, c) for i, c in enumerate(st.session_state.ai_clips) if c["category"] in cat_filter]
            if sort_mode == "Best First":
                display_clips.sort(key=lambda x: x[1]["viral_score"], reverse=True)

            # ── Header + Batch Render ──────────────────────────────────────────
            hd_col, br_col = st.columns([2, 1])
            with hd_col:
                n_disp = len(display_clips)
                st.markdown(f'<div class="sec-head"><span class="sec-lbl">Results</span><span class="sec-cnt">{n_disp} Clip{"s" if n_disp!=1 else ""}</span></div>', unsafe_allow_html=True)
            with br_col:
                if st.button("✂️  Cut All Clips at Once", use_container_width=True):
                    n_total = len(display_clips)
                    prog = st.progress(0, text="Starting…")

                    if not st.session_state.local_source_path or not os.path.exists(st.session_state.local_source_path):
                        st.session_state.local_source_path = _download_with_progress(prog, info["url"], f"source_{info['id']}")
                        if st.session_state.local_source_path:
                            prog.progress(1.0, text="⬇️ Download complete — preparing to cut…")

                    if st.session_state.local_source_path:
                        batch_err = None
                        n_done = 0
                        for b_idx, (orig_i, clip) in enumerate(display_clips):
                            r_start, r_end = _clip_edit_range(orig_i, clip)

                            def _render_hook(frac, _idx=b_idx, _title=clip["title"]):
                                overall = (_idx + frac) / n_total
                                prog.progress(max(0.0, min(1.0, overall)),
                                              text=f"✂️ Cutting clip {_idx+1}/{n_total} — {int(frac*100)}%: {_title}")

                            try:
                                render_clip(st.session_state.local_source_path,
                                    r_start, r_end,
                                    output_name=f"{info['id']}_{clip['title']}",
                                    aspect_ratio=aspect_ratio, crop_mode=crop_mode,
                                    transcript_items=st.session_state.raw_transcript,
                                    burn_captions=burn_captions,
                                    caption_style=caption_style, accent_color=accent_color,
                                    caption_position=caption_position, caption_custom_pct=caption_custom_pct,
                                    progress_callback=_render_hook)
                                n_done += 1
                            except Exception as e:
                                batch_err = str(e)
                                break
                        prog.empty()
                        if batch_err:
                            st.error(f"Something went wrong after cutting {n_done}/{n_total} clips. Please try again.")
                            with st.expander("Show technical details"):
                                st.code(batch_err)
                        else:
                            st.success(f"✅ All {n_total} clips are ready! Find them in the 📂 Gallery tab.")
                    else:
                        prog.empty()
                        st.error("Couldn't download the source video. Please try again.")
                st.caption("Cuts every clip below in one go, using any timing you've adjusted. This can take several minutes for long videos — please wait for it to finish instead of clicking again.")

            # ── Clip cards ─────────────────────────────────────────────────────
            for orig_i, clip in display_clips:
                st.markdown('<div class="clip-card">', unsafe_allow_html=True)
                st.markdown(f"""
                <div class="clip-num">Clip {orig_i+1:02d}</div>
                <div class="clip-title">{clip['title']}</div>
                <div class="pills">
                    <span class="pill p-fire">🔥 {clip['viral_score']}/100</span>
                    <span class="pill p-cat">{clip['category']}</span>
                    <span class="pill p-time">⏱ {clip['start_time']} → {clip['end_time']} · {int(clip['duration_sec'])}s</span>
                    <span class="pill p-src">{clip.get('source','AI')}</span>
                </div>
                <div class="clip-hook">💡 <b>Why it's good:</b> {clip['hook']}</div>
                """, unsafe_allow_html=True)

                with st.expander("🎯 Change the Start & End Time (optional)"):
                    edit_fmt = "HH:mm:ss" if info["duration"] >= 3600 else "mm:ss"
                    edit_start_t, edit_end_t = st.slider(
                        "Drag either end to change where the clip starts and stops",
                        min_value=_sec_to_time(0), max_value=_sec_to_time(info["duration"]),
                        value=(_sec_to_time(clip["start_sec"]), _sec_to_time(clip["end_sec"])),
                        format=edit_fmt, key=f"edit_range_{scan_id}_{orig_i}")
                    edit_start, edit_end = _time_to_sec(edit_start_t), _time_to_sec(edit_end_t)
                    if edit_end <= edit_start:
                        st.warning("End must be after start.")
                    else:
                        st.markdown(f'<div class="dur-strip"><div><span class="di-lbl">New Length</span><span class="di-val">{seconds_to_hms(edit_start)} → {seconds_to_hms(edit_end)} · {edit_end - edit_start}s</span></div></div>', unsafe_allow_html=True)

                r_start, r_end = _clip_edit_range(orig_i, clip)
                bcol, _ = st.columns([1, 2])
                with bcol:
                    cut_clicked = st.button("✂️  Cut This Clip", key=f"r_{scan_id}_{orig_i}", type="primary", use_container_width=True)
                st.caption("Downloads the video once, then cuts out this part. Short videos finish in under a minute — long ones can take several minutes. Please don't click this again or navigate away while it's running; that will cancel it and you'll have to start over. It's saved to the 📂 Gallery tab when done.")
                if cut_clicked:
                    err_detail = None
                    try:
                        out = _cut_clip_with_progress(
                            info["url"], f"source_{info['id']}", r_start, r_end,
                            output_name=f"{info['id']}_{clip['title']}",
                            render_kwargs=dict(
                                aspect_ratio=aspect_ratio, crop_mode=crop_mode,
                                transcript_items=st.session_state.raw_transcript,
                                burn_captions=burn_captions,
                                caption_style=caption_style, accent_color=accent_color,
                                caption_position=caption_position, caption_custom_pct=caption_custom_pct))
                    except Exception as e:
                        out, err_detail = None, str(e)
                    if out:
                        st.success("✅ Clip ready! Find it anytime in the 📂 Gallery tab."); st.video(out)
                    else:
                        st.error("Something went wrong while cutting this clip. Please try again.")
                        if err_detail:
                            with st.expander("Show technical details"):
                                st.code(err_detail)
                st.markdown('</div>', unsafe_allow_html=True)

    # ── Manual Tab ────────────────────────────────────────────────────────────
    with tab_manual:
        st.markdown('<p class="tab-hint">✂️ Watch the video below, then drag the slider to pick exactly where your clip starts and ends.</p>', unsafe_allow_html=True)

        st.video(info["url"])
        st.divider()

        st.markdown('<span class="sb-lbl" style="margin-top:0">Drag to Select Your Clip</span>', unsafe_allow_html=True)
        manual_fmt = "HH:mm:ss" if info["duration"] >= 3600 else "mm:ss"
        default_end = min(45, int(info["duration"]))
        start_t, end_t = st.slider(
            "Clip range", min_value=_sec_to_time(0), max_value=_sec_to_time(info["duration"]),
            value=(_sec_to_time(15), _sec_to_time(default_end)),
            format=manual_fmt, label_visibility="collapsed")
        calc_start, calc_end = _time_to_sec(start_t), _time_to_sec(end_t)

        t1, t2 = st.columns(2)
        with t1:
            st.markdown('<span class="sb-lbl" style="margin-top:0">Starts At</span>', unsafe_allow_html=True)
            st.markdown(f'<div class="time-box">{seconds_to_hms(calc_start)}</div>', unsafe_allow_html=True)
        with t2:
            st.markdown('<span class="sb-lbl" style="margin-top:0">Ends At</span>', unsafe_allow_html=True)
            st.markdown(f'<div class="time-box">{seconds_to_hms(calc_end)}</div>', unsafe_allow_html=True)

        clip_len = calc_end - calc_start
        if clip_len > 0:
            mode_label = "Keep it all" if crop_mode == "blur_pad" else "Zoomed in"
            st.markdown(f"""
            <div class="dur-strip">
                <div><span class="di-lbl">Length</span><span class="di-val">{int(clip_len)}s &nbsp;·&nbsp; {seconds_to_hms(int(clip_len))}</span></div>
                <div><span class="di-lbl">Shape</span><span class="di-val">{aspect_ratio}</span></div>
                <div><span class="di-lbl">Style</span><span class="di-val">{mode_label}</span></div>
            </div>""", unsafe_allow_html=True)
        else:
            st.warning("End time must be after the start time.")

        rc2, _ = st.columns([1, 2])
        with rc2:
            cut_manual_clicked = st.button("✂️  Cut This Clip", type="primary", use_container_width=True)
        st.caption("Downloads the video once and cuts out just this part — usually under a minute. Saved to the 📂 Gallery tab when it's done.")
        if cut_manual_clicked:
            if clip_len <= 0:
                st.error("Invalid time range.")
            else:
                err_detail = None
                try:
                    out = _cut_clip_with_progress(
                        info["url"], f"source_{info['id']}", calc_start, calc_end,
                        output_name=f"manual_{info['id']}_{seconds_to_hms(calc_start)}",
                        render_kwargs=dict(
                            aspect_ratio=aspect_ratio, crop_mode=crop_mode,
                            transcript_items=st.session_state.raw_transcript,
                            burn_captions=burn_captions,
                            caption_style=caption_style, accent_color=accent_color,
                            caption_position=caption_position, caption_custom_pct=caption_custom_pct))
                except Exception as e:
                    out, err_detail = None, str(e)
                if out:
                    st.success("✅ Clip ready! Find it anytime in the 📂 Gallery tab."); st.video(out)
                else:
                    st.error("Something went wrong while cutting this clip. Please try again.")
                    if err_detail:
                        with st.expander("Show technical details"):
                            st.code(err_detail)

    # ── Gallery Tab ───────────────────────────────────────────────────────────
    with tab_gallery:
        st.markdown('<p class="tab-hint">📂 Every clip you\'ve rendered, ready to preview and download.</p>', unsafe_allow_html=True)
        files = sorted(OUTPUT_DIR.glob("*.mp4"), key=os.path.getmtime, reverse=True)
        if not files:
            st.markdown("""
            <div class="empty-state">
                <span class="empty-icon">📂</span>
                <h3>No clips yet</h3>
                <p>Render clips from the AI or Manual tabs — they'll all appear here for download.</p>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="sec-head"><span class="sec-lbl">Rendered</span><span class="sec-cnt">{len(files)} Clip{"s" if len(files)!=1 else ""}</span></div>', unsafe_allow_html=True)
            for fp in files:
                st.markdown('<div class="gallery-card">', unsafe_allow_html=True)
                vc, ic2 = st.columns([2, 1])
                with vc:
                    st.video(str(fp))
                with ic2:
                    size_mb = round(os.path.getsize(fp) / (1024*1024), 2)
                    st.markdown(f"""
                    <div style="margin-bottom:.9rem">
                        <div style="font-size:.85rem;font-weight:700;color:var(--text0);word-break:break-all;line-height:1.4">{fp.name}</div>
                        <div style="font-size:.75rem;color:var(--text2);margin-top:5px">📁 {size_mb} MB</div>
                    </div>""", unsafe_allow_html=True)
                    with open(fp, "rb") as f:
                        st.download_button("⬇️  Download", data=f.read(), file_name=fp.name, mime="video/mp4", use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)

else:
    st.markdown("""
    <div class="empty-state" style="padding:2.5rem 2rem 1.5rem">
        <span class="empty-icon">🎬</span>
        <h3>Paste a link above to get started</h3>
        <p>Here's how it works:</p>
    </div>
    <div style="max-width:560px;margin:0 auto 3rem;display:flex;flex-direction:column;gap:14px;">
        <div class="scan-box">
            <span class="scan-icon">1️⃣</span>
            <div><h3>Paste a YouTube link</h3><p>Copy any YouTube video's URL and paste it into the box above, then hit "Load".</p></div>
        </div>
        <div class="scan-box">
            <span class="scan-icon">2️⃣</span>
            <div><h3>Pick your favorite moment</h3><p>Let AI find the best highlights automatically, or drag a slider to choose your own start and end point.</p></div>
        </div>
        <div class="scan-box">
            <span class="scan-icon">3️⃣</span>
            <div><h3>Download and share</h3><p>Press Render, then download your finished clip — ready for Shorts, Reels, or TikTok.</p></div>
        </div>
    </div>""", unsafe_allow_html=True)
