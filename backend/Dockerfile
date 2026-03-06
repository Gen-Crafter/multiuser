FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for Playwright + psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl wget gnupg \
    libnss3 libatk-bridge2.0-0 libdrm2 libxcomposite1 \
    libxdamage1 libxrandr2 libgbm1 libasound2 \
    libpango-1.0-0 libcairo2 libatspi2.0-0 libcups2 \
    libxfixes3 libxkbcommon0 libxshmfence1 \
    libglib2.0-0 libdbus-1-3 libexpat1 \
    libnss3 libnspr4 libx11-6 libxcb1 libxext6 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libxtst6 libxi6 libxrender1 libxss1 \
    libgdk-pixbuf-2.0-0 libgtk-3-0 \
    fonts-liberation fonts-noto-color-emoji fonts-unifont xdg-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Install Playwright Chromium browser binary only (skip install-deps which fails on Debian Trixie)
RUN playwright install chromium

COPY . .

# Create session storage directory
RUN mkdir -p /app/sessions

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--loop", "uvloop"]
