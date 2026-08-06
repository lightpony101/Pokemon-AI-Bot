#!/usr/bin/env bash
# Setup script for GBA AI Player on Debian/Ubuntu Linux
set -euo pipefail

echo "=== GBA AI Player - Linux Setup ==="

# 1. Install system dependencies
echo "[1/5] Installing system dependencies..."
sudo apt update
sudo apt install -y \
    python3 python3-pip python3-venv \
    mgba-qt \
    x11-utils \
    wget curl git \
    libgl1 libegl1 libx11-6 libxext6 libxrender1 \
    ffmpeg

# 2. Install Ollama
echo "[2/5] Installing Ollama..."
if ! command -v ollama &>/dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "Ollama already installed"
fi

# 3. Pull required models
echo "[3/5] Pulling AI models (this may take a while)..."
ollama pull llava
ollama pull llama3

# 4. Set up Python virtual environment
echo "[4/5] Setting up Python environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 5. Create config from template
echo "[5/5] Creating default config..."
if [ ! -f config/user.yaml ]; then
    cp config/default.yaml config/user.yaml
    echo "Edit config/user.yaml to set your ROM path and capture region"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Place your Pokémon ROM in the project directory"
echo "  2. Edit config/user.yaml and set emulator.rom_path"
echo "  3. Adjust capture_region in config/user.yaml for your monitor setup"
echo "  4. Start Ollama: ollama serve"
echo "  5. Run: source .venv/bin/activate && python -m src.main config/user.yaml"
echo ""
echo "Tip: Use 'xwininfo' to find your mGBA window geometry for capture_region"
echo "     xwininfo -root -tree | grep -i mgba"
