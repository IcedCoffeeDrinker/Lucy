from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter
import httpx
import asyncio

router = APIRouter()
active_sessions = {}
url = "http://csm_tts:8000/api/v1/audio/conversation"


async def generate_audio(text: str, user_id: str):
    payload = {
        "text": text,
        "speaker_id": 0,
        "context": active_sessions[user_id]["context"],
        "temperature": 0.7,
        "response_format": "wav",
        "topk": 50
    }
    async with httpx.AsyncClient() as client:
        try:
            print(payload) # debugging 
            response = await client.post(url, json=payload)
            response.raise_for_status()  # This will raise an exception for 4XX/5XX Sresponses
            audio_data = response.content  # This will be bytes
            return audio_data

        except httpx.HTTPStatusError as exc:
            print(f"HTTP error occurred: {exc.response.status_code} - {exc.response.text}")
        except httpx.RequestError as exc:
            print(f"An error occurred while requesting {exc.request.url!r}: {exc}")


@router.post("/csm_api/conversation/{user_id}")
async def handle_conversation(user_id: str,payload: dict):
    if user_id not in active_sessions:
        active_sessions[user_id] = {"context": []}
    user_text, llm_text = payload.get("user_text"), payload.get("llm_text")
    audio = await generate_audio(llm_text, user_id)
    new_context = [{"text": user_text, "speaker": 0}, {"text": llm_text, "speaker_id": 1}]
    active_sessions[user_id]["context"] += new_context
    return {"audio": audio}

@router.post("/csm_api/conversation/terminate/{user_id}")
async def terminate_conversation(user_id: str):
    del active_sessions[user_id]
    return {"message": "Conversation terminated"}
    

'''
curl -X POST http://localhost:8000/api/v1/audio/conversation \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Nice to meet you too!",
    "speaker_id": 0,
    "context": [
      {
        "speaker": 1,
        "text": "Hello, nice to meet you.",
        "audio": "BASE64_ENCODED_AUDIO"
      }
    ]
  }' \
  --output response.wav
'''
