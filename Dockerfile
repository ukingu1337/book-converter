FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends calibre wget p7zip-full && \
    which ebook-convert || (echo "ebook-convert NOT FOUND" && exit 1) && \
    rm -rf /var/lib/apt/lists/*

ENV QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu"
ENV QT_QPA_PLATFORM=offscreen

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]