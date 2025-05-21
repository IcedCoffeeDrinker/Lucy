# Lucy - AI Accountability Friend
Lucy uses advanced emotional AI to provide motivational support through regular phone calls, helping you stay accountable and focused on your goals.

Checkout Lucy's [demo product page](https://lucy-daily-drive.lovable.app/)

## Description
**Daily Check-ins** Lucy will call you either over discord or phone
**Set Your Own Schedule** You tell Lucy when to call you
**Goal Alignment** Be mocked, motivated, and held accountable for your daily progress
**Emotional Intelligence** Lucy learns how to motivate you specifically - with kindness or tough love

# Subscription Plans
### All plans include:
- Personalized conversations
- Memory of Past conversations
- Emotional finetuning

### **Daily Nudge**
- 1 check-in call a day
- price: 5$ / month

### **Double Truble**
- 2 check-in calls a day
- Weekly insights and reports
- price: 8$ / month

### **Get Me To Ivy**
- Up to 5 check-in calls
- dynamic intensity in 'sloppy phases'
- Weekly insights and reports
- Detailed analytics on your consistency

# Dev Section

## Stack
- [Twilio](https://github.com/twilio/twilio-python) / [Discord.js/voice](https://www.npmjs.com/package/@discordjs/voice)
- [SQLite](https://sqlite.org/)
- [Ollama](https://ollama.com/)
- [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper)
- [Docker](https://www.docker.com/)

## Testing / Local Deployment
Currently Docker isn't used. 
Instead create a python `.venv` at the root directory and install the dependencies with pip.
```bash
cd Lucy

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
Use the template `.env.example` file to create a `.env` at `Lucy/.env`
Execute the central `main.py` file at `Lucy/src/services/main.py`

# Project State
Currently `database_api` and `ollama_api` are working.
Ollama speaks to my local server and isn't set up to work with local model files yet. Docker has yet to be implemented and a migration from `pip` to `poetry` is planned. 