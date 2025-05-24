# Lucy - AI Accountability Friend
Lucy uses advanced emotional AI to provide motivational support through regular phone calls, helping you stay accountable and focused on your goals.

Check out Lucy's [demo product page](https://lucy-daily-drive.lovable.app/)

## Description

+ **Daily Check-ins**
--> Lucy connects with you daily via Discord or phone, ensuring you stay on track.

+ **Set Your Own Schedule**
--> You decide when Lucy should call—flexibility tailored to your routine.

+ **Goal Alignment**
--> Stay accountable with Lucy's unique blend of motivation, humor, and support.

+ **Emotional Intelligence**
--> Lucy adapts to your needs, offering encouragement with kindness or tough love, just the way you need it.

## Subscription Plans
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
- [Faster-Whisper-Server](https://github.com/etalab-ia/faster-whisper-server)
- [Docker](https://www.docker.com/)

## Testing / Local Deployment
Use Docker for local development. Install the docker engine first, then proceed.
For local deployment:
```bash
git clone https://github.com/IcedCoffeeDrinker/Lucy.git
cd Lucy
docker-compose build
docker-compose up
```
Then in a seperate terminal:
```bash
# Execute any test by running them with python3. You may have to install additional dependencies.
# Example:
python3 src/services/faster_whisper_api/tests/test_live_transcription.py
# most tests use dynamic paths, so you can execute them from anywhere
```


## Project State
Currently working:
- `database_api`
- `ollama_api`
- `twilio_api`
- `faster_whisper_api`

Ollama speaks to my local server and isn't set up to work with local ollama files yet. A migration from `pip` to `poetry` is planned. 