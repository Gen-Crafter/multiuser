#!/usr/bin/env bash
set -euo pipefail

echo "── Installing Ollama ──────────────────────────────"

if command -v ollama &> /dev/null; then
  echo "Ollama already installed: $(ollama --version)"
else
  curl -fsSL https://ollama.com/install.sh | sh
fi

# Start Ollama service
sudo systemctl enable ollama 2>/dev/null || true
sudo systemctl start ollama 2>/dev/null || true

# Wait for Ollama to be ready
echo "Waiting for Ollama to start..."
for i in $(seq 1 30); do
  if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "Ollama is ready."
    break
  fi
  sleep 2
done

# Pull default models
echo "Pulling default LLM model (llama3)..."
ollama pull llama3 || echo "Warning: could not pull llama3. Pull manually later."

echo "Pulling embedding model (nomic-embed-text)..."
ollama pull nomic-embed-text || echo "Warning: could not pull nomic-embed-text. Pull manually later."

echo "✅ Ollama setup complete."
