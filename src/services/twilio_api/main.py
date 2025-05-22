import os
import asyncio
import socket
import base64
from typing import Dict, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
import httpx
from pydantic import BaseModel

from pyngrok import ngrok
from twilio.http.async_http_client import AsyncTwilioHttpClient
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream

from collections import defaultdict
from queue import Queue
import urllib.parse
import audioop

load_dotenv()
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

router = APIRouter()
audio_queues = defaultdict(Queue)  
active_calls = []
connections: Dict[str, "StreamConnection"] = {}

@router.post("/twilio_api/place_call/{user_id}")
async def start_twilio_call(user_id: str):
    url = f"http://localhost:5001/database_api/get_user/{user_id}"
    async with httpx.AsyncClient(timeout=10.0) as client: # Define a reasonable timeout
        response = await client.get(url)
    client_phone_number = response.json()["phone_number"]

    ngrok_tunnel = await asyncio.to_thread(ngrok.connect, 5001, bind_tls=True)
    public_url = ngrok_tunnel.public_url
    print(f"Ngrok public URL for call {user_id}: {public_url}")

    twilio_ws_stream_url = public_url.replace("https://", "wss://") + f"/stream/{user_id}"
    print(f"Twilio WebSocket Stream URL for call {user_id}: {twilio_ws_stream_url}")

    encoded_twilio_ws_stream_url = urllib.parse.quote(twilio_ws_stream_url)
    twiml_callback_url = f"{public_url}/twiml/{user_id}?stream_url={encoded_twilio_ws_stream_url}"
    print(f"TwiML callback URL for Twilio call {user_id}: {twiml_callback_url}")

    http_client = AsyncTwilioHttpClient()
    client = Client(account_sid, auth_token, http_client=http_client)
    
    call = await client.calls.create_async(
        to=client_phone_number,
        from_=TWILIO_PHONE_NUMBER,
        url=twiml_callback_url
    )
    
    active_calls.append({'user_id': user_id, "call_sid": call.sid, "ws_url": twilio_ws_stream_url})
    return {"call_sid": call.sid, "ngrok_public_url": public_url, "twilio_ws_stream_url": twilio_ws_stream_url, "twiml_callback_url": twiml_callback_url}

@router.post("/twiml/{user_id}")
async def serve_twiml_for_stream(user_id: str, stream_url: str = Query(...)):
    """
    Generates TwiML to instruct Twilio to connect and stream media.
    Twilio makes a POST request to this endpoint using the url provided in calls.create_async.
    The stream_url query parameter dictates where Twilio should send the WebSocket media stream.
    """
    response_twiml = VoiceResponse()
    connect = Connect()
    connect.stream(url=stream_url)
    response_twiml.append(connect)
    
    print(f"[{user_id}] Serving TwiML to stream to: {stream_url}")
    print(f"[{user_id}] TwiML Response: {str(response_twiml)}")
    
    return Response(content=str(response_twiml), media_type="application/xml")

class InjectAudio(BaseModel):
    payload_b64: str

class StreamConnection:
    def __init__(self, websocket: WebSocket, user_id: str):
        self.ws = websocket
        self.user_id = user_id
        self.stream_sid: Optional[str] = None

    async def start(self):
        try:
            print(f"[{self.user_id}] WebSocket connection opened. Waiting for messages...")
            async for message_text in self.ws.iter_text(): # Use iter_text for robust JSON parsing
                try:
                    # Ensure message_text is imported from json
                    import json 
                    message = json.loads(message_text)
                except json.JSONDecodeError:
                    print(f"[{self.user_id}] Received non-JSON message: {message_text}")
                    continue

                event = message.get("event")
                # print(f"[{self.user_id}] Received WebSocket event: {event}, Full message: {message}") # Optional debug log

                if event == "connected":
                    print(f"[{self.user_id}] WebSocket 'connected' event. Protocol: {message.get('protocol')}, Version: {message.get('version')}")
                    # streamSid is not reliably in this event.

                elif event == "start":
                    start_payload = message.get("start", {})
                    new_stream_sid = start_payload.get("streamSid")
                    if new_stream_sid:
                        self.stream_sid = new_stream_sid
                        print(f"[{self.user_id}] Media stream 'start' event. streamSid acquired: {self.stream_sid}.")
                        # print(f"[{self.user_id}] Full 'start' event details: {message}") # Optional debug
                    else:
                        print(f"[{self.user_id}] WARNING: 'start' event received but 'streamSid' was missing in 'start' payload. Message: {message}")

                elif event == "media":
                    if not self.stream_sid:
                        print(f"[{self.user_id}] WARNING: 'media' event received but streamSid is not yet set. Discarding media from user_id: {self.user_id}")
                        continue
                    payload = message.get("media", {}).get("payload")
                    if payload:
                        await self._handle_audio(payload)
                    else:
                        print(f"[{self.user_id}] 'media' event received without payload. Message: {message}")
                
                elif event == "stop":
                    stop_payload = message.get("stop", {})
                    print(f"[{self.user_id}] Media stream 'stop' event received for streamSid: {stop_payload.get('streamSid')}. Message: {message}")
                    break 

                elif event == "closed" or event == "disconnected": # WebSocket lifecycle events
                    print(f"[{self.user_id}] WebSocket '{event}' event received. Breaking loop. Message: {message}")
                    break
                
                else:
                    print(f"[{self.user_id}] Received unhandled WebSocket event type: '{event}'. Message: {message}")

        except WebSocketDisconnect as e:
            print(f"[{self.user_id}] WebSocket disconnected by client. Code: {e.code}, Reason: {e.reason}")
        except Exception as e:
            print(f"[{self.user_id}] Error in WebSocket handling loop: {type(e).__name__}: {e}")
        finally:
            print(f"[{self.user_id}] Exited WebSocket handling loop for streamSid {self.stream_sid}.")
            # Actual WebSocket close is typically managed by the endpoint's finally or FastAPI/Uvicorn

    async def _handle_audio(self, payload_b64: str):
        raw_audio = base64.b64decode(payload_b64)
        # Assuming it's 8kHz, 1-channel mu-law from Twilio
        pcm_audio_segment = audioop.ulaw2lin(raw_audio, 2) # 2 bytes for 16-bit linear
        gain_factor = 1.2
            if pcm_audio_segment:
                amplified_audio = audioop.mul(pcm_audio_segment, 2, gain_factor)
                print(f"[{self.user_id}] recv {len(raw_audio)} bytes (ulaw), decoded to {len(pcm_audio_segment)} bytes (pcm), amplified to {len(amplified_audio)} bytes")
                audio_queues[self.user_id].put(amplified_audio)
            else:
                audio_queues[self.user_id].put(pcm_audio_segment) 
        except audioop.error as e:
            print(f"[{self.user_id}] audioop.error during gain application: {e}. Using original PCM audio.")
            audio_queues[self.user_id].put(pcm_audio_segment) 

    async def send_audio(self, payload_b64: str):
        """Send one 20 ms audio packet back into the call."""
        if not self.stream_sid:
            raise RuntimeError("streamSid not yet received; wait for 'start' event from Twilio media stream")
        await self.ws.send_json(
            {
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {"payload": payload_b64},
            }
        )

@router.websocket("/stream/{user_id}")
async def twilio_stream(websocket: WebSocket, user_id: str):
    await websocket.accept()
    conn = StreamConnection(websocket, user_id)
    connections[user_id] = conn
    print(f"[{user_id}] WebSocket connection established for /stream/{user_id}")
    try:
        await conn.start()
    except WebSocketDisconnect:
        print(f"[{user_id}] WebSocketDisconnect caught directly in twilio_stream for /stream/{user_id}")
    except Exception as e:
        print(f"[{user_id}] Exception caught in twilio_stream for /stream/{user_id}: {type(e).__name__} - {e}")
    finally:
        print(f"[{user_id}] Cleaning up connection for /stream/{user_id} (streamSid: {conn.stream_sid if conn else 'N/A'})")
        if connections.pop(user_id, None):
            print(f"[{user_id}] Removed StreamConnection object from 'connections' dict.")
        else:
            print(f"[{user_id}] WARNING: StreamConnection object for user_id {user_id} not found in 'connections' dict during cleanup.")

        # Clean up active_calls
        call_to_remove_index = -1
        for i, call_info in enumerate(active_calls):
            if call_info.get("user_id") == user_id: 
                call_to_remove_index = i
                break
        
        if call_to_remove_index != -1:
            try:
                removed_call = active_calls.pop(call_to_remove_index)
                print(f"[{user_id}] Removed call (SID: {removed_call.get('call_sid')}) from 'active_calls' list.")
                if removed_call and 'ngrok_public_url' in removed_call:
                    url_to_disconnect = removed_call['ngrok_public_url']
                    print(f"[{user_id}] Disconnecting ngrok tunnel: {url_to_disconnect}")
                    try:
                        await asyncio.to_thread(ngrok.disconnect, url_to_disconnect)
                        print(f"[{user_id}] Successfully disconnected ngrok tunnel: {url_to_disconnect}")
                    except Exception as e:
                        print(f"[{user_id}] Error disconnecting ngrok tunnel {url_to_disconnect}: {e}")
            except IndexError:
                print(f"[{user_id}] ERROR: IndexError while trying to pop call for user_id {user_id} from active_calls. List may have changed.")
        else:
            print(f"[{user_id}] WARNING: Could not find call in 'active_calls' to remove for user_id {user_id}.")
        
        print(f"[{user_id}] WebSocket for /stream/{user_id} is now fully closed and cleaned up.")
        # Ensure WebSocket is closed if not already; FastAPI usually handles this when the handler finishes.
        try:
            if websocket.client_state == websocket.client_state.CONNECTED: # Check if WebSocket is still connected
                 await websocket.close()
                 print(f"[{user_id}] WebSocket explicitly closed in twilio_stream finally block.")
        except Exception as e:
            print(f"[{user_id}] Exception while trying to explicitly close WebSocket in finally: {e} (might be already closed)")

@router.get("/twilio_api/audio_stream/{user_id}")
async def audio_stream(user_id: str):
    """Stream audio data for the given user_id."""
    if user_id not in audio_queues:
        raise HTTPException(status_code=404, detail="No active audio stream for user_id")

    async def audio_generator():
        while True:
            if not audio_queues[user_id].empty():
                chunk = audio_queues[user_id].get()
                yield chunk
            else:
                await asyncio.sleep(0.01)

    return StreamingResponse(audio_generator(), media_type="audio/wav")

@router.post("/twilio_api/inject/{user_id}")
async def inject_audio(user_id: str, body: InjectAudio):
    conn = connections.get(user_id)
    if not conn:
        raise HTTPException(status_code=404, detail="No active call for user_id")
    await conn.send_audio(body.payload_b64)
    return {"status": "sent"}

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0

if __name__ == "__main__":
    print("Starting Twilio API...")
    from fastapi import FastAPI
    standalone_app = FastAPI()
    standalone_app.include_router(router)
    import socket
    if not is_port_in_use(5001):
        import uvicorn
        uvicorn.run(standalone_app, host="0.0.0.0", port=5001, reload=True) 
    #asyncio.run(start_twilio_call("01JVT4A67BNZX7BJXKFVWKKHPM"))