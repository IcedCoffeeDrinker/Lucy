'''
This test was written by AI
'''
import httpx
import base64
import wave
import numpy as np
import time
import os
import threading # Kept for recorder, can be simplified further if needed

# Basic Configuration
FASTAPI_BASE_URL = "http://localhost:5001"
TEST_USER_ID = "01JVT4A67BNZX7BJXKFVWKKHPM" # Keep your specific User ID
OUTPUT_RECORDING_FILENAME = "twilio_test_recording.wav"
SAMPLE_RATE = 8000  # Hz (Twilio standard for PSTN/voice)
AUDIO_CHUNK_DURATION_MS = 20  # ms (standard for Twilio media stream)
FRAMES_PER_CHUNK = int(SAMPLE_RATE * (AUDIO_CHUNK_DURATION_MS / 1000.0))

# Ensure output directory exists
output_dir = os.path.dirname(OUTPUT_RECORDING_FILENAME)
if output_dir and not os.path.exists(output_dir):
    os.makedirs(output_dir)

stop_recording_event = threading.Event()

def place_call(user_id: str):
    url = f"{FASTAPI_BASE_URL}/twilio_api/place_call/{user_id}"
    print(f"Placing call for {user_id} via {url}...")
    try:
        # Increased timeout for ngrok setup within the endpoint
        response = httpx.post(url, timeout=45.0) 
        response.raise_for_status()
        call_data = response.json()
        print(f"Call placed successfully: SID {call_data.get('call_sid')}, Ngrok URL: {call_data.get('ngrok_public_url')}")
        return call_data
    except Exception as e:
        print(f"Error placing call: {e}")
    return None

def generate_pcm_sound(frequency: float, duration_ms: int, sample_rate: int):
    """Generates PCM data for a sound (e.g., sine wave)."""
    num_frames = int(sample_rate * (duration_ms / 1000.0))
    t = np.linspace(0, duration_ms / 1000.0, num_frames, endpoint=False)
    wave_data = np.sin(2 * np.pi * frequency * t)
    # Scale to 16-bit integer range
    audio_data = (wave_data * 32767).astype(np.int16)
    return audio_data.tobytes()

def inject_audio_chunk(user_id: str, pcm_data: bytes):
    """Injects a single chunk of PCM audio data into the call."""
    inject_url = f"{FASTAPI_BASE_URL}/twilio_api/inject/{user_id}"
    payload_b64 = base64.b64encode(pcm_data).decode('utf-8')
    try:
        response = httpx.post(inject_url, json={"payload_b64": payload_b64}, timeout=5.0)
        if response.status_code == 200:
            print(f"Successfully injected {len(pcm_data)} bytes for user {user_id}.")
        else:
            print(f"Error injecting audio for {user_id}: {response.status_code} - {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"Exception injecting audio for {user_id}: {e}")
    return False

def record_audio_from_call(user_id: str, output_filename: str, duration_seconds: int):
    """Records audio received from the call for a specified duration."""
    audio_stream_url = f"{FASTAPI_BASE_URL}/twilio_api/audio_stream/{user_id}"
    print(f"Starting to record audio from {audio_stream_url} to {output_filename} for {duration_seconds}s...")
    
    with wave.open(output_filename, 'wb') as wf:
        wf.setnchannels(1)       # Mono
        wf.setsampwidth(2)       # 16-bit
        wf.setframerate(SAMPLE_RATE)
        
        start_time = time.time()
        try:
            with httpx.stream("GET", audio_stream_url, timeout=15.0) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes(chunk_size=FRAMES_PER_CHUNK * 2): # Read enough for a bit
                    if stop_recording_event.is_set() or (time.time() - start_time) > duration_seconds:
                        break
                    wf.writeframes(chunk)
        except Exception as e:
            print(f"Error during audio recording for {user_id}: {e}")
        finally:
            print(f"Finished recording audio. Output saved to {output_filename}")
            stop_recording_event.set() # Ensure main thread knows recording is done

def main():
    print("--- Minimal Twilio Call Test ---")
    call_info = place_call(TEST_USER_ID)

    if not call_info:
        print("Failed to place call. Exiting test.")
        return

    print("Call initiated by test script. Waiting for call to connect (approx 10-15 seconds for ngrok and Twilio setup)...")
    # This sleep is crucial to allow ngrok to start, Twilio to make the TwiML request, 
    # and the WebSocket to establish for media streaming.
    time.sleep(15) 

    # --- Start Recording Thread ---
    # We'll record for a total of ~20 seconds to capture a bit of everything.
    recording_duration = 20 
    recorder_thread = threading.Thread(
        target=record_audio_from_call, 
        args=(TEST_USER_ID, OUTPUT_RECORDING_FILENAME, recording_duration)
    )
    print("Starting audio recording thread...")
    recorder_thread.start()
    time.sleep(1) # Give recorder a moment to start fetching the stream

    # --- Test 1: Stream a continuous sound TO the call for a few seconds ---
    print("\n--- Test 1: Streaming continuous sound TO the call ---")
    stream_duration_seconds = 5
    num_chunks_to_stream = int((stream_duration_seconds * 1000) / AUDIO_CHUNK_DURATION_MS)
    for i in range(num_chunks_to_stream):
        if stop_recording_event.is_set(): # Stop if recording ended early
            break
        # Generate a 440Hz (A4 note) sine wave chunk
        pcm_chunk = generate_pcm_sound(frequency=440, duration_ms=AUDIO_CHUNK_DURATION_MS, sample_rate=SAMPLE_RATE)
        inject_audio_chunk(TEST_USER_ID, pcm_chunk)
        time.sleep(AUDIO_CHUNK_DURATION_MS / 1000.0) # Pace the streaming
    print("Finished streaming continuous sound.")

    time.sleep(2) # Pause between tests

    # --- Test 2: Inject a distinct, short sound TO the call (testing send_audio again) ---
    print("\n--- Test 2: Injecting a distinct short sound TO the call ---")
    # Generate a short, different frequency sound (e.g., 880Hz, 0.5 seconds)
    distinct_sound_pcm = generate_pcm_sound(frequency=880, duration_ms=500, sample_rate=SAMPLE_RATE)
    # Send it in one go (or could break into chunks if very long, but 0.5s is fine)
    # For Twilio media stream, it's best to send in 20ms chunks anyway.
    num_distinct_chunks = len(distinct_sound_pcm) // (FRAMES_PER_CHUNK * 2) # Assuming 16-bit so 2 bytes/frame
    if num_distinct_chunks == 0 and len(distinct_sound_pcm) > 0 : num_distinct_chunks = 1
    
    for i in range(num_distinct_chunks):
        start_byte = i * FRAMES_PER_CHUNK * 2
        end_byte = (i + 1) * FRAMES_PER_CHUNK * 2
        chunk_to_send = distinct_sound_pcm[start_byte:end_byte]
        if not chunk_to_send: break # Should not happen if logic is right
        inject_audio_chunk(TEST_USER_ID, chunk_to_send)
        time.sleep(AUDIO_CHUNK_DURATION_MS / 1000.0)
    print("Finished injecting distinct sound.")

    # --- Wait for recording to finish ---
    print("\nWaiting for recording thread to complete...")
    recorder_thread.join(timeout=recording_duration + 5) # Wait a bit longer than expected duration

    if recorder_thread.is_alive():
        print("Warning: Recording thread did not complete in time.")
        stop_recording_event.set() # Force it to stop if still running
        recorder_thread.join(timeout=5)

    print("--- Minimal Twilio Call Test Finished ---")
    print(f"Check '{OUTPUT_RECORDING_FILENAME}' for the audio.")
    print("You should hear the continuous sound, then the distinct short sound, and any audio you spoke.")

if __name__ == "__main__":
    main() 