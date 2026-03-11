# AssemblyAI Voice Agent — Next.js Frontend

A complete Next.js 15 web application for real-time voice conversations with AssemblyAI's Speech-to-Speech API. Dark-themed, mobile-friendly, and deployable to Vercel in one click.

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/github?repo=https://github.com/dan-ince-aai/assemblyai-s2s-examples)

## What it does

- Click the microphone button to start a voice conversation
- Streams your microphone audio to AssemblyAI's S2S API via WebSocket
- Plays back the agent's audio response through the Web Audio API
- Shows live user transcript and agent response text
- Animated status indicator (idle / connecting / listening / speaking)
- Canvas-based audio visualizer that shows mic activity

## Local Development

```bash
cd nextjs-frontend
npm install

cp .env.local.example .env.local
# Edit .env.local and add NEXT_PUBLIC_ASSEMBLYAI_API_KEY

npm run dev
# Open http://localhost:3000
```

## Deploy

### Railway (recommended)

The app uses a custom Node.js server (`server.ts`) to proxy WebSocket connections to AssemblyAI with the `Authorization: Bearer` header — browsers can't send this header directly. Vercel's serverless platform doesn't support long-lived WebSocket connections, so **Railway is the recommended deploy target**.

```bash
npm i -g @railway/cli
railway login
cd nextjs-frontend
railway init
railway up
# Set ASSEMBLYAI_API_KEY in Railway dashboard → Variables
```

### Fly.io

```bash
brew install flyctl
fly auth login
cd nextjs-frontend
fly launch   # uses fly.toml — skip config prompts
fly secrets set ASSEMBLYAI_API_KEY=your_key_here
fly deploy
```

### Render

Push to GitHub, connect at render.com → New Web Service.
- Build command: `npm install && npm run build`
- Start command: `npm start`
- Add `ASSEMBLYAI_API_KEY` in the Environment section.

### Local dev

```bash
cp .env.local.example .env.local
# Add your ASSEMBLYAI_API_KEY
npm install
npm run dev
# Open http://localhost:3000
```

### Why not Vercel?

Vercel serverless functions time out after 30 seconds and don't support WebSocket upgrade connections. The app works on any platform that runs a persistent Node.js server (Railway, Render, Fly.io, EC2, etc.).

## Architecture — Audio Flow

```
Browser Mic
    |
getUserMedia() -> MediaStream
    |
AudioContext (sampleRate: 24000)
    |
createMediaStreamSource()
    |
ScriptProcessorNode (4096 frames)
    |   onaudioprocess:
    |     Float32Array -> Int16Array (PCM16)
    |     Int16Array -> base64
    |
WebSocket.send({ type: "input.audio", audio: base64 })
    |
AssemblyAI S2S API
    |
reply.audio: { data: base64 PCM16 }
    |
base64 -> Int16Array -> Float32Array
    |
AudioContext.createBuffer() -> createBufferSource().start()
    |
Browser Speaker
```

## Security Note

`NEXT_PUBLIC_ASSEMBLYAI_API_KEY` is a public env var — it is embedded in the client-side JavaScript bundle and visible to anyone who inspects network requests. This is fine for demos and personal projects.

For production, proxy WebSocket connections through a backend:

1. Create an API route (`/api/ws-token`) that issues short-lived tokens
2. Have the client connect to your backend, which forwards audio to AssemblyAI
3. Keep `ASSEMBLYAI_API_KEY` server-side only

## File Structure

```
nextjs-frontend/
  app/
    layout.tsx           # Root layout with Inter font
    page.tsx             # Home page — renders VoiceAgent
    globals.css          # Tailwind + CSS variables
  components/
    VoiceAgent.tsx       # Main UI component
    AudioVisualizer.tsx  # Canvas waveform visualizer
  hooks/
    useAssemblyAISession.ts  # WebSocket + Web Audio logic
```
