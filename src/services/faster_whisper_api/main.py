import os
import httpx
from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter(
    prefix="/faster_whisper_api",
    tags=["faster-whisper"]
)

WHISPER_SERVER_URL = os.getenv("WHISPER_SERVER_URL", "http://localhost:8000/v1/") # Default for local dev outside Docker

@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...), model: str = "Systran/faster-distil-whisper-large-v3"):
    """
    Receives an audio file, sends it to the faster-whisper-server for transcription,
    and returns the transcription result.
    """
    if not WHISPER_SERVER_URL:
        raise HTTPException(status_code=500, detail="WHISPER_SERVER_URL is not configured.")

    transcribe_url = f"{WHISPER_SERVER_URL.rstrip('/')}/audio/transcriptions"
    
    files = {"file": (file.filename, await file.read(), file.content_type)}
    data = {"model": model} # You can add other parameters like language here

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(transcribe_url, files=files, data=data)
            response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
            return response.json()
        except httpx.HTTPStatusError as e:
            # Log the error and details for debugging
            print(f"HTTP error occurred: {e}")
            print(f"Response content: {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail=f"Error from whisper server: {e.response.text}")
        except httpx.RequestError as e:
            # Log the error for debugging
            print(f"Request error occurred: {e}")
            raise HTTPException(status_code=503, detail=f"Could not connect to whisper server: {e}")
