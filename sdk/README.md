# @assemblyai/s2s-client

Tiny browser SDK for AssemblyAI's Speech-to-Speech API. Zero runtime dependencies.

## Setup

You need a proxy server so your API key stays server-side. Deploy `standalone-proxy/` in 3 commands:

```bash
cd standalone-proxy
railway login && railway init && railway up
# Set ASSEMBLYAI_API_KEY in Railway → Variables
```

Then use the SDK to connect from any browser app — no API key on the client.

## Install

**From GitHub (recommended):**
```bash
npm install "github:dan-ince-aai/assemblyai-s2s-examples#path:sdk"
```

**CDN / script tag — no install needed:**
```html
<script type="module">
  import { AssemblyAIS2S } from 'https://cdn.jsdelivr.net/gh/dan-ince-aai/assemblyai-s2s-examples@main/sdk/dist/index.js';
</script>
```

## Quick start

```typescript
import { AssemblyAIS2S } from '@assemblyai/s2s-client';

const agent = new AssemblyAIS2S({
  proxyUrl: 'wss://your-proxy.railway.app',
  systemPrompt: 'You are a helpful assistant.',
  onTranscript: (text) => console.log('User:', text),
  onAgentText:  (text) => console.log('Agent:', text),
});

document.getElementById('btn').onclick = () => agent.start();
```

## Embeddable widget

Drop one line into any page — a floating mic button appears bottom-right:

```html
<script src="https://cdn.jsdelivr.net/gh/dan-ince-aai/assemblyai-s2s-examples@main/sdk/dist/widget.js"
        data-proxy="wss://your-proxy.railway.app"
        data-prompt="You are a helpful assistant.">
</script>
```

Optional attributes:
- `data-prompt` — system prompt for the agent
- `data-position` — `bottom-right` (default) or `bottom-left`

## Tool calling

```typescript
const agent = new AssemblyAIS2S({
  proxyUrl: 'wss://your-proxy.railway.app',
  tools: [{
    type: 'function',
    name: 'get_weather',
    description: 'Get weather for a city',
    parameters: {
      type: 'object',
      properties: { city: { type: 'string' } },
      required: ['city'],
    },
  }],
});

agent.addEventListener('toolcall', async (e) => {
  const { callId, name, args } = e.detail;
  if (name === 'get_weather') {
    const result = await fetchWeather(args.city);
    agent.sendToolResult(callId, result);
  }
});
```

## API

### `new AssemblyAIS2S(options)`

| Option | Type | Description |
|---|---|---|
| `proxyUrl` | `string` | WebSocket URL of your proxy — use `/ws` for same-origin |
| `systemPrompt` | `string?` | System prompt sent on connect |
| `tools` | `object[]?` | Tool schemas to register |
| `onStateChange` | `(state) => void` | `idle` \| `connecting` \| `listening` \| `speaking` |
| `onTranscript` | `(text, isFinal) => void` | Live user transcript |
| `onAgentText` | `(text) => void` | Agent response text |
| `onError` | `(error) => void` | Error handler |

### Methods
- `agent.start()` — request mic permission and begin session
- `agent.stop()` — end session cleanly
- `agent.sendToolResult(callId, result)` — respond to a `toolcall` event
- `agent.state` — current `AgentState`

### Events
- `statechange` — `CustomEvent<AgentState>`
- `transcript` — `CustomEvent<{text: string, isFinal: boolean}>`
- `agenttext` — `CustomEvent<{text: string}>`
- `toolcall` — `CustomEvent<{callId: string, name: string, args: object}>`
- `error` — `CustomEvent<Error>`

## Build from source

```bash
cd sdk
npm install
npm run build   # outputs to dist/
```
