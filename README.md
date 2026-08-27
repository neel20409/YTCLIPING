# 🎬 YTCliping - AI YouTube Video Clipper & Shorts Generator

An AI-powered web application built with **Streamlit**, **Google Gemini AI**, and **yt-dlp** that automatically analyzes YouTube videos, extracts transcripts, identifies viral/engaging highlights, and cuts short-form video clips for TikTok, YouTube Shorts, and Instagram Reels.

## ✨ Features

- 🤖 **AI-Powered Highlight Detection**: Uses Google Gemini API to analyze transcript context and detect key moments, hooks, and highlights.
- ⚡ **Automated Video Downloading & Cutting**: Powered by `yt-dlp` and `FFmpeg` for high-quality video segment extraction.
- 📜 **Transcript Processing**: Automatic extraction of YouTube video captions and transcripts via `youtube-transcript-api`.
- 🎛️ **Interactive Streamlit UI**: User-friendly web interface with live progress bars, video preview, and custom clip rendering options.
- 🛡️ **Windows UTF-8 & Legacy Support**: Robust handling for special characters in video titles and filenames.

---

## 🛠️ Tech Stack

- **Frontend / Web UI**: [Streamlit](https://streamlit.io/)
- **AI Model**: [Google Gemini AI (google-genai)](https://ai.google.dev/)
- **Video Processing**: `yt-dlp`, `MoviePy` / `FFmpeg`
- **Transcript Extraction**: `youtube-transcript-api`
- **Language**: Python 3.9+

---

## 🚀 Quickstart Guide

### 1. Prerequisites
Ensure you have **Python 3.9+** and **FFmpeg** installed on your system.

### 2. Clone the Repository
```bash
git clone https://github.com/<YOUR-USERNAME>/YTCliping.git
cd YTCliping
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the root directory and add your Google Gemini API key:
```env
GEMINI_API_KEY=your_gemini_api_key_here
```

### 5. Run the Application
```bash
streamlit run app.py
```

---

## 📁 Project Structure

```
YTCliping/
├── app.py                 # Main Streamlit web application interface
├── config.py              # Configuration & path settings
├── core/
│   ├── ai_clipper.py      # Gemini AI prompt engine & moment identifier
│   ├── downloader.py      # yt-dlp video & audio download logic
│   ├── transcript.py      # YouTube transcript fetcher & parser
│   ├── video_editor.py    # Video cutting & rendering backend
│   └── utils.py           # Helper utilities
├── requirements.txt       # Python dependencies
└── .gitignore             # Git ignore rules
```

---

## 📜 License
[MIT](LICENSE)
