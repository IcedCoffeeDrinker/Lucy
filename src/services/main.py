from fastapi import FastAPI
from ollama_api.main import app as ollama_app
from twilio_api.main import app as twilio_app
from database_api.main import app as database_app
app = FastAPI()

# already specified path in the imported apps, e.g. /ollama_api
app.mount("/", ollama_app)
app.mount("/", twilio_app)
app.mount("/", database_app) # this has to be last, else crash :)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=5001, reload=True)