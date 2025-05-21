import httpx, json
from typing import AsyncGenerator, List, Dict
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

'''
Wrapper for locally hosted Ollama LLM
Last edit: Implement server-side system message and session management
use test_v3.py for testing
'''

app = FastAPI()
OLLAMA_URL = "http://192.168.1.234:11434/api/chat"
MODEL = "dolphin-mistral"
SYSTEM = "You are Lucy, a helpful assistant."

sessions = {}
system = {"role": "system", "content": "You are Lucy, a helpful assistant."}

async def stream_ollama(messages: List[Dict]) -> AsyncGenerator[str, None]:
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", OLLAMA_URL, json={"messages": messages, "model": MODEL}, timeout=None) as response:
            async for line in response.aiter_lines():
                if line.strip(): 
                    parsed_line = json.loads(line)
                    yield parsed_line["message"]["content"]

@app.post("/ollama_api")
async def chat_stream(payload: dict):
    session_id = payload.get("session_id")
    if session_id not in sessions:
        sessions[session_id] = []
        sessions[session_id].append(system)
    sessions[session_id].append({"role": "user", "content": payload["message"]})
    async def event_generator():
        async for chunk in stream_ollama(sessions[session_id]):
            yield chunk + "\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0

if __name__ == "__main__":
    import socket
    if not is_port_in_use(5001):
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=5001, reload=True)