# AssemblyAI Speech-to-Speech Examples — Claude Code Guide

This file helps Claude Code understand the project and autonomously guide users through setup and deployment.

## What This Repo Is

A collection of voice agent examples using the AssemblyAI Speech-to-Speech (S2S) API. The S2S API is a single WebSocket endpoint that handles speech recognition, language model, and text-to-speech in one hop. You stream PCM16 audio in, you get PCM16 audio back.

## Directory Map

| Path | What it is |
|---|---|
| `pipecat/plugin/` | AssemblyAI S2S plugin for Pipecat framework |
| `pipecat/01-basic-agent/` | Minimal Pipecat voice bot |
| `pipecat/02-lead-capture-agent/` | Pipecat bot with tool calling |
| `livekit/plugin/` | AssemblyAI S2S plugin for LiveKit Agents |
| `livekit/01-basic-agent/` | Minimal LiveKit voice agent |
| `livekit/02-onboarding-agent/` | LiveKit agent with scenario-based flow |
| `websocket/python/` | Raw Python WebSocket client (mic → S2S → speaker) |
| `websocket/node/` | Raw Node.js WebSocket client |
| `tool-calling/` | Standalone tool-calling examples (01, 02, 03) |
| `phone/` | Twilio bridge — gives any agent a real phone number (framework-agnostic) |
| `nextjs-frontend/` | Next.js web app with mic, visualizer, transcript |
| `deploy/` | Railway/Render/Fly config files |
| `scripts/` | setup.sh, deploy-api.sh |

## Environment Variables

Every example needs `ASSEMBLYAI_API_KEY`. Get one at assemblyai.com.

The production S2S URL is `wss://speech-to-speech.us.assemblyai.com/v1/realtime`.

Always run `cp .env.example .env` in the relevant folder and prompt the user for missing values before running anything.

## How to Help a User Deploy

### "I want to run it locally"
1. Ask which example they want
2. `cd` into the folder
3. `cp .env.example .env` and fill in values
4. Python: `uv sync && uv run bot.py` (or `python agent.py dev` for LiveKit)
5. Next.js: `npm install && npm run dev`

### "I want to deploy to Pipecat Cloud"
Requirements: Docker installed, Docker Hub account

```bash
# From inside pipecat/01-basic-agent/ or pipecat/02-lead-capture-agent/
pip install pipecat-ai[cloud]
uv run pipecat cloud auth login
# Edit pcc-deploy.toml: replace YOUR_DOCKERHUB_USERNAME with their Docker Hub username
uv run pipecat cloud secrets set assemblyai-secrets --file .env
uv run pipecat cloud docker build-push
uv run pipecat cloud deploy
```

### "I want to deploy to LiveKit Cloud"
```bash
# Install LiveKit CLI
brew install livekit-cli
# Or: curl -sSL https://get.livekit.io/cli | bash

# Authenticate (opens browser to cloud.livekit.io)
lk cloud auth

# From inside livekit/01-basic-agent/ or livekit/02-onboarding-agent/
lk agent create
# This builds and deploys the agent. Sets LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET automatically.
# Add ASSEMBLYAI_API_KEY in the LiveKit Cloud dashboard -> Agent Settings -> Environment Variables

# Monitor
lk agent status
lk agent logs
```

### "I want to deploy the web app to Vercel"
```bash
cd nextjs-frontend
npm i -g vercel
vercel login
vercel --prod
# When prompted: set NEXT_PUBLIC_ASSEMBLYAI_API_KEY
```

### "I want to deploy to Railway"
```bash
npm i -g @railway/cli
railway login
cd phone/   # or whichever directory has server.py
railway init
railway up
# Set ASSEMBLYAI_API_KEY in Railway dashboard -> Variables tab
# Copy the Railway URL for use as SERVER_URL
```

### "I want to give the agent a phone number"

There are two paths depending on which framework they're using.

---

#### Path A: LiveKit agent + LiveKit Phone Numbers (easiest, no Twilio)

LiveKit Cloud lets you buy a real US phone number and route inbound calls directly to your agent. No Twilio or third-party SIP needed.

1. Deploy the agent to LiveKit Cloud:
```bash
lk cloud auth
cd livekit/01-basic-agent
lk agent create
```

2. In the browser — go to [cloud.livekit.io](https://cloud.livekit.io) → project → **Telephony** → **Phone Numbers** → **Buy a Number**. Select a local or toll-free US number.

3. Go to **Telephony** → **Dispatch Rules** → **Create Rule**. Set it to dispatch inbound calls to your deployed agent.

4. Call the number — the agent answers.

LiveKit handles all SIP/audio bridging automatically. See https://docs.livekit.io/sip for full docs.

---

#### Path B: Twilio bridge (for standalone / Pipecat / WebSocket examples)

This uses `phone/server.py` — a FastAPI server that bridges Twilio Media Streams to AssemblyAI S2S directly.

1. Deploy phone/server.py (Railway is easiest — it gives a public HTTPS URL automatically):
```bash
cd phone
railway login
railway init
railway up
# Note the URL, e.g. https://phone-agent-production.up.railway.app
# Set in Railway dashboard -> Variables: ASSEMBLYAI_API_KEY, SERVER_URL (the Railway URL)
```

2. Install Twilio CLI and log in:
```bash
brew install twilio
twilio login
```

3. Buy a phone number:
```bash
twilio phone-numbers:buy:local --country-code US --voice-enabled
# Note the number shown, e.g. +15551234567
```

4. Wire the number to the server:
```bash
twilio phone-numbers:update +15551234567 \
  --voice-url https://YOUR_RAILWAY_URL/incoming-call \
  --voice-method POST
```

5. Call the number. Done.

**Troubleshooting:**
- If the call connects but there's silence: check that ASSEMBLYAI_API_KEY is set in Railway
- If the call doesn't connect: check the Twilio webhook URL is correct (no trailing slash)
- If audio is garbled: verify the S2S URL points to the right region
- Check Railway logs: `railway logs`
- Check Twilio debugger: console.twilio.com -> Monitor -> Errors

## Common Issues

- **ModuleNotFoundError**: Run `uv sync` first, or check that the sys.path hack is at the top of the file
- **ASSEMBLYAI_API_KEY not set**: Run `cp .env.example .env` and fill in the key
- **WebSocket connection refused**: Check the ASSEMBLYAI_REALTIME_URL is correct
- **No audio on LiveKit**: Make sure LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET are all set

## API Protocol Quick Reference

```
Client -> Server:
  audio.append       { type, audio: <base64 PCM16 24kHz mono> }
  session.configure  { type, session: { system_prompt, tools } }
  response.create    { type }    -- manual trigger
  response.cancel    { type, response_id }
  function.result    { type, call_id, result }

Server -> Client:
  session.ready
  speech.started / speech.stopped
  transcript.user.delta  { text }   -- partial
  transcript.user        { text, item_id }   -- final
  response.started       { response_id }
  response.audio         { data: base64 PCM16 }
  response.transcript    { text }
  response.done / response.interrupted
  function.call          { call_id, name, args }
  error                  { message }
```
