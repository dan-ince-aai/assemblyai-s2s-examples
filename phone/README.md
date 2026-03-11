# Phone Agent — Twilio + AssemblyAI S2S

Give your voice agent a real phone number. Calls go through Twilio, audio is bridged to AssemblyAI's S2S API in real time.

## How it works

```
Phone Call -> Twilio -> WebSocket -> server.py -> AssemblyAI S2S
                                         |
Phone Call <- Twilio <- WebSocket <------+
```

`server.py` is a FastAPI application that:
1. Receives incoming call webhooks from Twilio (`POST /incoming-call`)
2. Returns TwiML instructing Twilio to open a Media Stream WebSocket to `/media-stream`
3. Bridges audio between Twilio (mulaw 8 kHz) and AssemblyAI S2S (PCM16 24 kHz)

Audio is transcoded in both directions using Python's stdlib `audioop` module — no external audio libraries needed.

## Quick Deploy

### Step 1 — Deploy the server (needs public HTTPS URL)

**Railway (recommended — easiest):**
```bash
npm i -g @railway/cli
railway login
cd phone/
railway init
railway up
# Copy the Railway URL (e.g. https://my-app.up.railway.app)
```

**Fly.io:**
```bash
brew install flyctl
fly auth login
cd phone/
fly launch   # uses fly.toml — skip config prompts
fly secrets set ASSEMBLYAI_API_KEY=your_key_here
fly deploy
# Copy the Fly URL (e.g. https://assemblyai-phone-agent.fly.dev)
```

**Render:**
Push to GitHub, connect at render.com -> New Web Service. Set:
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn server:app --host 0.0.0.0 --port $PORT`

**Local dev with ngrok:**
```bash
pip install -r requirements.txt
uvicorn server:app --port 8080 --reload
# In another terminal:
ngrok http 8080
# Use the ngrok HTTPS URL as your webhook URL
```

### Step 2 — Set environment variables

In Railway or Render dashboard, add:

| Variable | Value |
|---|---|
| `ASSEMBLYAI_API_KEY` | Your AssemblyAI API key |
| `SERVER_URL` | Your deployed URL, e.g. `https://my-app.up.railway.app` |
| `ASSEMBLYAI_REALTIME_URL` | `wss://speech-to-speech.us.assemblyai.com/v1/realtime` |

Or copy `.env.example` to `.env` and fill in values for local dev:
```bash
cp .env.example .env
```

### Step 3 — Buy a Twilio phone number

```bash
# Install Twilio CLI
brew install twilio
# or: pip install twilio

# Log in (opens browser)
twilio login

# Buy a US number with voice enabled
twilio phone-numbers:buy:local --country-code US --voice-enabled
# Note the number, e.g. +15551234567
```

Or buy at [console.twilio.com](https://console.twilio.com) -> Phone Numbers -> Buy a Number.

### Step 4 — Point the number at your server

```bash
# Replace with your actual number and server URL
twilio phone-numbers:update +15551234567 \
  --voice-url https://my-app.up.railway.app/incoming-call \
  --voice-method POST
```

Or in Twilio console: Phone Numbers -> Manage -> Active Numbers -> click the number -> Voice Configuration -> set Webhook URL to `https://YOUR_SERVER_URL/incoming-call` with HTTP POST.

### Step 5 — Call it

Call your Twilio number. You should hear the agent respond within a few seconds.

## Troubleshooting

- **Silence after connecting**: Check that `ASSEMBLYAI_API_KEY` is set correctly in Railway/Render
- **Call doesn't connect**: Verify the Twilio webhook URL is correct — no trailing slash, HTTPS only
- **Audio is distorted**: Verify `ASSEMBLYAI_REALTIME_URL` points to the correct region
- **500 error on incoming-call**: Check `SERVER_URL` is set (it's used to build the WebSocket URL in the TwiML response)
- **Check Railway logs**: `railway logs`
- **Check Twilio debugger**: [console.twilio.com](https://console.twilio.com) -> Monitor -> Errors & Warnings

## Customise the agent

Edit the `SYSTEM_PROMPT` variable at the top of `server.py` to change the agent's personality and behaviour.

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in ASSEMBLYAI_API_KEY and SERVER_URL

uvicorn server:app --host 0.0.0.0 --port 8080 --reload
```

The server starts at `http://localhost:8080`. Use ngrok or similar to expose it publicly for Twilio to reach.

## File structure

```
phone/
  server.py         # FastAPI + WebSocket bridge
  requirements.txt  # Python dependencies
  .env.example      # Environment variable template
  README.md         # This file
```
