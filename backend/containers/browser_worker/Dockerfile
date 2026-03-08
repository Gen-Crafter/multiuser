FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Chromium and its runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    libnss3 libnspr4 \
    libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 \
    libpango-1.0-0 libcairo2 \
    libatspi2.0-0 \
    libglib2.0-0 libdbus-1-3 libexpat1 \
    libx11-6 libxcb1 libxext6 libxi6 libxrender1 \
    fonts-liberation fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

COPY worker.py .

EXPOSE 9222 8080

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["python3", "worker.py"]
