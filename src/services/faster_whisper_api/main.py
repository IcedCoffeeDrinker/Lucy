import os
# import httpx # No longer needed for batch transcription
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect # Removed UploadFile, File
import asyncio
import websockets # For the outbound WebSocket connection

router = APIRouter(
    prefix="/faster_whisper_api",
    tags=["faster-whisper"]
)

# WHISPER_SERVER_URL for HTTP API is no longer needed as batch transcription is removed
# WHISPER_HTTP_SERVER_URL = os.getenv("WHISPER_SERVER_URL", "http://whisper:8000/v1/")

# Define the WebSocket URL for the live transcription server
# Assuming the faster-whisper-server is named 'whisper' in your docker-compose network
# and its WebSocket endpoint is on port 8000 at /v1/audio/transcriptions
WHISPER_WS_SERVER_URL = os.getenv("WHISPER_WS_SERVER_URL", "ws://whisper:8000/v1/audio/transcriptions")

# @router.post("/transcribe") # Batch transcription endpoint removed
# async def transcribe_audio(file: UploadFile = File(...), model: str = "Systran/faster-distil-whisper-large-v3"):
#     """
#     Receives an audio file, sends it to the faster-whisper-server for transcription,
#     and returns the transcription result.
#     """
#     if not WHISPER_HTTP_SERVER_URL:
#         raise HTTPException(status_code=500, detail="WHISPER_SERVER_URL for HTTP is not configured.")
# 
#     transcribe_url = f"{WHISPER_HTTP_SERVER_URL.rstrip('/')}/audio/transcriptions"
#     
#     files = {"file": (file.filename, await file.read(), file.content_type)}
#     data = {"model": model, "response_format": "json"}
# 
#     async with httpx.AsyncClient() as client:
#         try:
#             response = await client.post(transcribe_url, files=files, data=data, timeout=60.0)
#             response.raise_for_status() # Raise an exception for bad status codes
#             return response.json()
#         except httpx.HTTPStatusError as e:
#             # Attempt to parse error detail from whisper server response if possible
#             detail = e.response.json().get("error", {}).get("message", e.response.text) if e.response.content else str(e)
#             raise HTTPException(status_code=e.response.status_code, detail=f"Error from whisper server: {detail}")
#         except httpx.RequestError as e:
#             raise HTTPException(status_code=503, detail=f"Could not connect to whisper server: {e}")

async def forward_to_server(client_ws: WebSocket, server_ws: websockets.WebSocketClientProtocol):
    """Forward messages from client to server."""
    try:
        while True:
            data = await client_ws.receive_bytes() # Assuming audio data is bytes
            await server_ws.send(data)
    except WebSocketDisconnect:
        print("Client disconnected")
    except websockets.exceptions.ConnectionClosed:
        print("Connection to whisper server closed while forwarding from client")
    except Exception as e:
        print(f"Error forwarding client to server: {e}")

async def forward_to_client(client_ws: WebSocket, server_ws: websockets.WebSocketClientProtocol):
    """Forward messages from server to client."""
    try:
        while True:
            message = await server_ws.recv() # Can be text (JSON) or bytes
            if isinstance(message, str):
                await client_ws.send_text(message)
            elif isinstance(message, bytes):
                await client_ws.send_bytes(message)
    except websockets.exceptions.ConnectionClosed:
        print("Connection to whisper server closed while forwarding to client")
    except WebSocketDisconnect:
        print("Client disconnected (unexpectedly in forward_to_client)")
    except Exception as e:
        print(f"Error forwarding server to client: {e}")

@router.websocket("/live_transcribe")
async def live_transcribe_endpoint(client_ws: WebSocket):
    await client_ws.accept()
    print("Client WebSocket connection accepted.")

    if not WHISPER_WS_SERVER_URL:
        print("WHISPER_WS_SERVER_URL is not configured.")
        await client_ws.close(code=1008, reason="Server not configured")
        return

    try:
        print(f"Connecting to whisper server at {WHISPER_WS_SERVER_URL}...")
        async with websockets.connect(WHISPER_WS_SERVER_URL, open_timeout=10) as server_ws:
            print("Connected to whisper server.")
            
            client_to_server_task = asyncio.create_task(forward_to_server(client_ws, server_ws))
            server_to_client_task = asyncio.create_task(forward_to_client(client_ws, server_ws))
            
            done, pending = await asyncio.wait(
                [client_to_server_task, server_to_client_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            
            for task in pending:
                task.cancel()
            print("Live transcription session ended.")

    except websockets.exceptions.InvalidURI:
        msg = f"Invalid WebSocket URI for whisper server: {WHISPER_WS_SERVER_URL}"
        print(msg)
        await client_ws.close(code=1011, reason=msg)
    except ConnectionRefusedError:
        msg = f"Connection refused by whisper server at {WHISPER_WS_SERVER_URL}"
        print(msg)
        await client_ws.close(code=1011, reason=msg)
    except Exception as e:
        msg = f"Error in live transcription endpoint: {e}"
        print(msg)
        await client_ws.close(code=1011, reason=str(e))
    finally:
        # Ensure client connection is closed if not already.
        # Check state to avoid errors if already closed by one of the tasks.
        if hasattr(client_ws, 'client_state') and client_ws.client_state != WebSocketDisconnect:
             try:
                await client_ws.close()
                print("Client WebSocket connection closed from finally block.")
             except RuntimeError as e:
                print(f"Ignoring error during final client_ws.close(): {e}")
