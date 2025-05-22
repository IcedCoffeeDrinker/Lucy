import os
import asyncio
import socket

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import httpx

from pyngrok import ngrok
from twilio.http.async_http_client import AsyncTwilioHttpClient
from twilio.rest import Client

from collections import defaultdict
from queue import Queue

load_dotenv()
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

app = FastAPI()
audio_queues = defaultdict(Queue)  
active_calls = []
connections: Dict[str, "StreamConnection"] = {}

@app.post("/twilio_api/place_call/{user_id}")
async def start_twilio_call(user_id: str):
    url = f"http://localhost:5001/database_api/get_user/{user_id}"
    response = httpx.get(url)
    client_phone_number = response.json()["phone_number"]
    public_url = ngrok.connect(5001, bind_tls=True).public_url
    ws_url = public_url.replace("https://", "wss://") + "/stream"
    print(ws_url)

    http_client = AsyncTwilioHttpClient()
    client = Client(account_sid, auth_token, http_client=http_client)
    call = await client.calls.create_async(to=client_phone_number,
                           from_=TWILIO_PHONE_NUMBER,
                           url=public_url)
    active_calls.append({'user_id': user_id, "call_sid": call.sid, "ws_url": ws_url})
    return {"call_sid": call.sid}


class InjectAudio(BaseModel):
    payload_b64: str

class StreamConnection:
    def __init__(self, websocket: WebSocket, user_id: str):
        self.ws = websocket
        self.user_id = user_id
        self.stream_sid: Optional[str] = None

    async def start(self):
        try:
            async for message in self.ws.iter_json():
                event = message.get("event")
                if event == "connected":
                    self.stream_sid = message["streamSid"]
                    print(f"[{self.user_id}] streamSid={self.stream_sid} connected")
                elif event == "media":
                    await self._handle_audio(message["media"]["payload"])
                elif event in ("closed", "disconnected"):
                    break
        finally:
            await self.ws.close()

    async def _handle_audio(self, payload_b64: str):
        pcm = base64.b64decode(payload_b64)
        print(f"[{self.user_id}] recv {len(pcm)} bytes")
        # Add the audio data to the queue for streaming
        audio_queues[self.user_id].put(pcm)

    async def send_audio(self, payload_b64: str):
        """Send one 20 ms audio packet back into the call."""
        if not self.stream_sid:
            raise RuntimeError("streamSid not yet received; wait for 'connected' event")
        await self.ws.send_json(
            {
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {"payload": payload_b64},
            }
        )

@app.websocket("/stream/{user_id}")
async def twilio_stream(websocket: WebSocket, user_id: str):
    await websocket.accept()
    conn = StreamConnection(websocket, user_id)
    connections[user_id] = conn
    try:
        await conn.start()
    except WebSocketDisconnect:
        pass
    finally:
        connections.pop(user_id, None)
        print(f"[{user_id}] disconnected")

@app.get("/audio_stream/{user_id}")
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
                await asyncio.sleep(0.01)  # Prevent busy-waiting

    return StreamingResponse(audio_generator(), media_type="audio/wav")

@app.post("/inject/{user_id}")
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
    import socket
    if not is_port_in_use(5001):
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=5001, reload=True)
    asyncio.run(start_twilio_call("01JVT4A67BNZX7BJXKFVWKKHPM"))