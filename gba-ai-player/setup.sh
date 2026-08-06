#!/usr/bin/env bash
# Setup script for GBA AI Player on Nobara Linux (Fedora-based)
# Nobara is RPM-based and ships with RPM Fusion enabled by default.
set -euo pipefail

echo "=== GBA AI Player - Nobara Linux Setup ==="

# 1. Install system dependencies
echo "[1/5] Installing system dependencies..."
sudo dnf install -y \
    python3 python3-pip python3-virtualenv \
    mgba-qt \
    x11-utils \
    wget curl git \
    mesa-libGL mesa-libEGL libX11 libXext libXrender \
    ffmpeg \
    xdotool \
    wtype \
    libappindicator-gtk3 \
    gtk3

# 2. Install Ollama
echo "[2/5] Installing Ollama..."
if ! command -v ollama &>/dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "Ollama already installed"
fi

# 3. Pull required models
echo "[3/5] Pulling AI models (this may take a while)..."
echo "  - llava: vision-capable model for screen understanding"
echo "  - llama3: text model fallback for state-only reasoning"
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
echo "Nobara-specific notes:"
echo "  - Nobara ships with RPM Fusion (free + non-free) pre-enabled, so mgba-qt"
echo "    and ffmpeg are available directly in the repos."
echo "  - xdotool (X11) and wtype (Wayland) are installed for keyboard input."
echo "    The AI will automatically detect which backend to use."
echo "  - If you are on a Wayland session, mGBA window capture via mss may fall"
echo "    back to the configured capture_region in config/user.yaml."
echo "    For best results, either:"
echo "      a) launch mGBA under XWayland and note its geometry with xwininfo, or"
echo "      b) set capture_region manually to match your mGBA window position."
echo "  - On Nobara GameOS or GNOME Gaming Edition, you may need to allow"
echo "    Ollama through the firewall for local-only access:"
echo "      sudo firewall-cmd --add-service=ollama --permanent && sudo firewall-cmd --reload"
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
