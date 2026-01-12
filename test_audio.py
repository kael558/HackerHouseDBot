#!/usr/bin/env python3
"""
Test audio output on your Raspberry Pi.
This script plays a test tone to verify audio is working.

Usage:
    python test_audio.py [device_id]

Examples:
    python test_audio.py        # Use device from selected_device.json or default
    python test_audio.py 5      # Use device 5
"""

import sys
import json
from pathlib import Path
import numpy as np
import sounddevice as sd

def play_test_tone(device=None, duration=2.0, frequency=440.0, sample_rate=44100):
    """
    Play a test tone (A4 = 440 Hz) for the specified duration.

    Args:
        device: Device ID or None for default
        duration: Duration in seconds
        frequency: Frequency in Hz
        sample_rate: Sample rate in Hz
    """
    print(f"\n{'='*60}")
    print("AUDIO OUTPUT TEST")
    print(f"{'='*60}")

    # Generate sine wave
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    tone = np.sin(frequency * 2 * np.pi * t)

    # Create stereo signal
    stereo_tone = np.column_stack([tone, tone])

    # Apply fade in/out to avoid clicks
    fade_samples = int(0.01 * sample_rate)  # 10ms fade
    fade_in = np.linspace(0, 1, fade_samples)
    fade_out = np.linspace(1, 0, fade_samples)
    stereo_tone[:fade_samples] *= fade_in[:, np.newaxis]
    stereo_tone[-fade_samples:] *= fade_out[:, np.newaxis]

    # Print device info
    if device is not None:
        device_info = sd.query_devices(device)
        print(f"\nUsing device: {device} - {device_info['name']}")
    else:
        default_device = sd.default.device[1]
        device_info = sd.query_devices(default_device)
        print(f"\nUsing default device: {default_device} - {device_info['name']}")

    print(f"Sample rate: {sample_rate} Hz")
    print(f"Channels: 2 (stereo)")
    print(f"Duration: {duration} seconds")
    print(f"Frequency: {frequency} Hz (A4)")
    print(f"\n{'='*60}")

    try:
        print("\n🔊 Playing test tone...")
        sd.play(stereo_tone, sample_rate, device=device)
        sd.wait()
        print("✓ Test tone completed successfully!")
        print("\nIf you heard the tone, audio is working correctly.")
        print("If not, try a different device ID or check your audio settings.")
        return True

    except Exception as e:
        print(f"\n✗ Error playing audio: {e}")
        print("\nTroubleshooting:")
        print("1. Check if device is available: python list_audio_devices.py")
        print("2. Verify Bluetooth connection: speaker-test -t wav")
        print("3. Check permissions: groups | grep audio")
        print("4. Install dependencies: sudo apt-get install libportaudio2")
        return False

def main():
    """Main function"""
    device = None

    # Parse command line arguments
    if len(sys.argv) > 1:
        try:
            device = int(sys.argv[1])
        except ValueError:
            print(f"Error: Device ID must be an integer")
            print(f"Usage: python test_audio.py [device_id]")
            print(f"\nRun 'python list_audio_devices.py' to see available devices")
            sys.exit(1)
    else:
        # Try to load device from selected_device.json
        device_config_path = Path("selected_device.json")
        if device_config_path.exists():
            try:
                with open(device_config_path, 'r') as f:
                    device_config = json.load(f)
                    device = device_config.get("device_id")
                    device_name = device_config.get("device_name", "Unknown")
                    if device is not None:
                        print(f"📋 Using device from selected_device.json: {device} - {device_name}")
            except Exception as e:
                print(f"⚠️  Failed to load selected_device.json: {e}")
                print("Using default device instead...")

    # Test with 44100 Hz
    print("\n🧪 Testing with 44100 Hz sample rate...")
    success_44k = play_test_tone(device=device, sample_rate=44100)

    # Test with 48000 Hz if Bluetooth
    if device is not None or input("\n\nTest with 48000 Hz as well? (y/n): ").lower() == 'y':
        print("\n🧪 Testing with 48000 Hz sample rate...")
        print("(This often works better with Bluetooth speakers)")
        success_48k = play_test_tone(device=device, sample_rate=48000)

        if success_48k and not success_44k:
            print("\n💡 TIP: 48000 Hz worked but 44100 Hz didn't!")
            print("Add this to your .env file:")
            print("AUDIO_SAMPLE_RATE=48000")

    print(f"\n{'='*60}")
    print("Test complete!")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
