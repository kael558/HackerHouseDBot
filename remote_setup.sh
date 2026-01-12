#!/bin/bash
set -e

echo "[Remote] Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y ffmpeg python3-pip

echo "[Remote] Checking yt-dlp..."
if ! command -v yt-dlp &> /dev/null; then
    echo "[Remote] Installing yt-dlp..."
    sudo wget https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -O /usr/local/bin/yt-dlp
    sudo chmod a+rx /usr/local/bin/yt-dlp
fi

echo "[Remote] Installing Python dependencies..."
cd REMOTE_DIR_PLACEHOLDER
pip3 install -r requirements.txt --break-system-packages || pip3 install -r requirements.txt

echo "[Remote] Making bot executable..."
chmod +x discord_audio_bot.py

echo "[Remote] Installing systemd service..."
sudo mv /tmp/discord-audio.service /etc/systemd/system/
sudo systemctl daemon-reload

echo "[Remote] Enabling service to start on boot..."
sudo systemctl enable discord-audio.service

echo "[Remote] Restarting service..."
sudo systemctl restart discord-audio.service

echo "[Remote] Checking service status..."
sudo systemctl status discord-audio.service --no-pager || true

echo ""
echo "[Remote] Setup complete!"
