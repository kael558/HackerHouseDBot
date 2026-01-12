https://discord.com/oauth2/authorize?client_id=1459938363439055054&permissions=2147534848&integration_type=0&scope=bot

# Deployment Guide - Discord Audio Bot

Complete guide for deploying your Discord Audio Bot to a Raspberry Pi.

---

## Prerequisites

### Hardware

- Raspberry Pi (3, 4, or 5 recommended)
- MicroSD card with Raspberry Pi OS installed
- Speaker connected via 3.5mm jack or HDMI
- Stable internet connection

### Software

- Windows PC with SSH client
- SSH access to your Raspberry Pi
- Discord Bot Token
- ElevenLabs API Key (for TTS)

---

## Step 1: Get Your API Keys

### Discord Bot Token

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to "Bot" section
4. Click "Add Bot"
5. Under "Token", click "Reset Token" and copy it (save this securely!)
6. Enable these "Privileged Gateway Intents":
   - Message Content Intent
7. Go to "OAuth2" > "URL Generator"
8. Select scopes:
   - `bot`
   - `applications.commands`
9. Select bot permissions:
   - Send Messages
   - Read Message History
   - Use Slash Commands
10. Copy the generated URL and open it in your browser to invite the bot to your server

### ElevenLabs API Key

1. Go to [ElevenLabs](https://elevenlabs.io/)
2. Sign up for a free account
3. Go to your profile settings
4. Copy your API key from the "API Keys" section

---

## Step 2: Configure Your Environment

1. In your project folder, copy the example environment file:

   ```
   .env.example -> .env
   ```

2. Edit `.env` and add your keys:

   ```
   DISCORD_TOKEN=your_actual_discord_token_here
   ELEVENLABS_API_KEY=your_actual_elevenlabs_key_here
   ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
   ```

3. Save the file

---

## Step 3: Configure Deployment Settings

1. Open `deploy.bat` in a text editor

2. Update these variables at the top:

   ```batch
   set "PI_HOST=raspberrypi.local"
   set "PI_USER=pi"
   ```

   Replace with your Raspberry Pi's:

   - Hostname or IP address (e.g., `192.168.1.100`)
   - SSH username (usually `pi`)

3. Save the file

---

## Step 4: Deploy to Raspberry Pi

1. Open Command Prompt or PowerShell

2. Navigate to your project directory:

   ```cmd
   cd C:\Users\Rahel\PycharmProjects\HackerHouseDBot
   ```

3. Run the deployment script:

   ```cmd
   deploy.bat
   ```

4. The script will:

   - Copy all files to your Raspberry Pi
   - Install dependencies (FFmpeg, yt-dlp, Python packages)
   - Set up the systemd service
   - Start the bot automatically

5. Wait for the deployment to complete

---

## Step 5: Verify Installation

### Check Bot Status

```bash
ssh pi@raspberrypi.local "sudo systemctl status discord-audio"
```

You should see:

- `Active: active (running)` in green
- Recent log entries showing the bot connected

### View Live Logs

```bash
ssh pi@raspberrypi.local "sudo journalctl -u discord-audio -f"
```

Look for:

```
INFO - Logged in as YourBotName#1234
INFO - FFmpeg mixer started
INFO - Bot is ready!
```

Press `Ctrl+C` to stop viewing logs.

---

## Step 6: Test the Bot

### In Discord:

1. Go to your Discord server where you invited the bot

2. Try these commands:

   **Play Music:**

   ```
   !play https://www.youtube.com/watch?v=dQw4w9WgXcQ
   ```

   **Check Queue:**

   ```
   !queue
   ```

   **Text-to-Speech:**

   ```
   /say Hello world! This is a test.
   ```

   **Volume Control:**

   ```
   !volume 50
   ```

   **Skip Track:**

   ```
   !skip
   ```

---

## Management Commands

### Restart Bot

```bash
ssh pi@raspberrypi.local "sudo systemctl restart discord-audio"
```

### Stop Bot

```bash
ssh pi@raspberrypi.local "sudo systemctl stop discord-audio"
```

### Start Bot

```bash
ssh pi@raspberrypi.local "sudo systemctl start discord-audio"
```

### View Recent Logs

```bash
ssh pi@raspberrypi.local "sudo journalctl -u discord-audio -n 50"
```

### Disable Auto-Start on Boot

```bash
ssh pi@raspberrypi.local "sudo systemctl disable discord-audio"
```

### Enable Auto-Start on Boot

```bash
ssh pi@raspberrypi.local "sudo systemctl enable discord-audio"
```

---

## Available Commands

### Music Commands (Prefix: `!`)

| Command           | Description                | Example                                 |
| ----------------- | -------------------------- | --------------------------------------- |
| `!play <url>`     | Add YouTube track to queue | `!play https://youtube.com/watch?v=...` |
| `!queue`          | Show current playlist      | `!queue`                                |
| `!skip`           | Skip current track         | `!skip`                                 |
| `!remove <index>` | Remove track from queue    | `!remove 2`                             |
| `!volume <0-200>` | Set music volume           | `!volume 75`                            |
| `!pause`          | Pause playback             | `!pause`                                |
| `!resume`         | Resume playback            | `!resume`                               |

### Speech Commands (Slash command: `/`)

| Command       | Description               | Example                      |
| ------------- | ------------------------- | ---------------------------- |
| `/say <text>` | Speak text via ElevenLabs | `/say Welcome to the party!` |

---

## Troubleshooting

### Bot Not Starting

1. Check service status:

   ```bash
   ssh pi@raspberrypi.local "sudo systemctl status discord-audio"
   ```

2. View error logs:
   ```bash
   ssh pi@raspberrypi.local "sudo journalctl -u discord-audio -n 100"
   ```

### Common Issues

**"DISCORD_TOKEN environment variable not set"**

- Your `.env` file is missing or not copied correctly
- Redeploy with `deploy.bat`

**"No audio output"**

- Check speaker connection
- Test audio: `ssh pi@raspberrypi.local "speaker-test -t wav -c 2"`
- Check ALSA device: `ssh pi@raspberrypi.local "aplay -l"`
- You may need to change `hw:0` in the FFmpeg command to your audio device

**"yt-dlp failed"**

- Update yt-dlp: `ssh pi@raspberrypi.local "sudo yt-dlp -U"`
- Check internet connection

**"TTS not working"**

- Verify your ElevenLabs API key is correct in `.env`
- Check if you have API quota remaining at [ElevenLabs](https://elevenlabs.io/)

### Update Bot

To update after making changes:

1. Edit files locally
2. Run `deploy.bat` again
3. The script will automatically restart the bot with new code

---

## File Locations on Raspberry Pi

| File          | Location                                          |
| ------------- | ------------------------------------------------- |
| Bot code      | `/home/pi/discord-audio-bot/discord_audio_bot.py` |
| Configuration | `/home/pi/discord-audio-bot/.env`                 |
| Queue state   | `/home/pi/discord-audio-bot/playlist.json`        |
| Logs          | `/home/pi/discord-audio-bot/logs/bot.log`         |
| System logs   | `journalctl -u discord-audio`                     |
| Service file  | `/etc/systemd/system/discord-audio.service`       |
| FIFO pipes    | `/tmp/music.pipe`, `/tmp/tts.pipe`                |

---

## Advanced Configuration

### Change Audio Output Device

1. SSH into your Pi
2. List audio devices:

   ```bash
   aplay -l
   ```

3. Note your device number (e.g., `card 1, device 0`)

4. Edit the bot file:

   ```bash
   nano /home/pi/discord-audio-bot/discord_audio_bot.py
   ```

5. Find the FFmpeg command and change `hw:0` to your device:

   ```python
   "-f", "alsa", "hw:1,0"  # card 1, device 0
   ```

6. Restart: `sudo systemctl restart discord-audio`

### Change ElevenLabs Voice

1. Visit [ElevenLabs Voice Library](https://elevenlabs.io/docs/voices/premade-voices)

2. Copy the Voice ID you want

3. Update your `.env` file:

   ```
   ELEVENLABS_VOICE_ID=your_new_voice_id_here
   ```

4. Redeploy with `deploy.bat`

---

## Performance Notes

- **CPU Usage**: ~5-15% on Raspberry Pi 4 during playback
- **Memory**: ~150MB RAM
- **Network**: Depends on audio quality (typically 128-256kbps)
- **Storage**: Minimal (no audio caching, streaming only)

---

## Security Notes

- Never commit your `.env` file to Git
- Keep your API keys private
- The bot runs as the `pi` user (not root)
- Only accept commands from trusted Discord servers

---

## Support

If you encounter issues:

1. Check the [Troubleshooting](#troubleshooting) section
2. Review logs with `journalctl -u discord-audio -f`
3. Verify your API keys are valid
4. Ensure your Raspberry Pi has internet access

---

## Configure Audio

pactl list sinks short
pactl info | grep "Default Sink"
pactl set-default-sink bluez_output.28_11_A5_EA_FD_DE.1
