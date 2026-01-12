#  Implementation Document

You can treat this as your **project README / system design doc**.

---

## 🎧 Discord Speaker Bot – Implementation Guide

### Purpose

A **headless Discord-controlled speaker system** running on a Raspberry Pi that:

* Plays YouTube audio locally
* Queues playlists
* Speaks text via ElevenLabs TTS
* Ducks music during speech
* Normalizes volume
* Survives reboots
* Runs unattended via systemd

---

## 🧠 High-Level Architecture

```
Discord (Text Commands)
        ↓
Python Bot (async)
        ↓
┌──────────────────────────┐
│   yt-dlp (music source)  │
│   ElevenLabs (TTS)       │
└──────────┬───────────────┘
           ↓ (FIFO pipes)
        FFmpeg Mixer
           ↓
        ALSA Speaker
```

---

## 🔑 Core Design Principles

* **FFmpeg does all audio work**
* **Python only orchestrates**
* **No audio DSP in Python**
* **Long-running FFmpeg process**
* **Named pipes (FIFO) for live injection**

This keeps CPU low and audio clean.

---

## 📦 Dependencies

### System

```bash
sudo apt install ffmpeg yt-dlp
```

### Python

```bash
pip install discord.py requests
```

---

## 📂 Files & Structure

```
/home/pi/
├── discord_audio_bot.py
├── playlist.json
└── logs/
```

---

## 🔁 Audio Pipes (FIFO)

Created at boot:

```bash
/tmp/music.pipe   # YouTube audio
/tmp/tts.pipe     # ElevenLabs speech
```

---

## 🔊 FFmpeg Mixer (Persistent)

```bash
ffmpeg \
-f wav -i /tmp/music.pipe \
-f wav -i /tmp/tts.pipe \
-filter_complex "
[0:a]loudnorm=I=-16:LRA=11:TP=-1.5[music];
[1:a]asplit=2[tts][sc];
[music][sc]sidechaincompress=threshold=0.02:ratio=10:attack=40:release=400[ducked];
[ducked][tts]amix=inputs=2:dropout_transition=0
" \
-f alsa hw:0
```

### What this does

* Normalizes YouTube loudness
* Ducks music when TTS is active
* Mixes speech + music cleanly
* Outputs to speaker

---

## 🎵 YouTube Queue System

* Backed by `asyncio.Queue`
* One track plays at a time
* Queue persists to `playlist.json`

### Persistence format

```json
{
  "queue": [
    "https://youtube.com/watch?v=...",
    "https://youtube.com/watch?v=..."
  ]
}
```

---

## 🗣 ElevenLabs TTS

* Triggered by `/say <text>`
* Audio written directly to FIFO
* Automatically ducks music
* Fully queued (no overlap glitches)

---

## 🎮 Discord Commands

### Music Control

| Command           | Description           |
| ----------------- | --------------------- |
| `!play <url>`     | Add YouTube track     |
| `!queue`          | Show current playlist |
| `!remove <index>` | Remove queued item    |
| `!skip`           | Skip current track    |
| `!pause`          | Pause playback        |
| `!resume`         | Resume playback       |
| `!volume <0–200>` | Set music volume      |

### Speech

| Command       | Description               |
| ------------- | ------------------------- |
| `/say <text>` | Speak text via ElevenLabs |

---

## 🧠 Playback State

```python
state = {
    "paused": False,
    "volume": 1.0,
    "current_process": None
}
```

---

## 🔁 systemd Auto-Start

### `/etc/systemd/system/discord-audio.service`

```ini
[Unit]
Description=Discord Audio Bot
After=network-online.target sound.target
Wants=network-online.target

[Service]
ExecStartPre=/usr/bin/mkfifo /tmp/music.pipe
ExecStartPre=/usr/bin/mkfifo /tmp/tts.pipe
ExecStart=/usr/bin/python3 /home/pi/discord_audio_bot.py
WorkingDirectory=/home/pi
User=pi
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

---

## 🔍 Debugging & Logs

```bash
journalctl -u discord-audio -f
```

---

## 🛡 Stability Notes

* FIFO pipes prevent blocking
* FFmpeg crash won’t kill Python
* Python restart rehydrates queue
* Audio continues uninterrupted

---

## 🏆 Summary

You now have a **broadcast-grade, headless Discord-controlled speaker system** that:

✔ Runs 24/7
✔ Survives reboots
✔ Sounds professional
✔ Scales cleanly
✔ Uses minimal Pi resources


