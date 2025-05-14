# Planning

### Project Split
- AI phone assistant (Lucy)
- AI 'living in your house' assistant (Lucy Roommate)

## Lucy
Description:
"Ever felt the need of someone reliably kicking your ass so you stay on track? Lucy will be exactly that 'person' for you."

### Basic Components
- twilio for voice streaming (both ways)
- csm for voice 
- fast-whisper for speech to text
- text (/ vector) storage for personalization
- time based activation script

## Lucy Roommate
Description:
An AI assistant with an excess point in your room. It locally evaluates sound to decide 
when to step in (possibly even unasked). Images are taken every 10 minutes and locally interpreted. 
If you're slacking off the AI will ask you if your seriously resting and nag you humorously if you're
actually procrastinating. 

- cloud server (local for development)
- Physical Lucy device
    - Streams sound both ways
    - Records and evaluates pictures every 15 min
    - (Display fr avatar)
- Standard Lucy components
- Always listening activation script
- multi-user personalization storage
