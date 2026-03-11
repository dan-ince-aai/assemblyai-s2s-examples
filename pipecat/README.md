# Pipecat + AssemblyAI Speech-to-Speech

[Pipecat](https://pipecat.ai) is an open-source framework for building voice AI pipelines. It models audio processing as a directed graph of processors — each frame flows through `transport.input → processors → transport.output`.

The `plugin/` directory contains `AssemblyAIRealtimeLLMService`, a drop-in `LLMService` that replaces any OpenAI-compatible LLM with AssemblyAI's native S2S endpoint. The plugin handles:

- WebSocket connection lifecycle (connect/disconnect/reconnect)
- Audio forwarding (`InputAudioRawFrame` → `audio.append`)
- Server event handling (transcripts, audio, function calls)
- Pipecat frame emission (`TTSAudioRawFrame`, `TranscriptionFrame`, `BotStartedSpeakingFrame`, etc.)
- Tool registration and dispatch via Pipecat's `register_function` API

## Examples

| Directory | Description |
|---|---|
| `01-basic-agent/` | Minimal 3-stage pipeline: input → AssemblyAI LLM → output |
| `02-lead-capture-agent/` | Facebook Ads intake agent with a `save_lead` tool |

## Quick Start

```bash
# 1. Copy the plugin (already in plugin/ — just install deps)
cd pipecat/01-basic-agent

# 2. Install dependencies
uv sync

# 3. Configure environment
cp .env.example .env
# Edit .env and add ASSEMBLYAI_API_KEY and ASSEMBLYAI_REALTIME_URL

# 4. Run
uv run bot.py
```

## Plugin — AssemblyAIRealtimeLLMService

```python
from pipecat_assemblyai_realtime import AssemblyAIRealtimeLLMService

llm = AssemblyAIRealtimeLLMService(
    url="wss://speech-to-speech.us.assemblyai.com/v1/realtime",
    api_key="your-key",
    system_prompt="You are a helpful assistant.",
)
```

### Registering tools

```python
from pipecat.services.llm_service import FunctionCallParams

async def my_tool(params: FunctionCallParams) -> None:
    args = params.arguments
    await params.result_callback(f"Result for {args}")

llm.register_function("my_tool", my_tool)

# After session.ready, send the tool schema:
await llm.set_tools([
    {
        "type": "function",
        "name": "my_tool",
        "description": "Does something useful",
        "parameters": {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "The input"}
            },
            "required": ["input"],
        },
    }
])
```

## Deploy to Pipecat Cloud

Requirements: Docker installed and running, Docker Hub account.

```bash
# 1. Install Pipecat Cloud CLI (already in pipecat-ai)
pip install pipecat-ai[cloud]

# 2. Log in
uv run pipecat cloud auth login

# 3. Edit pcc-deploy.toml — replace YOUR_DOCKERHUB_USERNAME with your Docker Hub username
#    image = "YOUR_DOCKERHUB_USERNAME/assemblyai-voice-agent:0.1"

# 4. Push your secrets
uv run pipecat cloud secrets set assemblyai-secrets --file .env

# 5. Build Docker image and push to Docker Hub
uv run pipecat cloud docker build-push

# 6. Deploy
uv run pipecat cloud deploy
```

Set `ASSEMBLYAI_API_KEY` and `ASSEMBLYAI_REALTIME_URL` in the Pipecat Cloud dashboard (or via the secrets step above).

For more information see [pipecat.daily.co](https://pipecat.daily.co).

## Deploy to Railway

Railway is a good option for running the bot as a persistent server (e.g. with a Twilio or WebSocket frontend).

```bash
npm i -g @railway/cli
railway login
railway init
railway up
# Set ASSEMBLYAI_API_KEY in Railway dashboard -> Variables
```

## Deploy to Render

Render works well for always-on Python services.

```bash
# Uses render.yaml in the deploy/ directory
# Push to GitHub, then connect repo at render.com -> New Web Service
# Build command: pip install -r requirements.txt
# Start command: uvicorn server:app --host 0.0.0.0 --port $PORT
# Or: render deploy (with Render CLI)
```

## Give Your Agent a Phone Number

Use `phone/server.py` to bridge Twilio calls to your Pipecat bot via AssemblyAI S2S.

### Step 1 — Deploy phone/server.py (needs a public HTTPS URL)

**Railway (recommended):**
```bash
cd phone/
railway login
railway init
railway up
# Note the Railway URL, e.g. https://my-phone-agent.up.railway.app
# Add env vars in Railway dashboard: ASSEMBLYAI_API_KEY, SERVER_URL (your Railway URL)
```

**Local dev with ngrok:**
```bash
cd phone/
pip install -r requirements.txt
uvicorn server:app --port 8080 --reload
# In another terminal:
ngrok http 8080
# Use the ngrok HTTPS URL as your webhook URL
```

### Step 2 — Buy a Twilio phone number

```bash
# Install Twilio CLI
brew install twilio
# Or: pip install twilio

twilio login

# Buy a US number with voice enabled
twilio phone-numbers:buy:local --country-code US --voice-enabled
# Note the number, e.g. +15551234567
```

Or buy at [console.twilio.com](https://console.twilio.com) -> Phone Numbers -> Buy a Number.

### Step 3 — Point the number at your server

```bash
twilio phone-numbers:update +15551234567 \
  --voice-url https://YOUR_SERVER_URL/incoming-call \
  --voice-method POST
```

Or in Twilio console: Phone Numbers -> Manage -> Active Numbers -> click the number -> Voice Configuration -> Webhook -> paste your URL.

### Step 4 — Call it

Call your Twilio number. You should hear the agent respond.

See `phone/README.md` for full details and troubleshooting.
