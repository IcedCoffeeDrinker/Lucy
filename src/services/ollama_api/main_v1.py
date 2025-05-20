'''
AI wrapper for locally hosed Ollama LLM
'''

from ollama import chat
from fastapi import FastAPI, Request

# SETTINGS
MODEL = 'dolphin-mistral'
SYSTEM = 'You are Lucy, a helpful assistant.'


app = FastAPI()


def ollama_api():
    '''
    Main function to run the Ollama API
    '''
    # Set up the model and system message
    stream = chat(
        model=MODEL,
        messages=[{'role': 'system', 'content': SYSTEM}],
        stream=True,
        base_url='http://192.168.1.234:11434',
    )

    # Print the response from the model
    for chunk in stream:
        print(chunk['message']['content'], end='', flush=True)

@app.post("/ollama_api")
async def generate(request: Request):
    body = await request.json()
    prompt = body.get("prompt")

    response = chat(model=MODEL, message=[{'role': 'user', 'content': prompt}])
    return {'response': response['message']['content']}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5001, reload=True)