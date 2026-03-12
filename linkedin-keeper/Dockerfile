# Backend for LinkedIn session keeper
FROM mcr.microsoft.com/playwright:v1.58.2-jammy

WORKDIR /app

# Install deps first for caching
COPY package.json ./
RUN npm install --omit=dev

# VNC + Xvfb + minimal WM (noninteractive to skip tz prompts)
ENV DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC
RUN ln -fs /usr/share/zoneinfo/Etc/UTC /etc/localtime && \
    apt-get update && apt-get install -y --no-install-recommends \
    xvfb x11vnc fluxbox tzdata novnc websockify && \
    dpkg-reconfigure -f noninteractive tzdata && \
    rm -rf /var/lib/apt/lists/*

# Copy source
COPY index.js ./
COPY public ./public
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV PORT=3001 \
    FRONTEND_ORIGIN=* \
    HEADLESS=false

VOLUME ["/app/linkedin-profile"]

EXPOSE 3001 5901 6080

ENTRYPOINT ["/app/entrypoint.sh"]
