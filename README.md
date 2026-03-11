# AssemblyAI Speech-to-Speech Examples

> A collection of production-ready voice agent examples using AssemblyAI's native Speech-to-Speech API. Clone any example, add your API key, and go.

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/template/new?repository=https://github.com/dan-ince-aai/assemblyai-s2s-examples)


## Quick Start

| Example | Framework | Run locally | Deploy options |
|---|---|---|---|
| Basic agent | Pipecat | `cd pipecat/01-basic-agent && uv run bot.py` | [Pipecat Cloud](https://pipecat.daily.co) |
| Lead capture | Pipecat | `cd pipecat/02-lead-capture-agent && uv run bot.py` | [Pipecat Cloud](https://pipecat.daily.co) |
| Basic agent | LiveKit | `cd livekit/01-basic-agent && python agent.py dev` | [LiveKit Cloud](https://cloud.livekit.io) |
| Onboarding agent | LiveKit | `cd livekit/02-onboarding-agent && python agent.py dev` | [LiveKit Cloud](https://cloud.livekit.io) |
| Raw WebSocket (Python) | WebSocket | `cd websocket/python && python basic_client.py` | Any server |
| Raw WebSocket (Node) | WebSocket | `cd websocket/node && node client.js` | Any server |
| Tool calling | WebSocket | `cd tool-calling && python 01_basic_tools.py` | Any server |
| Phone agent | Twilio + FastAPI | `cd phone && uvicorn server:app --port 8080` | [Railway](https://railway.app) · [Fly.io](https://fly.io) · [Render](https://render.com) |
| Voice web app | Next.js | `cd nextjs-frontend && npm run dev` | [Railway](https://railway.app) · [Fly.io](https://fly.io) · [Render](https://render.com) |
| Browser SDK | Vanilla TS | `cd sdk && npm install && npm run build` | CDN / any host |
| WebSocket proxy | Node.js | `cd standalone-proxy && npm install && npm start` | [Railway](https://railway.app) · [Fly.io](https://fly.io) · Docker |

## Embed in Any App

Use the browser SDK and proxy to add a voice agent to any web app in minutes.

### 1. Deploy the proxy (holds your API key)

```bash
cd standalone-proxy
railway login && railway init && railway up
# Set ASSEMBLYAI_API_KEY in Railway dashboard
```

### 2. Add the SDK to your app

```bash
npm install @assemblyai/s2s-client
```

```typescript
import { AssemblyAIS2S } from '@assemblyai/s2s-client';

const agent = new AssemblyAIS2S({
  proxyUrl: 'wss://your-proxy.railway.app',
  onTranscript: (text) => console.log('User:', text),
  onAgentText: (text) => console.log('Agent:', text),
});

button.onclick = () => agent.start();
```

### Or: one-line embeddable widget

```html
<script src="https://cdn.jsdelivr.net/npm/@assemblyai/s2s-client/dist/widget.js"
        data-proxy="wss://your-proxy.railway.app">
</script>
```

See [sdk/README.md](sdk/README.md) and [standalone-proxy/README.md](standalone-proxy/README.md).

## Give Your Agent a Phone Number

Two paths depending on which example you're using:

### LiveKit — built-in phone numbers (no Twilio needed)

LiveKit Cloud lets you buy a real US phone number and route inbound calls directly to your deployed LiveKit agent:

1. Deploy your agent: `lk cloud auth && lk agent create`
2. In [cloud.livekit.io](https://cloud.livekit.io) → **Telephony** → **Phone Numbers** → Buy a number
3. Create a **Dispatch Rule** to route calls to your agent
4. Call the number — the agent answers

See [livekit/README.md](livekit/README.md) for full steps and [docs.livekit.io/sip](https://docs.livekit.io/sip) for LiveKit telephony docs.

### Twilio bridge (works with any example)

The `phone/` directory contains a FastAPI server that bridges Twilio phone calls to AssemblyAI S2S directly — works standalone without LiveKit or Pipecat.

```bash
# 1. Deploy to Railway (gets you a public HTTPS URL)
cd phone && railway login && railway init && railway up
# Set ASSEMBLYAI_API_KEY and SERVER_URL in the Railway dashboard

# 2. Buy a number via Twilio CLI
twilio login
twilio phone-numbers:buy:local --country-code US --voice-enabled

# 3. Point the number at your server
twilio phone-numbers:update +15551234567 \
  --voice-url https://YOUR_RAILWAY_URL/incoming-call \
  --voice-method POST

# 4. Call your number
```

See [phone/README.md](phone/README.md) for the full guide.

## Prerequisites

- AssemblyAI API key — get one at [assemblyai.com](https://assemblyai.com)
- Python 3.10+ with uv (`pip install uv`)
- Node.js 18+ (for Next.js and WebSocket/Node examples)

## What is AssemblyAI Speech-to-Speech?

AssemblyAI's Speech-to-Speech (S2S) API is a native real-time voice conversation endpoint. Unlike a pipeline of STT → LLM → TTS, the S2S API handles everything in a single WebSocket connection:

- **Built-in VAD** — server-side voice activity detection, no client configuration needed
- **Automatic turn detection** — the model decides when the user has finished speaking
- **Native audio output** — the model streams PCM16 audio back directly
- **Function calling** — register tools and handle `tool.call` / `tool.result` events
- **Low latency** — end-to-end voice-to-voice in a single hop

The protocol uses simple JSON events over WebSocket:

```
-> input.audio         { audio: <base64 PCM16 24kHz mono> }
-> session.update      { session: { system_prompt, tools } }
<- session.ready
<- transcript.user     { text }
<- reply.audio         { data: <base64 PCM16> }
<- transcript.agent    { text }
<- tool.call           { call_id, name, args }
-> tool.result         { call_id, result }
```

## Examples

### Pipecat

The `pipecat/` directory contains a plugin (`pipecat/plugin/`) and two example bots built with [Pipecat](https://pipecat.ai). See [pipecat/README.md](pipecat/README.md).

### LiveKit

The `livekit/` directory contains a plugin (`livekit/plugin/`) and two example agents built with [LiveKit Agents](https://agents.livekit.io). See [livekit/README.md](livekit/README.md).

### WebSocket

The `websocket/` directory has Python and Node.js terminal clients that connect directly to the S2S WebSocket without any framework. Good for understanding the raw protocol. See [websocket/README.md](websocket/README.md).

### Tool Calling

The `tool-calling/` directory has three standalone Python scripts demonstrating the function calling protocol in increasing complexity. See [tool-calling/README.md](tool-calling/README.md).

### Phone Agent

**LiveKit agents** get a phone number through [LiveKit's built-in telephony](https://docs.livekit.io/sip) — buy a US number directly in the LiveKit Cloud dashboard, no third-party SIP needed.

For **all other examples**, the `phone/` directory contains a Twilio bridge (FastAPI + WebSocket) that routes any inbound call to AssemblyAI S2S. See [phone/README.md](phone/README.md).

### Next.js Frontend

The `nextjs-frontend/` directory is a complete web app with a built-in WebSocket proxy. Deploy to Railway, Fly.io, or Render. See [nextjs-frontend/README.md](nextjs-frontend/README.md).

## Deployment

See [deploy/README.md](deploy/README.md) for options including Railway, Render, Pipecat Cloud, LiveKit Cloud, Fly.io, and Docker.

## License

MIT
