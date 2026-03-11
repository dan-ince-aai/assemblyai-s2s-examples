# Tool Calling — AssemblyAI S2S

These examples demonstrate the function calling protocol in the AssemblyAI S2S API, from simple synchronous tools to async HTTP calls and stateful multi-turn agents.

## How tool calling works

The tool calling cycle has three steps:

**1. Register tools in `session.update`**

Send a `session.update` event after `session.ready` with a list of tool definitions in OpenAI function-calling format:

```json
{
  "type": "session.update",
  "session": {
    "system_prompt": "You are a helpful assistant.",
    "tools": [
      {
        "type": "function",
        "name": "get_weather",
        "description": "Get weather for a city",
        "parameters": {
          "type": "object",
          "properties": {
            "city": { "type": "string", "description": "City name" }
          },
          "required": ["city"]
        }
      }
    ]
  }
}
```

**2. Handle `tool.call`**

When the agent decides to call a tool, you receive:

```json
{ "type": "tool.call", "call_id": "abc123", "name": "get_weather", "args": { "city": "London" } }
```

**3. Send `tool.result`**

Execute the tool and send the result back. The agent will incorporate it into its response:

```json
{ "type": "tool.result", "call_id": "abc123", "result": "London: Cloudy, 12°C" }
```

## Examples

### 01_basic_tools.py — Simple synchronous tools

Two tools with no external dependencies:
- `get_current_time` — returns the current UTC timestamp
- `flip_coin` — returns heads or tails

Best starting point for understanding the protocol.

```bash
python 01_basic_tools.py
```

### 02_weather_agent.py — Async HTTP tool

Single tool that makes an async HTTP request to [wttr.in](https://wttr.in):
- `get_weather` — fetches live weather for any city

Demonstrates how to `await` an HTTP call inside the tool handler while keeping the WebSocket receive loop running.

```bash
python 02_weather_agent.py
```

### 03_multi_tool_agent.py — Multi-tool stateful agent

Four tools demonstrating multi-turn usage and in-memory state:
- `calculate` — safely evaluate a math expression
- `take_note` — save a note to memory
- `get_notes` — retrieve all saved notes
- `get_current_time` — current UTC timestamp

Try asking: "What is 2 to the power of 16?", "Remember that I need milk", "What have I asked you to remember?"

```bash
python 03_multi_tool_agent.py
```

## Setup

```bash
cd tool-calling
pip install -r requirements.txt
cp .env.example .env
# Add ASSEMBLYAI_API_KEY
```
