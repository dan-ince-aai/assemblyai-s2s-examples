# WebSocket Examples — AssemblyAI S2S Raw Protocol

These examples connect directly to the AssemblyAI S2S WebSocket without any framework layer. They are the best starting point for understanding the protocol and for building your own integration.

## Audio format

All audio must be:
- **Encoding**: PCM16 (signed 16-bit little-endian integers)
- **Sample rate**: 24,000 Hz
- **Channels**: 1 (mono)
- **Transport**: base64-encoded in JSON payloads

## Event reference

### Client → Server

| Event | Payload | Description |
|---|---|---|
| `input.audio` | `{ audio: <base64 PCM16> }` | Send a chunk of microphone audio |
| `session.update` | `{ session: { system_prompt?, tools? } }` | Configure the session (send after `session.ready`) |
| `reply.create` | `{}` | Manually trigger a response (only needed if VAD is disabled) |
| `reply.cancel` | `{ reply_id }` | Cancel an in-progress agent response |
| `tool.result` | `{ call_id, result }` | Return the result of a tool call |

### Server → Client

| Event | Payload | Description |
|---|---|---|
| `session.ready` | `{}` | Session is initialized — safe to send audio and configure tools |
| `input.speech.started` | `{}` | Server-side VAD detected speech start |
| `input.speech.stopped` | `{}` | Server-side VAD detected speech end |
| `transcript.user.delta` | `{ text }` | Partial user transcript (cumulative) |
| `transcript.user` | `{ text, item_id }` | Final user transcript |
| `reply.started` | `{ reply_id }` | Agent response began |
| `reply.audio` | `{ data: <base64 PCM16> }` | A chunk of agent audio |
| `transcript.agent` | `{ text }` | Full agent response transcript |
| `reply.done` | `{ reply_id }` | Agent response complete |
| `reply.interrupted` | `{}` | Agent response was interrupted by the user |
| `tool.call` | `{ call_id, name, args }` | The agent wants to call a tool |
| `session.error` | `{ message }` | An error occurred |

## Python Quick Start

```bash
cd websocket/python
pip install -r requirements.txt
cp ../.env.example .env
# Add ASSEMBLYAI_API_KEY to .env
python basic_client.py
```

With tools:
```bash
python agent_with_tools.py
```

## Node.js Quick Start

```bash
cd websocket/node
npm install
cp ../.env.example .env
# Add ASSEMBLYAI_API_KEY to .env
node client.js
```

## Tool Calling Protocol

1. After `session.ready`, send a `session.update` event with your tool definitions
2. When the agent decides to use a tool, you receive a `tool.call` event
3. Execute the tool and send a `tool.result` event with the `call_id` and result string
4. The agent continues its response incorporating the tool result

```json
// You receive:
{ "type": "tool.call", "call_id": "abc123", "name": "get_weather", "args": { "city": "London" } }

// You send:
{ "type": "tool.result", "call_id": "abc123", "result": "London: Cloudy, 12°C" }
```

See `../tool-calling/` for more detailed tool calling examples.
