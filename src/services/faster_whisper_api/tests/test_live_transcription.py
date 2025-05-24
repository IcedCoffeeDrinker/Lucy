import asyncio
import websockets
# import numpy as np # No longer needed for WAV file streaming
# import math # No longer needed
import struct
import json
import wave # For reading WAV files
import os # For constructing dynamic paths

# --- Audio Configuration ---
# SAMPLE_RATE = 16000  # Hz # This will be read from the WAV file
# DURATION = 2  # seconds # This will be determined by the WAV file length
CHUNK_DURATION_SECONDS = 0.03  # How much audio (in seconds) to send per chunk (e.g., 30ms)

# !!! WAV file is assumed to be in the SAME DIRECTORY as this script !!!
YOUR_WAV_FILENAME = "test_input_16khz.wav" # Use the resampled 16kHz file
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
YOUR_WAV_FILE_PATH = os.path.join(SCRIPT_DIR, YOUR_WAV_FILENAME)

WEBSOCKET_URL = "ws://localhost:8000/v1/audio/transcriptions"

async def receive_transcriptions(websocket):
    """Receives and prints transcriptions from the server."""
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                if "text" in data:
                    print(f"Received: {data['text']}")
                elif "segments" in data and data["segments"]:
                    full_text = " ".join([segment.get('text', '') for segment in data["segments"]])
                    print(f"Received (segments): {full_text.strip()}")
                else:
                    print(f"Received (raw): {data}")
            except json.JSONDecodeError:
                print(f"Received (non-JSON): {message}")
    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed: {e}")
    except Exception as e:
        print(f"Error receiving transcription: {e}")

async def send_audio_from_wav(websocket, wav_path):
    """Reads a WAV file and streams its audio data in chunks."""
    try:
        with wave.open(wav_path, 'rb') as wf:
            sample_rate = wf.getframerate()
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth() # Bytes per sample (e.g., 2 for 16-bit)
            
            print(f"Streaming audio from: {wav_path}")
            print(f"  - Sample Rate: {sample_rate} Hz")
            print(f"  - Channels: {channels}")
            print(f"  - Sample Width: {sampwidth*8}-bit PCM")

            if sample_rate != 16000:
                print(f"WARNING: Audio sample rate is {sample_rate} Hz. Server expects 16000 Hz.")
            if channels != 1:
                print(f"WARNING: Audio is {channels}-channel. Server expects mono (1-channel).")
            if sampwidth != 2:
                print(f"WARNING: Audio sample width is {sampwidth*8}-bit. Server expects 16-bit.")

            # Calculate chunk size in frames based on CHUNK_DURATION_SECONDS
            chunk_size_frames = int(sample_rate * CHUNK_DURATION_SECONDS)
            if chunk_size_frames == 0:
                print("ERROR: CHUNK_DURATION_SECONDS is too small for the sample rate, resulting in zero frames per chunk.")
                return

            while True:
                frames = wf.readframes(chunk_size_frames) # Read audio frames
                if not frames:
                    print("Finished sending audio from WAV file.")
                    break
                await websocket.send(frames) # Send raw bytes
                # print(f"Sent chunk of {len(frames)} bytes.") # Optional: for debugging
                await asyncio.sleep(CHUNK_DURATION_SECONDS) # Simulate real-time stream by sleeping for chunk duration
                
    except FileNotFoundError:
        print(f"ERROR: WAV file not found at {wav_path}")
    except wave.Error as e:
        print(f"ERROR: Could not read WAV file ({wav_path}): {e}. Ensure it's a valid WAV.")
    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed while sending WAV: {e}")
    except Exception as e:
        print(f"Error sending audio from WAV: {e}")

async def live_transcribe_test():
    print(f"Connecting to {WEBSOCKET_URL}...")
    try:
        async with websockets.connect(WEBSOCKET_URL, open_timeout=20) as websocket:
            print("Connected to faster-whisper-server.")
            
            receive_task = asyncio.create_task(receive_transcriptions(websocket))
            send_task = asyncio.create_task(send_audio_from_wav(websocket, YOUR_WAV_FILE_PATH))
            
            await asyncio.gather(send_task, receive_task)
            
    except websockets.exceptions.InvalidURI:
        print(f"Error: Invalid WebSocket URI: {WEBSOCKET_URL}")
    except ConnectionRefusedError:
        print(f"Error: Connection refused. Is the faster-whisper-server running at {WEBSOCKET_URL}?")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    print("Starting live transcription test from WAV file...")
    print(f"Attempting to stream: {YOUR_WAV_FILE_PATH}")
    print("Make sure the faster-whisper-server is running and accessible.")
    print("You should see audio being streamed and transcriptions (if any) printed below.")
    asyncio.run(live_transcribe_test())