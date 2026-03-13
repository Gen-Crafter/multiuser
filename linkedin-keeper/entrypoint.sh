#!/bin/bash
set -e

# Clean stale Chromium profile locks
rm -f /app/linkedin-profile/SingletonLock /app/linkedin-profile/SingletonSocket /app/linkedin-profile/SingletonCookie 2>/dev/null || true

# Clean stale X lock
rm -f /tmp/.X99-lock /tmp/.X11-unix/.X99-lock 2>/dev/null || true

XVFB_DISPLAY=:99
Xvfb $XVFB_DISPLAY -screen 0 1280x720x24 -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
export DISPLAY=$XVFB_DISPLAY

# Give X server a moment to initialize
sleep 2

# Minimal window manager to keep things tidy
fluxbox -display :99.0 &
x11vnc -display :99.0 -nopw -forever -shared -rfbport 5901 -quiet &

# start noVNC/websockify on 6080 serving /usr/share/novnc
websockify --web /usr/share/novnc 0.0.0.0:6080 localhost:5901 &

exec node /app/index.js
