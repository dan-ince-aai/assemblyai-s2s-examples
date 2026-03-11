# AssemblyAI S2S Proxy

A minimal WebSocket proxy for the AssemblyAI Speech-to-Speech API. Deploy this server, then use the browser SDK (`../sdk/`) to connect from any web app — your API key stays server-side.

## Deploy in 3 commands

**Railway:**
```bash
railway login && railway init && railway up
# Set ASSEMBLYAI_API_KEY in Railway dashboard → Variables
```

**Fly.io:**
```bash
fly auth login && fly launch && fly secrets set ASSEMBLYAI_API_KEY=your_key
fly deploy
```

**Local:**
```bash
cp .env.example .env  # add your key
npm install && npm start
# Proxy running at ws://localhost:8080
```

## Use with the browser SDK

```typescript
import { AssemblyAIS2S } from '@assemblyai/s2s-client';

const agent = new AssemblyAIS2S({ proxyUrl: 'wss://your-proxy.railway.app' });
await agent.start();
```

## Restrict allowed origins (optional)

Set `ALLOWED_ORIGINS` in your environment to only allow connections from specific domains:

```
ALLOWED_ORIGINS=https://myapp.com,https://staging.myapp.com
```

Leave unset to allow all origins (fine for development).

## How it works

```
Browser ──── ws:// ──── Proxy ──── wss://speech-to-speech.us.assemblyai.com
(no key)                (adds Authorization: Bearer)
```

## Endpoints

- `GET /` — health check, returns `{"status":"ok","connections":N}`
- `WS /` — WebSocket upgrade, proxied to AssemblyAI
