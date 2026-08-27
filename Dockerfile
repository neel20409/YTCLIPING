FROM python:3.11-slim

# ffmpeg for cutting/rendering clips, fonts-dejavu-core so burned-in captions
# (libass) have a font to render with — same requirement as packages.txt
# needed for Streamlit Community Cloud.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

# $PORT is injected by Railway/Render; default to 8501 for local `docker run`.
CMD streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.headless=true
