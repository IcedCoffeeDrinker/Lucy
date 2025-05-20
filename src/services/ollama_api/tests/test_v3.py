import httpx
import asyncio
import random

session_id = random.randint(1, 1000000)

async def stream_chat():
    url = "http://localhost:5001/ollama_api"
    data = {
        "session_id": session_id, "message": ""
    }
    async with httpx.AsyncClient() as client:
        while True:
            user_input = input("Enter a message > ")
            data["message"] = user_input
            async with client.stream("POST", url, json=data) as response:
                async for line in response.aiter_lines():
                    print(line, end='', flush=True)
                print("\n")

asyncio.run(stream_chat())