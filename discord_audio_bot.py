#!/usr/bin/env python3
"""
Discord Audio Bot - Headless speaker system for Raspberry Pi
Uses sounddevice for direct audio output with mixing
Plays YouTube audio and speaks via ElevenLabs TTS with professional audio mixing
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict
import signal
import threading
import numpy as np
import sounddevice as sd
import yt_dlp
from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import commands
import requests
from io import BytesIO

# Load .env
load_dotenv()

# Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Default: Rachel voice
AUTHORIZED_USER = "kael558"  # Only this user can restart the bot
PLAYLIST_FILE = Path("playlist.json")
LOG_DIR = Path("logs")

# Setup logging
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("discord_audio_bot")

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Audio configuration
SAMPLE_RATE = 48000
CHANNELS = 2
BLOCKSIZE = 4096

# Global state
state = {
    "paused": False,
    "volume": 1.0,
    "skip": False,
    "queue": asyncio.Queue(),
    "current_track": None,
    "playback_task": None,
    "music_task": None,
    "yt_task": None,
    "audio_stream": None,
    "music_buffer": None,  # Ring buffer for music
    "tts_buffer": None,    # Ring buffer for TTS
    "buffer_lock": threading.Lock(),
    "audio_device_id": None,  # Selected audio device
}


# ============================
# Queue Persistence
# ============================

def load_queue():
    """Load queue from disk"""
    if PLAYLIST_FILE.exists():
        try:
            with open(PLAYLIST_FILE, 'r') as f:
                data = json.load(f)
                return data.get("queue", [])
        except Exception as e:
            logger.error(f"Failed to load queue: {e}")
    return []


def save_queue():
    """Save queue to disk"""
    try:
        items = list(state["queue"]._queue)
        with open(PLAYLIST_FILE, 'w') as f:
            json.dump({"queue": items}, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save queue: {e}")


# ============================
# Audio Mixer (sounddevice-based)
# ============================

class AudioBuffer:
    """Thread-safe queue-based audio buffer"""
    def __init__(self, maxsize=SAMPLE_RATE * 10):  # 10 seconds buffer
        self.buffer = []
        self.lock = threading.Lock()
        self.maxsize = maxsize
        self.current_size = 0

    def write(self, data: np.ndarray):
        """Write audio data to buffer"""
        with self.lock:
            data_len = len(data)
            if data_len == 0:
                return

            # Check if buffer is getting too full
            if self.current_size + data_len > self.maxsize:
                # Drop oldest chunks until there's room
                while self.buffer and self.current_size + data_len > self.maxsize:
                    oldest = self.buffer.pop(0)
                    self.current_size -= len(oldest)
                logger.warning(f"Audio buffer overflow, dropped {data_len} frames")

            # Add new data
            self.buffer.append(data.copy())
            self.current_size += data_len

    def read(self, frames: int) -> np.ndarray:
        """Read audio data from buffer, return silence if empty"""
        with self.lock:
            if not self.buffer or self.current_size == 0:
                return np.zeros((frames, CHANNELS), dtype=np.float32)

            result = np.zeros((frames, CHANNELS), dtype=np.float32)
            read_offset = 0

            while read_offset < frames and self.buffer:
                chunk = self.buffer[0]
                chunk_len = len(chunk)
                remaining = frames - read_offset

                if chunk_len <= remaining:
                    # Use entire chunk
                    result[read_offset:read_offset + chunk_len] = chunk
                    read_offset += chunk_len
                    self.buffer.pop(0)
                    self.current_size -= chunk_len
                else:
                    # Use part of chunk
                    result[read_offset:read_offset + remaining] = chunk[:remaining]
                    self.buffer[0] = chunk[remaining:]
                    self.current_size -= remaining
                    read_offset += remaining

            return result

    def clear(self):
        """Clear the buffer"""
        with self.lock:
            self.buffer.clear()
            self.current_size = 0

    def available_frames(self):
        """Get number of frames available in buffer"""
        with self.lock:
            return self.current_size


def audio_callback(outdata, frames, time_info, status):
    """Audio callback for sounddevice - mixes music and TTS"""
    if status:
        logger.warning(f"Audio callback status: {status}")

    # Read from buffers
    music = state["music_buffer"].read(frames) if state["music_buffer"] else np.zeros((frames, CHANNELS), dtype=np.float32)
    tts = state["tts_buffer"].read(frames) if state["tts_buffer"] else np.zeros((frames, CHANNELS), dtype=np.float32)

    # Apply volume to music
    music *= state["volume"]

    # Simple ducking: reduce music volume when TTS is playing
    tts_active = np.any(np.abs(tts) > 0.001)
    if tts_active:
        music *= 0.2  # Duck music to 20% when TTS is playing

    # Mix and apply limiter
    mixed = music + tts
    mixed = np.clip(mixed, -0.95, 0.95)

    outdata[:] = mixed


def start_audio_system():
    """Start the sounddevice audio output system"""
    try:
        # Initialize buffers
        state["music_buffer"] = AudioBuffer()
        state["tts_buffer"] = AudioBuffer()

        # List available devices for debugging
        logger.info("Available audio devices:")
        logger.info(sd.query_devices())

        # Determine which device to use
        device_id = state["audio_device_id"]
        if device_id is not None:
            logger.info(f"Using selected audio device: {device_id}")
        else:
            logger.info("Using default audio device")

        # Start audio stream
        state["audio_stream"] = sd.OutputStream(
            device=device_id,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            callback=audio_callback,
            blocksize=BLOCKSIZE,
            dtype=np.float32
        )
        state["audio_stream"].start()

        device_info = sd.query_devices(device_id if device_id is not None else sd.default.device[1])
        logger.info(f"Audio system started on device: {device_info['name']} (sample_rate={SAMPLE_RATE}, channels={CHANNELS})")
        return True

    except Exception as e:
        logger.error(f"Failed to start audio system: {e}", exc_info=True)
        return False


def stop_audio_system():
    """Stop the audio system"""
    try:
        if state["audio_stream"]:
            state["audio_stream"].stop()
            state["audio_stream"].close()
            state["audio_stream"] = None
        logger.info("Audio system stopped")
    except Exception as e:
        logger.error(f"Error stopping audio system: {e}")


# ============================
# YouTube Playback
# ============================

async def play_youtube(url: str):
    """
    Play YouTube audio by converting to PCM and streaming to music buffer
    """
    if not state["music_buffer"]:
        logger.error("Music buffer not available")
        return False

    try:
        # Start yt-dlp to download audio and pipe to FFmpeg for conversion
        yt_process = await asyncio.create_subprocess_exec(
            "yt-dlp", "-f", "bestaudio", "-o", "-", url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Convert to raw PCM float32
        ffmpeg_process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-i", "pipe:0",
            "-f", "f32le",
            "-ar", str(SAMPLE_RATE),
            "-ac", str(CHANNELS),
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Store processes for skip/shutdown functionality
        state["music_task"] = ffmpeg_process
        state["yt_task"] = yt_process

        # Create task to pipe yt-dlp output to FFmpeg input
        async def pipe_yt_to_ffmpeg():
            try:
                while True:
                    chunk = await yt_process.stdout.read(65536)
                    if not chunk:
                        break
                    ffmpeg_process.stdin.write(chunk)
                    await ffmpeg_process.stdin.drain()
            except (asyncio.CancelledError, BrokenPipeError, ConnectionResetError):
                # Expected when track is skipped
                pass
            except Exception as e:
                logger.error(f"Error piping yt-dlp to FFmpeg: {e}")
            finally:
                try:
                    if ffmpeg_process.stdin and not ffmpeg_process.stdin.is_closing():
                        ffmpeg_process.stdin.close()
                except:
                    pass

        pipe_task = asyncio.create_task(pipe_yt_to_ffmpeg())

        # Stream PCM to music buffer
        while True:
            # Check for skip first (even during pause)
            if state["skip"]:
                state["skip"] = False
                # Cancel pipe task first
                pipe_task.cancel()
                try:
                    await asyncio.wait_for(pipe_task, timeout=0.5)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                # Then terminate processes
                try:
                    ffmpeg_process.terminate()
                    yt_process.terminate()
                except:
                    pass
                # Clear the music buffer
                if state["music_buffer"]:
                    state["music_buffer"].clear()
                logger.info("Track skipped")
                break

            # Check for pause
            while state["paused"] and not state["skip"]:
                await asyncio.sleep(0.1)

            # Backpressure: wait if buffer is too full
            while state["music_buffer"] and state["music_buffer"].available_frames() > SAMPLE_RATE * 2:  # 2 seconds max buffer
                await asyncio.sleep(0.1)

            # Read PCM chunk (4 bytes per sample for float32)
            chunk = await ffmpeg_process.stdout.read(BLOCKSIZE * CHANNELS * 4)

            if not chunk:
                break

            # Convert bytes to numpy array
            audio_data = np.frombuffer(chunk, dtype=np.float32).reshape(-1, CHANNELS)

            # Write to music buffer
            state["music_buffer"].write(audio_data)

        # Wait for pipe task to complete
        try:
            await asyncio.wait_for(pipe_task, timeout=1.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

        # Wait for processes to complete with timeout
        try:
            await asyncio.wait_for(ffmpeg_process.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            ffmpeg_process.kill()

        try:
            await asyncio.wait_for(yt_process.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            yt_process.kill()

        state["music_task"] = None
        state["yt_task"] = None
        return True

    except asyncio.CancelledError:
        # Clean up processes on cancellation
        if state["music_task"]:
            state["music_task"].terminate()
            try:
                await asyncio.wait_for(state["music_task"].wait(), timeout=1.0)
            except asyncio.TimeoutError:
                state["music_task"].kill()

        if state["yt_task"]:
            state["yt_task"].terminate()
            try:
                await asyncio.wait_for(state["yt_task"].wait(), timeout=1.0)
            except asyncio.TimeoutError:
                state["yt_task"].kill()
        raise
    except Exception as e:
        logger.error(f"Playback error: {e}", exc_info=True)
        return False


async def playback_loop():
    """Main playback loop - processes queue"""
    logger.info("Playback loop started")

    while True:
        try:
            # Get next track from queue
            url = await state["queue"].get()
            state["current_track"] = url

            logger.info(f"Now playing: {url}")

            # Play the track
            success = await play_youtube(url)

            if not success:
                logger.warning(f"Failed to play: {url}")

            state["current_track"] = None
            save_queue()

        except asyncio.CancelledError:
            logger.info("Playback loop stopped")
            break
        except Exception as e:
            logger.error(f"Playback loop error: {e}")
            await asyncio.sleep(1)


# ============================
# ElevenLabs TTS
# ============================

async def speak_text(text: str):
    """
    Speak text via ElevenLabs and inject to TTS buffer
    Converts WAV to PCM and streams to tts_buffer
    """
    logger.info(f"speak_text called with: {text[:50]}...")

    if not ELEVENLABS_API_KEY:
        logger.error("ElevenLabs API key not set")
        return False

    if not state["tts_buffer"]:
        logger.error("TTS buffer not available")
        return False

    try:
        # Get TTS audio from ElevenLabs
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
        logger.info(f"Requesting TTS from ElevenLabs API...")

        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        }

        data = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "output_format": "mp3_44100_128",
            "voice_settings": {
                "use_speaker_boost": True,
                "stability": 0.58,
                "similarity_boost": 0.82,
                "speed": 0.84
            }
        }

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.post(url, json=data, headers=headers, stream=True)
        )
        logger.info(f"ElevenLabs response status: {response.status_code}")
        response.raise_for_status()

        # Convert WAV to PCM using FFmpeg
        logger.info("Converting audio to PCM...")
        ffmpeg_process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-i", "pipe:0",
            "-f", "f32le",
            "-ar", str(SAMPLE_RATE),
            "-ac", str(CHANNELS),
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Write WAV data to FFmpeg
        wav_data = response.content
        logger.info(f"Writing {len(wav_data)} bytes of WAV data to FFmpeg")
        ffmpeg_process.stdin.write(wav_data)
        ffmpeg_process.stdin.close()

        # Stream PCM to TTS buffer
        logger.info("Streaming PCM to TTS buffer...")
        total_bytes = 0
        while True:
            chunk = await ffmpeg_process.stdout.read(BLOCKSIZE * CHANNELS * 4)
            if not chunk:
                break

            # Convert bytes to numpy array
            audio_data = np.frombuffer(chunk, dtype=np.float32).reshape(-1, CHANNELS)

            # Write to TTS buffer
            state["tts_buffer"].write(audio_data)
            total_bytes += len(chunk)

        await ffmpeg_process.wait()
        logger.info(f"TTS complete: streamed {total_bytes} bytes")

        logger.info(f"Spoke: {text[:50]}...")
        return True

    except Exception as e:
        logger.error(f"TTS error: {e}", exc_info=True)
        return False


# ============================
# YouTube Helper Functions
# ============================

async def search_youtube(query: str) -> Optional[Dict]:
    """Search YouTube and return video info"""
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'default_search': 'ytsearch',
        }

        loop = asyncio.get_event_loop()

        def _search():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Check if it's a URL or search query
                if "youtube.com" in query or "youtu.be" in query:
                    info = ydl.extract_info(query, download=False)
                else:
                    # Search for the query
                    info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                    if 'entries' in info and info['entries']:
                        info = info['entries'][0]
                    else:
                        return None

                return {
                    'title': info.get('title', 'Unknown'),
                    'url': info.get('webpage_url', ''),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                }

        return await loop.run_in_executor(None, _search)

    except Exception as e:
        logger.error(f"YouTube search error: {e}")
        return None


# ============================
# Discord Commands - Music
# ============================

@bot.tree.command(name="play", description="Play a YouTube video by URL or search query")
@app_commands.describe(query="YouTube URL or search query")
async def play(interaction: discord.Interaction, query: str):
    """Add a YouTube track to the queue"""
    try:
        await interaction.response.defer()

        # Search YouTube to get video info
        video_info = await search_youtube(query)

        if not video_info:
            await interaction.followup.send("❌ Could not find video")
            return

        # Add URL to queue
        await state["queue"].put(video_info['url'])
        save_queue()

        position = state["queue"].qsize()
        duration_min = video_info['duration'] // 60
        duration_sec = video_info['duration'] % 60

        await interaction.followup.send(
            f"✅ Added to queue (position: {position})\n"
            f"🎵 **{video_info['title']}**\n"
            f"👤 {video_info['uploader']} | ⏱️ {duration_min}:{duration_sec:02d}"
        )

    except Exception as e:
        logger.error(f"Play command error: {e}")
        await interaction.followup.send(f"❌ Error: {e}")


@bot.tree.command(name="queue", description="Show the current playlist")
async def show_queue(interaction: discord.Interaction):
    """Show the current playlist"""
    try:
        items = list(state["queue"]._queue)

        if not items and not state["current_track"]:
            await interaction.response.send_message("📭 Queue is empty")
            return

        response = "🎵 **Current Queue**\n\n"

        if state["current_track"]:
            response += f"▶️ Now playing: {state['current_track']}\n\n"

        if items:
            for i, url in enumerate(items, 1):
                response += f"{i}. {url}\n"

        await interaction.response.send_message(response)

    except Exception as e:
        logger.error(f"Queue command error: {e}")
        await interaction.response.send_message(f"❌ Error: {e}")


@bot.tree.command(name="skip", description="Skip the current track")
async def skip(interaction: discord.Interaction):
    """Skip the current track"""
    try:
        if state["current_track"]:
            state["skip"] = True
            await interaction.response.send_message("⏭️ Skipping...")
        else:
            await interaction.response.send_message("❌ Nothing is playing")
    except Exception as e:
        logger.error(f"Skip command error: {e}")
        await interaction.response.send_message(f"❌ Error: {e}")


@bot.tree.command(name="remove", description="Remove a track from the queue")
@app_commands.describe(index="Position of the track in the queue (starting from 1)")
async def remove(interaction: discord.Interaction, index: int):
    """Remove a track from the queue"""
    try:
        items = list(state["queue"]._queue)

        if index < 1 or index > len(items):
            await interaction.response.send_message(f"❌ Invalid index. Queue has {len(items)} items")
            return

        removed = items.pop(index - 1)

        # Rebuild queue
        state["queue"] = asyncio.Queue()
        for item in items:
            await state["queue"].put(item)

        save_queue()
        await interaction.response.send_message(f"🗑️ Removed: {removed}")

    except Exception as e:
        logger.error(f"Remove command error: {e}")
        await interaction.response.send_message(f"❌ Error: {e}")


@bot.tree.command(name="volume", description="Set music volume")
@app_commands.describe(level="Volume level (0-200)")
async def volume(interaction: discord.Interaction, level: int):
    """Set music volume (0-200)"""
    try:
        if level < 0 or level > 200:
            await interaction.response.send_message("❌ Volume must be between 0 and 200")
            return

        state["volume"] = level / 100.0
        await interaction.response.send_message(f"🔊 Volume set to {level}%")

    except Exception as e:
        logger.error(f"Volume command error: {e}")
        await interaction.response.send_message(f"❌ Error: {e}")


@bot.tree.command(name="pause", description="Pause playback")
async def pause(interaction: discord.Interaction):
    """Pause playback"""
    try:
        if state["current_track"]:
            state["paused"] = True
            await interaction.response.send_message("⏸️ Paused")
        else:
            await interaction.response.send_message("❌ Nothing is playing")
    except Exception as e:
        logger.error(f"Pause command error: {e}")
        await interaction.response.send_message(f"❌ Error: {e}")


@bot.tree.command(name="resume", description="Resume playback")
async def resume(interaction: discord.Interaction):
    """Resume playback"""
    try:
        if state["paused"]:
            state["paused"] = False
            await interaction.response.send_message("▶️ Resumed")
        else:
            await interaction.response.send_message("❌ Nothing is paused")
    except Exception as e:
        logger.error(f"Resume command error: {e}")
        await interaction.response.send_message(f"❌ Error: {e}")


# ============================
# Discord Commands - Speech
# ============================

@bot.tree.command(name="say", description="Speak text via ElevenLabs TTS")
@app_commands.describe(text="The text to speak")
async def say(interaction: discord.Interaction, text: str):
    """Speak text via ElevenLabs"""
    try:
        logger.info(f"Say command received: {text[:50]}...")
        await interaction.response.defer()
        logger.info("Response deferred, calling speak_text")

        success = await speak_text(text)
        logger.info(f"speak_text returned: {success}")

        if success:
            await interaction.followup.send(f"🗣️ Speaking: {text[:100]}...")
        else:
            await interaction.followup.send("❌ Failed to speak text")

    except Exception as e:
        logger.error(f"Say command error: {e}", exc_info=True)
        try:
            await interaction.followup.send(f"❌ Error: {e}")
        except Exception as followup_error:
            logger.error(f"Failed to send error message: {followup_error}")


# ============================
# Admin Commands
# ============================

@bot.tree.command(name="restart", description="Restart the bot (admin only)")
async def restart_bot(interaction: discord.Interaction):
    """Restart the bot - only authorized users can use this"""
    try:
        # Check if user is authorized
        if interaction.user.name != AUTHORIZED_USER:
            await interaction.response.send_message("❌ You are not authorized to restart the bot", ephemeral=True)
            logger.warning(f"Unauthorized restart attempt by {interaction.user.name}")
            return

        await interaction.response.send_message("�� Restarting bot...", ephemeral=True)
        logger.info(f"Bot restart initiated by {interaction.user.name}")

        # Trigger shutdown which will cause the bot to exit
        # If running with a process manager (systemd, pm2, etc), it will restart automatically
        asyncio.create_task(shutdown())

    except Exception as e:
        logger.error(f"Restart command error: {e}", exc_info=True)
        try:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
        except:
            pass


@bot.tree.command(name="devices", description="List available audio devices (admin only)")
async def list_devices(interaction: discord.Interaction):
    """List all available audio output devices"""
    try:
        # Check if user is authorized
        if interaction.user.name != AUTHORIZED_USER:
            await interaction.response.send_message("❌ You are not authorized to view devices", ephemeral=True)
            return

        devices = sd.query_devices()
        output_devices = []

        for i, device in enumerate(devices):
            if isinstance(device, dict):
                # Check if device has output channels
                if device.get('max_output_channels', 0) > 0:
                    name = device.get('name', 'Unknown')
                    channels = device.get('max_output_channels', 0)
                    current = "**[CURRENT]**" if i == state["audio_device_id"] else ""
                    default = "**[DEFAULT]**" if i == sd.default.device[1] else ""
                    output_devices.append(f"`{i}` - {name} ({channels}ch) {current} {default}")

        if not output_devices:
            await interaction.response.send_message("❌ No output devices found", ephemeral=True)
            return

        response = "🔊 **Available Audio Output Devices:**\n\n" + "\n".join(output_devices)
        response += "\n\nUse `/setdevice <id>` to change the audio device"

        await interaction.response.send_message(response, ephemeral=True)

    except Exception as e:
        logger.error(f"Devices command error: {e}", exc_info=True)
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


@bot.tree.command(name="setdevice", description="Set audio output device (admin only)")
@app_commands.describe(device_id="Device ID from /devices command")
async def set_device(interaction: discord.Interaction, device_id: int):
    """Set the audio output device"""
    try:
        # Check if user is authorized
        if interaction.user.name != AUTHORIZED_USER:
            await interaction.response.send_message("❌ You are not authorized to change devices", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Validate device ID
        devices = sd.query_devices()
        if device_id < 0 or device_id >= len(devices):
            await interaction.followup.send(f"❌ Invalid device ID. Use `/devices` to see available devices", ephemeral=True)
            return

        device_info = devices[device_id]
        if device_info.get('max_output_channels', 0) <= 0:
            await interaction.followup.send(f"❌ Device {device_id} has no output channels", ephemeral=True)
            return

        # Stop current audio stream
        stop_audio_system()

        # Set new device
        state["audio_device_id"] = device_id
        logger.info(f"Audio device changed to {device_id} by {interaction.user.name}")

        # Save to selected_device.json
        device_config = {"device_id": device_id, "device_name": device_info.get('name', 'Unknown')}
        with open("selected_device.json", "w") as f:
            json.dump(device_config, f, indent=2)
        logger.info(f"Saved device {device_id} to selected_device.json")

        # Restart audio stream
        if not start_audio_system():
            await interaction.followup.send(f"❌ Failed to start audio on device {device_id}", ephemeral=True)
            return

        device_name = device_info.get('name', 'Unknown')
        await interaction.followup.send(f"✅ Audio device changed to: **{device_name}** (ID: {device_id})", ephemeral=True)

    except Exception as e:
        logger.error(f"Set device command error: {e}", exc_info=True)
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


# ============================
# Bot Events
# ============================

@bot.event
async def on_ready():
    """Bot startup"""
    logger.info(f"Logged in as {bot.user}")

    # Load saved audio device
    device_config_path = Path("selected_device.json")
    if device_config_path.exists():
        try:
            with open(device_config_path, 'r') as f:
                device_config = json.load(f)
                state["audio_device_id"] = device_config.get("device_id")
                logger.info(f"Loaded audio device {state['audio_device_id']} from selected_device.json")
        except Exception as e:
            logger.warning(f"Failed to load selected_device.json: {e}")

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} slash commands")
        logger.info(f"Commands: {', '.join([cmd.name for cmd in synced])}")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")

    # Start audio system
    if not start_audio_system():
        logger.error("Failed to start audio system - bot cannot function")
        await bot.close()
        return

    # Load saved queue
    saved_items = load_queue()
    for item in saved_items:
        await state["queue"].put(item)
    logger.info(f"Loaded {len(saved_items)} items from saved queue")

    # Start playback loop
    state["playback_task"] = asyncio.create_task(playback_loop())

    logger.info("Bot is ready!")


@bot.event
async def on_command_error(ctx, error):
    """Handle command errors"""
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: {error.param.name}")
    else:
        logger.error(f"Command error: {error}")
        await ctx.send(f"❌ An error occurred: {error}")


# ============================
# Shutdown Handler
# ============================

async def shutdown():
    """Graceful shutdown"""
    logger.info("Shutting down...")

    # Stop playback
    if state["playback_task"]:
        state["playback_task"].cancel()
        try:
            await asyncio.wait_for(state["playback_task"], timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    # Stop yt-dlp process
    if state["yt_task"]:
        state["yt_task"].terminate()
        try:
            await asyncio.wait_for(state["yt_task"].wait(), timeout=1.0)
        except asyncio.TimeoutError:
            state["yt_task"].kill()

    # Stop current track (FFmpeg)
    if state["music_task"]:
        state["music_task"].terminate()
        try:
            await asyncio.wait_for(state["music_task"].wait(), timeout=1.0)
        except asyncio.TimeoutError:
            state["music_task"].kill()

    # Stop audio system
    stop_audio_system()

    # Save queue
    save_queue()

    # Close bot
    await bot.close()

    logger.info("Shutdown complete")


# ============================
# Main
# ============================

def main():
    """Main entry point"""
    # Validate configuration
    if not DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN environment variable not set")
        sys.exit(1)

    if not ELEVENLABS_API_KEY:
        logger.warning("ELEVENLABS_API_KEY not set - TTS will be disabled")

    # Setup signal handlers (Unix only - Windows doesn't support add_signal_handler)
    if sys.platform != 'win32':
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        def signal_handler():
            asyncio.create_task(shutdown())

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)
    else:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        # Run bot
        bot.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        if not loop.is_closed():
            loop.run_until_complete(shutdown())
            loop.close()


if __name__ == "__main__":
    main()
