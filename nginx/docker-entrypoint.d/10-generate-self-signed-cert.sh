#!/bin/sh
set -eu

DOMAIN="${CERTBOT_DOMAIN:-example.com}"
LIVE_DIR="/etc/letsencrypt/live/${DOMAIN}"

if [ ! -f "${LIVE_DIR}/fullchain.pem" ] || [ ! -f "${LIVE_DIR}/privkey.pem" ]; then
  mkdir -p "${LIVE_DIR}"

  if [ ! -f "${LIVE_DIR}/fullchain.pem" ] || [ ! -f "${LIVE_DIR}/privkey.pem" ]; then
    openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
      -keyout "${LIVE_DIR}/privkey.pem" \
      -out "${LIVE_DIR}/fullchain.pem" \
      -subj "/CN=${DOMAIN}" >/dev/null 2>&1 || true
  fi
fi
