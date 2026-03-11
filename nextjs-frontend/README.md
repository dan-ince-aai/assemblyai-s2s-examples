# AssemblyAI Voice Agent — Next.js Frontend

A complete Next.js 15 web application for real-time voice conversations with AssemblyAI's Speech-to-Speech API. Dark-themed, mobile-friendly, and deployable to Vercel in one click.

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/dan-ince-aai/assemblyai-s2s-examples&root-directory=nextjs-frontend&env=NEXT_PUBLIC_ASSEMBLYAI_API_KEY&project-name=assemblyai-voice-agent)

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

## Deploy to Vercel

### One-click deploy

Click the button above — you'll only be asked for your `NEXT_PUBLIC_ASSEMBLYAI_API_KEY`. The API URL defaults to the US region automatically.

### CLI deploy

```bash
# Install Vercel CLI
npm i -g vercel

# Login
vercel login

# Deploy to production
vercel --prod
```

The only environment variable you need is `NEXT_PUBLIC_ASSEMBLYAI_API_KEY`. Set it in the Vercel dashboard under Settings → Environment Variables, or when prompted by the CLI.

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
WebSocket.send({ type: "audio.append", audio: base64 })
    |
AssemblyAI S2S API
    |
response.audio: { data: base64 PCM16 }
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
