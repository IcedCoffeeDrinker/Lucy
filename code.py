❯ cat make_call2.py 
#!/usr/bin/env python3
"""
make_call.py – Twilio ↔ Vosk ↔ Ollama ↔ CSM‑1B
==============================================

* Inbound 8 kHz media stream from Twilio.
* Vosk transcribes; every 2 s we pass the last 20 words to an Ollama LLM
  (`OLLAMA_MODEL`, default *llama3:8b*).
* If Ollama returns `{"speak": true, "response": "…"}` we synthesise with
  CSM‑1B and stream the audio back.

Synchronous, CPU‑only, with robust Twilio credential checks and correct
indentation.
"""

###############################################################################
#  ENV & IMPORTS                                                              #
###############################################################################
import os, sys, json, base64, time, re
from collections import deque
import numpy as np, audioop, vosk
import torch  # Added for device check
from flask import Flask, request
from flask_sock import Sock
from twilio.twiml.voice_response import VoiceResponse, Start
from twilio.rest import Client
from dotenv import load_dotenv
from generator import load_csm_1b
from ollama import chat

# ── torch safety knobs ──────────────────────────────────────────────────────
# Removed lines forcing CPU:
# os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
# os.environ.setdefault("TORCH_DISABLE_CUDA", "1")
# os.environ.setdefault("NO_TORCH_COMPILE", "1")

###############################################################################
#  CONFIG                                                                     #
###############################################################################
load_dotenv()
TWILIO_SID               = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN             = os.getenv("TWILIO_AUTH_TOKEN") or os.getenv("TWILIO_ACCESS_TOKEN")
TWILIO_FROM              = os.getenv("TWILIO_PHONE_NUMBER")
CALL_TO                  = os.getenv("PERSONAL_PHONE_NUMBER")
NGROK_AUTH               = os.getenv("NGROK_AUTH")
OLLAMA_DECISION_MODEL    = os.getenv("OLLAMA_DECISION_MODEL", "llama3.2:1b") # Changed default from 3.1
OLLAMA_CONVERSATIONAL_MODEL = os.getenv("OLLAMA_CONVERSATIONAL_MODEL", "llama3:8b") # New: Model for response generation
CHECK_EVERY              = 0.75   # seconds - Reduced for lower latency
MAX_CALL_MIN             = 5

if not all([TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM, CALL_TO]):
    sys.exit("✖  Missing Twilio environment variables. Check .env file.")

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"[config] Using device: {DEVICE}")
GENERATOR = load_csm_1b(device=DEVICE) # Pass determined device
GEN_SR    = GENERATOR.sample_rate
VOSK_MODEL = vosk.Model("csm/vosk_model")  # 8 kHz model folder

FRAME_MS  = 20
DST_RATE  = 8000
SAMPLES   = DST_RATE * FRAME_MS // 1000
MU        = 255

###############################################################################
#  HELPERS                                                                    #
###############################################################################

def ulaw2pcm16(b: bytes) -> bytes:
    return audioop.ulaw2lin(b, 2)

def pcm16_to_ulaw_bytes(pcm16: np.ndarray) -> bytes:
    x = pcm16.astype(np.float32) / 32768.0
    mag = np.log1p(MU * np.abs(x)) / np.log1p(MU)
    ul  = np.sign(x) * mag
    return (((ul + 1) / 2 * MU).astype(np.uint8) ^ 0xFF).tobytes()

def resample(pcm: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst:
        return pcm
    dst_len = int(len(pcm) * dst / src)
    idx = np.linspace(0, len(pcm) - 1, num=dst_len)
    return np.interp(idx, np.arange(len(pcm)), pcm).astype(np.float32)

# New Helper: Robust Ollama JSON extraction
def ask_ollama(model_name: str, prompt: str) -> dict | None:
    """Calls Ollama, attempts to extract JSON from response."""
    try:
        res = chat(model=model_name, messages=[{"role": "user", "content": prompt}])
        content = res["message"]["content"]
        # Try to find JSON object using regex, even if surrounded by text/markdown
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            # Strip whitespace before parsing
            json_str = match.group(0).strip()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as json_e:
                print(f"\n[ollama] JSON decode error: {json_e}", file=sys.stderr)
                print(f"[ollama] Raw content was: {content}", file=sys.stderr)
                # Add the attempted parsed string for debugging
                print(f"[ollama] Attempted to parse: >>{json_str}<<", file=sys.stderr)
                return None
        else:
            print(f"\n[ollama] No JSON object found in response.", file=sys.stderr)
            print(f"[ollama] Raw content was: {content}", file=sys.stderr)
            return None
    except Exception as e:
        print(f"\n[ollama] API call error: {e}", file=sys.stderr)
        return None

###############################################################################
#  TTS STREAMER                                                               #
###############################################################################

def stream_tts(ws, sid: str, text: str, seq: int) -> int:
    import torch
    with torch.inference_mode():
        audio = GENERATOR.generate(text=text, speaker=0, context=[], max_audio_length_ms=10000)
    pcm = audio.squeeze().cpu().numpy()
    pcm8 = resample(pcm, GEN_SR, DST_RATE)
    pcm16 = np.clip(pcm8 * 32767, -32768, 32767).astype(np.int16)
    for idx, off in enumerate(range(0, len(pcm16) - SAMPLES + 1, SAMPLES)):
        payload = base64.b64encode(pcm16_to_ulaw_bytes(pcm16[off:off + SAMPLES])).decode()
        ws.send(json.dumps({
            "event": "media", "streamSid": sid,
            "sequenceNumber": str(seq + idx),
            "media": {"track": "outbound", "chunk": str(seq + idx),
                      "timestamp": str(FRAME_MS * (seq + idx - 1)),
                      "payload": payload},
        }))
    final = seq + idx + 1
    ws.send(json.dumps({"event": "mark", "streamSid": sid,
                        "sequenceNumber": str(final), "mark": {"name": "csm-done"}}))
    return final

###############################################################################
#  FLASK APP                                                                  #
###############################################################################
app = Flask(__name__)
sock = Sock(app)
client = Client(TWILIO_SID, TWILIO_TOKEN)
CL, BS = "\x1b[0K", "\x08"

@sock.route("/stream")
def stream(ws):
    rec = vosk.KaldiRecognizer(VOSK_MODEL, 8000)
    words = deque(maxlen=100)  # Store recent words
    last_check = time.time()
    seq = 1; sid = None
    CL, BS = "\x1b[0K", "\x08" # ANSI escape codes for clearing line/backspace

    while True:
        raw = ws.receive()
        if raw is None:
            print("\n[stream] WebSocket closed.")
            break
        pkt = json.loads(raw)
        evt = pkt.get("event")

        if evt == "start":
            sid = pkt["streamSid"]
            print(f"\n[stream] Started stream {sid}")
            continue
        if evt == "stop":
            print(f"\n[stream] Stopped stream {sid}")
            break
        if evt != "media":
            continue # Ignore non-media messages for now

        # Process incoming audio
        pcm_bytes = ulaw2pcm16(base64.b64decode(pkt["media"]["payload"]))
        if rec.AcceptWaveform(pcm_bytes):
            result = json.loads(rec.Result())
            txt = result["text"].strip()
            if txt:
                print(CL + txt + " ", end="", flush=True)
                words.extend(txt.split())
        else:
            partial_result = json.loads(rec.PartialResult())
            part = partial_result.get("partial", "").strip()
            # Only print partial if non-empty to avoid flickering
            if part:
                 # Print partial, overwrite with backspaces
                print(CL + part + BS * len(part), end="", flush=True)
                # Don't add partial results to the main word buffer
                # to avoid duplicate processing on final result
                # words.extend(part.split()) # <-- Removed this

        # ---- Ask Ollama periodically ----
        current_time = time.time()
        if current_time - last_check >= CHECK_EVERY and words:
            last_check = current_time # Reset timer immediately
            snippet_text = " ".join(list(words)[-30:]) # Use last 30 words for context

            # 1. Ask the Decision Model if we should speak
            decision_prompt = (
                "You are an AI assistant deciding *only* whether to speak right now or wait for the user to continue. "
                "Consider the last 30 words spoken by the caller. Respond ONLY with JSON: "
                '{\\"speak\\": true} or {\\"speak\\": false}. '
                "Do not add any other text or explanation.\\n"
                f'Caller words: \\"{snippet_text}\\"'
            )
            decision_result = ask_ollama(OLLAMA_DECISION_MODEL, decision_prompt)

            if decision_result and decision_result.get("speak") is True:
                print(f"\n[ollama-decision] Decided to speak based on: '{snippet_text}'")

                # 2. Ask the Conversational Model what to say
                #    (Could potentially use more history from `words` here if needed)
                conversation_prompt = (
                   "You are Lucy, an emotional AI assistant. Briefly respond to the user's last statement. "
                   "Be concise and natural. Respond ONLY with JSON containing the response text: "
                   '{\\"response\\": \\"Your response here.\\"}. '
                   "Do not add any other text or explanation.\\n"
                   f'User said: \\"{snippet_text}\\"'
                )
                conversation_result = ask_ollama(OLLAMA_CONVERSATIONAL_MODEL, conversation_prompt)

                if conversation_result and isinstance(conversation_result.get("response"), str):
                    response_text = conversation_result["response"].strip()
                    if response_text:
                        print(f"\n[ollama-convo] Generating speech for: '{response_text}'")
                        seq = stream_tts(ws, sid, response_text, seq)
                        words.clear() # Clear buffer after responding
                        # Reset timer again after speaking to avoid immediate re-trigger
                        last_check = time.time()
                    else:
                         print("\n[ollama-convo] Warning: Received empty response string.", file=sys.stderr)

                elif conversation_result:
                    print(f"\n[ollama-convo] Error: Unexpected format from conversational model: {conversation_result}", file=sys.stderr)
                # If conversation_result is None, ask_ollama already printed an error

            elif decision_result and decision_result.get("speak") is False:
                # Optional: Log that we decided not to speak
                # print(f"\n[ollama-decision] Decided not to speak for '{snippet_text}'")
                pass # Do nothing if speak is false

            # If decision_result is None, ask_ollama already printed an error

###############################################################################
#  TWILIO ROUTES & ENTRYPOINT                                                 #
###############################################################################
@app.route("/call", methods=["POST"])
def call():
    vr = VoiceResponse(); st = Start(); st.stream(url=f"wss://{request.host}/stream"); vr.append(st)
    vr.pause(length=int(60 * MAX_CALL_MIN))
    client.calls.create(to=CALL_TO, from_=TWILIO_FROM, twiml=vr)
    return str(vr), 200, {"Content-Type": "text/xml"}

if __name__ == "__main__":
    PORT = 5001
    # Import the specific exception class
    from pyngrok import ngrok
    from pyngrok.exception import PyngrokNgrokError 

    if not NGROK_AUTH:
        sys.exit("✖  NGROK_AUTH not set in .env")
    ngrok.set_auth_token(NGROK_AUTH)

    public_url = None # Initialize public_url
    try:
        # --- Connect ngrok --- 
        print("[ngrok] Connecting...")
        # Adding region preference if helpful, e.g., region="eu"
        # Consider adding a try-except specifically around connect if needed
        public_url = ngrok.connect(PORT, bind_tls=True).public_url # Use http.public_url if connect returns Tunnel object
        print(f"[ngrok] Public URL: {public_url}")

        # --- Update Twilio Webhook --- 
        try:
            print("[twilio] Updating voice URL...")
            # Find the first available number and update it
            # Note: This assumes you want to update the *first* number found.
            # You might want more specific logic if you have multiple numbers.
            phone_numbers = client.incoming_phone_numbers.list(limit=1)
            if phone_numbers:
                phone_numbers[0].update(voice_url=f"{public_url}/call")
                print(f"[twilio] Set voice URL for {phone_numbers[0].phone_number} to {public_url}/call")
            else:
                 print("[twilio] Warning: No incoming phone numbers found to update.", file=sys.stderr)
        except Exception as e:
            # Use traceback for more detailed error reporting
            import traceback
            print(f"✖  Twilio API interaction failed:", file=sys.stderr)
            traceback.print_exc()
            # Decide if we should exit or try to continue without webhook update
            # For now, let's exit as the call logic depends on it.
            sys.exit(1)

        # --- Make the Outbound Call --- 
        wss_url = public_url.replace("https://", "wss://") + "/stream"
        twiml_response = VoiceResponse()
        start = Start()
        start.stream(url=wss_url)
        twiml_response.append(start)
        twiml_response.pause(length=int(60 * MAX_CALL_MIN))
        
        try:
            print(f"[twilio] Creating outbound call to {CALL_TO} from {TWILIO_FROM}...")
            call = client.calls.create(to=CALL_TO, from_=TWILIO_FROM, twiml=str(twiml_response))
            print(f"[twilio] Outbound call SID: {call.sid}")
        except Exception as e:
            import traceback
            print(f"[twilio] Outbound call failed:", file=sys.stderr)
            traceback.print_exc()
            # Allow server to run even if outbound call fails, 
            # maybe an inbound call will trigger it.

        # --- Run Flask App --- 
        print(f"[flask] Starting server on port {PORT}...")
        app.run(host="0.0.0.0", port=PORT)

    # Catch the specific PyngrokNgrokError
    except PyngrokNgrokError as ngrok_err:
        print(f"✖  Ngrok connection failed: {ngrok_err}", file=sys.stderr)
        # Specifically check for the common session limit error
        if "ERR_NGROK_108" in str(ngrok_err):
            print("\n[fix] This often means another ngrok tunnel is running on your account.", file=sys.stderr)
            print("[fix] Please check for other running scripts or ngrok instances", file=sys.stderr)
            print("[fix] You can view/manage sessions at: https://dashboard.ngrok.com/tunnels/agents", file=sys.stderr)
        sys.exit(1) # Exit if ngrok fails to connect

    except Exception as e:
        import traceback
        print(f"✖  An unexpected error occurred in main block:", file=sys.stderr)
        traceback.print_exc()

    finally:
        # --- Cleanup --- 
        print("\n[cleanup] Shutting down...")
        if public_url:
            try:
                print(f"[ngrok] Disconnecting tunnel: {public_url}")
                ngrok.disconnect(public_url)
            except Exception as e:
                print(f"[ngrok] Error during disconnect: {e}", file=sys.stderr)
        try:
            print("[ngrok] Killing ngrok process...")
            ngrok.kill()
            print("[ngrok] Process killed.")
        except Exception as e:
            print(f"[ngrok] Error during kill: {e}", file=sys.stderr)
        print("[cleanup] Finished.")
