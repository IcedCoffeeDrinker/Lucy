import asyncio
import httpx

async def main():
    prompt = input("Enter a prompt: ")
    async with httpx.AsyncClient() as client:

        resp = await client.post(
            "http://localhost:5001/ollama_api",
            json={"prompt": prompt}
        )
        data = resp.json()
        print("LLM says:", data["response"], end='')

if __name__ == "__main__":
    while True:
        asyncio.run(main())
