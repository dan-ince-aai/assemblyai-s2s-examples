# LiveKit Agents + AssemblyAI Speech-to-Speech

[LiveKit Agents](https://agents.livekit.io) is a framework for building real-time voice and multimodal AI agents on top of the LiveKit RTC platform. Agents run as server-side workers that join a LiveKit room and process audio from participants.

The `plugin/` directory contains `RealtimeModel` and `RealtimeSession`, which implement LiveKit's `llm.RealtimeModel` / `llm.RealtimeSession` interfaces backed by AssemblyAI's native S2S WebSocket API. This means you can drop it in wherever a LiveKit realtime model is expected.

The plugin handles:
- WebSocket connection and send/receive task management (via `aiohttp`)
- Audio resampling to 24 kHz mono
- LiveKit event emission (`generation_created`, `input_speech_started`, `input_audio_transcription_completed`, etc.)
- Function call bridging via `FunctionCall` / `FunctionCallOutput` in the chat context

## Examples

| Directory | Description |
|---|---|
| `01-basic-agent/` | Minimal agent with a brief, conversational assistant |
| `02-onboarding-agent/` | DeliveryHero rider onboarding — scenario-based conversation |

## Quick Start

```bash
# 1. Install dependencies
cd livekit/01-basic-agent
uv sync

# 2. Configure environment
cp .env.example .env
# Fill in ASSEMBLYAI_API_KEY, LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET

# 3. Run in development mode (connects to LiveKit Cloud sandbox)
python agent.py dev
```

## Plugin — RealtimeModel

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'plugin'))

from assemblyai_realtime import RealtimeModel as AssemblyAIRealtimeModel

session = AgentSession(
    llm=AssemblyAIRealtimeModel(
        url="wss://speech-to-speech.us.assemblyai.com/v1/realtime",
        api_key=os.environ["ASSEMBLYAI_API_KEY"],
    )
)
```

## Deploy to LiveKit Cloud

```bash
# 1. Install LiveKit CLI
brew install livekit-cli
# or: curl -sSL https://get.livekit.io/cli | bash

# 2. Authenticate (opens browser to cloud.livekit.io)
lk cloud auth

# 3. Create and deploy the agent (run from inside 01-basic-agent/ or 02-onboarding-agent/)
lk agent create
# This registers the agent, builds a Docker image, and deploys it.
# A livekit.toml config file is generated automatically.
# Add ASSEMBLYAI_API_KEY in the LiveKit Cloud dashboard -> Agent Settings -> Environment Variables

# 4. Monitor
lk agent status
lk agent logs
```

Set environment variables in the LiveKit Cloud dashboard under Agent Settings:
- `ASSEMBLYAI_API_KEY`
- `ASSEMBLYAI_REALTIME_URL`
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` (set automatically by `lk agent create`)

For more information see [cloud.livekit.io](https://cloud.livekit.io).

## Docker Deploy

Each example includes a `Dockerfile` for containerized deployment:

```bash
cd livekit/01-basic-agent
docker build -t assemblyai-livekit-basic .
docker run --env-file .env assemblyai-livekit-basic
```

## Deploy to Railway

```bash
npm i -g @railway/cli
railway login
cd livekit/01-basic-agent
railway init
railway up
# Set ASSEMBLYAI_API_KEY, LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET in Railway dashboard -> Variables
```

## Deploy to Render

```bash
# Push to GitHub, then connect repo at render.com -> New Web Service
# Build command: pip install -r requirements.txt
# Start command: python agent.py start
# Add env vars in the Render dashboard
```

## Give Your Agent a Phone Number

LiveKit has **built-in phone number support** — you can buy a real US phone number directly through LiveKit Cloud and route inbound calls straight to your agent. No Twilio or third-party SIP provider needed.

### Option A — LiveKit Phone Numbers (recommended)

LiveKit Cloud lets you purchase local and toll-free US numbers and attach them to your agent in a few steps.

**Step 1 — Deploy your agent to LiveKit Cloud**
```bash
lk cloud auth
cd livekit/01-basic-agent
lk agent create
# Note your project's LiveKit URL
```

**Step 2 — Buy a phone number**

Go to [cloud.livekit.io](https://cloud.livekit.io) → your project → **Telephony** → **Phone Numbers** → **Buy a Number**. Select a local or toll-free US number.

**Step 3 — Create a dispatch rule**

In the LiveKit Cloud dashboard → **Telephony** → **Dispatch Rules** → **Create Rule**. Set it to dispatch inbound calls to your agent. Your agent will automatically join a new room for each incoming call.

**Step 4 — Call it**

Call the number. Your LiveKit agent answers.

LiveKit telephony also supports:
- Outbound calls
- DTMF (keypad input)
- Call transfers
- Noise cancellation (Krisp)
- HD voice

See [docs.livekit.io/sip](https://docs.livekit.io/sip) for full telephony docs.

---

### Option B — Twilio bridge (standalone, framework-agnostic)

If you want a phone number that works without LiveKit (e.g. with the raw WebSocket examples), use `phone/server.py` — a FastAPI bridge between Twilio Media Streams and AssemblyAI S2S directly.

See [`phone/README.md`](../phone/README.md) for the full setup guide.
