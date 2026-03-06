#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# LinkedIn Campaign Platform – Ubuntu 24.04 Setup Script
# ============================================================

echo "╔══════════════════════════════════════════════════╗"
echo "║  LinkedIn Campaign Platform – Ubuntu 24.04 Setup ║"
echo "╚══════════════════════════════════════════════════╝"

# ── System update ────────────────────────────────────────────
sudo apt-get update && sudo apt-get upgrade -y

# ── Core dependencies ────────────────────────────────────────
sudo apt-get install -y \
  curl wget git build-essential software-properties-common \
  apt-transport-https ca-certificates gnupg lsb-release \
  python3 python3-pip python3-venv \
  libpq-dev libffi-dev libssl-dev

# ── Docker ───────────────────────────────────────────────────
if ! command -v docker &> /dev/null; then
  echo "Installing Docker..."
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker "$USER"
  echo "Docker installed. You may need to log out and back in for group changes."
fi

# ── Docker Compose (standalone, if plugin not sufficient) ────
if ! docker compose version &> /dev/null; then
  echo "Installing Docker Compose standalone..."
  sudo curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" -o /usr/local/bin/docker-compose
  sudo chmod +x /usr/local/bin/docker-compose
fi

# ── Node.js 20 LTS ──────────────────────────────────────────
if ! command -v node &> /dev/null; then
  echo "Installing Node.js 20..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi

# ── Playwright system deps ───────────────────────────────────
echo "Installing Playwright system dependencies..."
sudo npx playwright install-deps 2>/dev/null || true

# ── Ollama ───────────────────────────────────────────────────
bash "$(dirname "$0")/install-ollama.sh"

# ── Environment file ─────────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  # Generate secrets
  sed -i "s|change-me-to-a-random-64-char-string|$(openssl rand -hex 32)|" .env
  sed -i "s|change-me-jwt-secret-key|$(openssl rand -hex 32)|" .env
  sed -i "s|change-me-fernet-key-base64|$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')|" .env
  echo ".env file created with generated secrets."
fi

# ── Kernel tuning for 2000 concurrent users ──────────────────
echo "Applying kernel tuning..."
sudo sysctl -w net.core.somaxconn=65535
sudo sysctl -w net.ipv4.tcp_max_syn_backlog=65535
sudo sysctl -w vm.overcommit_memory=1
echo "net.core.somaxconn=65535" | sudo tee -a /etc/sysctl.conf
echo "net.ipv4.tcp_max_syn_backlog=65535" | sudo tee -a /etc/sysctl.conf

echo ""
echo "✅ Setup complete. Run:  docker compose up --build -d"
