import httpx
from typing import AsyncGenerator, List, Dict
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import json

app = FastAPI()
OLLAMA_URL = "http://192.168.1.234:11434/api/chat"
MODEL = "dolphin-mistral"

async def stream_ollama(messages: List[Dict]) -> AsyncGenerator[str, None]:
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", OLLAMA_URL, json={"messages": messages, "model": MODEL}, timeout=None) as response:
            async for line in response.aiter_lines():
                if line.strip(): 
                    parsed_line = json.loads(line)
                    yield parsed_line["message"]["content"]

@app.post("/ollama_api")
async def chat_stream(payload: dict):
    async def event_generator():
        async for chunk in stream_ollama(payload["messages"]):
            yield chunk + "\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5001, reload=True)