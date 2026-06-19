FROM python:3.12-slim

# ===== системные пакеты =====
RUN apt-get update && apt-get install -y --no-install-recommends     calibre     wget     curl     ca-certificates     fonts-liberation     xdg-utils     libglib2.0-0     libnss3     libx11-6     libx11-xcb1     libxcb1     libxcomposite1     libxdamage1     libxrandr2     libxkbcommon-x11-0     libdbus-1-3     libgtk-3-0     libasound2     libatk1.0-0     libatk-bridge2.0-0  && rm -rf /var/lib/apt/lists/*

# ===== headless Qt / Chromium фиксы =====
ENV QT_QPA_PLATFORM=offscreen
ENV QT_OPENGL=software
ENV QTWEBENGINE_DISABLE_SANDBOX=1
ENV QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu --disable-software-rasterizer"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN which ebook-convert || (echo "ebook-convert NOT FOUND" && exit 1)

COPY . .

CMD ["python", "bot.py"]
