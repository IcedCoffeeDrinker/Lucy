import httpx
import asyncio


async def stream_chat():
    url = "http://localhost:5001/ollama_api"
    data = {
        "messages": [
            {"role": "system", "content": "You are Lucy, a helpful assistant."},
        ]
    }
    async with httpx.AsyncClient() as client:
        while True:
            user_input = input("Enter a message > ")c
            data["messages"].append({"role": "user", "content": user_input})
            async with client.stream("POST", url, json=data) as response:
                async for line in response.aiter_lines():
                    print(line, end='', flush=True)
                print("\n")

asyncio.run(stream_chat())