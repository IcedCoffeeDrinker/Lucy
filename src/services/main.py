from fastapi import FastAPI
from ollama_api.main import router as ollama_router
from twilio_api.main import router as twilio_router
from database_api.main import router as database_router
app = FastAPI()

# already specified path in the imported apps, e.g. /ollama_api
app.include_router(ollama_router)
app.include_router(twilio_router)
app.include_router(database_router) # this has to be last, else crash :)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=5001, reload=True, workers=4)