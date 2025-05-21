from fastapi import FastAPI
from src.services.database_api.main import app as database_app
from src.services.ollama_api.main import app as ollama_app
from src.services.twilio_api.main import app as twilio_app
app = FastAPI()

# already specified path in the imported apps, e.g. /ollama_api
app.mount("/", database_app)
app.mount("/", ollama_app)
app.mount("/", twilio_app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("project_main:app", host="0.0.0.0", port=5001, reload=True)