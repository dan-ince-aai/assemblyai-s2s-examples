"""AssemblyAI S2S WebSocket Client with Tool Calling (Python).

Extends basic_client.py by registering tools with the session and
handling function.call / function.result events.

Tools registered:
  - get_current_time: returns the current ISO timestamp
  - get_weather:      fetches weather from wttr.in for a given city

Usage:
  python agent_with_tools.py
  python agent_with_tools.py --url wss://... --api-key sk-...
"""

import argparse
import asyncio
import base64
import json
import os
import queue
import sys
import threading
from datetime import datetime, timezone

import aiohttp
import sounddevice as sd
import websockets
from dotenv import load_dotenv

load_dotenv()

SAMPLE_RATE = 24000
CHANNELS = 1
DTYPE = "int16"
CHUNK_FRAMES = 1024

GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"

TOOLS = [
    {
        "type": "function",
        "name": "get_current_time",
        "description": "Returns the current date and time in ISO 8601 format (UTC).",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "get_weather",
        "description": "Get current weather conditions for a city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "The city name, e.g. 'London' or 'New York'",
                }
            },
            "required": ["city"],
        },
    },
]

SYSTEM_PROMPT = (
    "You are a helpful assistant. "
    "You can tell the time using get_current_time and check the weather using get_weather."
)


def parse_args():
    parser = argparse.ArgumentParser(description="AssemblyAI S2S client with tools")
    parser.add_argument(
        "--url",
        default=os.getenv(
            "ASSEMBLYAI_REALTIME_URL",
            "wss://speech-to-speech.us.assemblyai.com/v1/realtime",
        ),
    )
    parser.add_argument("--api-key", default=os.getenv("ASSEMBLYAI_API_KEY", ""))
    return parser.parse_args()


# ── Tool implementations ──────────────────────────────────────────────────────

def tool_get_current_time(_args: dict) -> str:
    return datetime.now(timezone.utc).isoformat()


async def tool_get_weather(args: dict) -> str:
    city = args.get("city", "London")
    url = f"https://wttr.in/{city}?format=j1"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return f"Could not fetch weather for {city}"
                data = await resp.json()
                current = data["current_condition"][0]
                desc = current["weatherDesc"][0]["value"]
                temp_c = current["temp_C"]
                feels_c = current["FeelsLikeC"]
                humidity = current["humidity"]
                return (
                    f"{city}: {desc}, {temp_c}°C (feels like {feels_c}°C), "
                    f"humidity {humidity}%"
                )
    except Exception as e:
        return f"Weather lookup failed: {e}"


async def dispatch_tool(name: str, args: dict) -> str:
    if name == "get_current_time":
        return tool_get_current_time(args)
    elif name == "get_weather":
        return await tool_get_weather(args)
    return f"Unknown tool: {name}"


# ── Main ──────────────────────────────────────────────────────────────────────

async def run(url: str, api_key: str) -> None:
    mic_queue: queue.Queue[bytes] = queue.Queue()
    playback_queue: queue.Queue[bytes] = queue.Queue()
    stop_event = threading.Event()

    def mic_callback(indata, frames, time_info, status):
        if status:
            print(f"{YELLOW}Mic: {status}{RESET}", file=sys.stderr)
        mic_queue.put(bytes(indata))

    def mic_thread():
        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=CHUNK_FRAMES,
            callback=mic_callback,
        ):
            stop_event.wait()

    def playback_thread():
        with sd.RawOutputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
        ) as stream:
            while not stop_event.is_set() or not playback_queue.empty():
                try:
                    chunk = playback_queue.get(timeout=0.05)
                    stream.write(chunk)
                except queue.Empty:
                    continue

    headers = {"Authorization": f"Bearer {api_key}"}
    print(f"{BOLD}Connecting to AssemblyAI S2S with tools...{RESET}")

    try:
        async with websockets.connect(url, additional_headers=headers) as ws:
            print(f"{GREEN}Connected.{RESET}")

            t_mic = threading.Thread(target=mic_thread, daemon=True)
            t_play = threading.Thread(target=playback_thread, daemon=True)
            t_mic.start()
            t_play.start()

            async def send_audio():
                while True:
                    chunks = []
                    try:
                        while True:
                            chunks.append(mic_queue.get_nowait())
                    except queue.Empty:
                        pass
                    if chunks:
                        b64 = base64.b64encode(b"".join(chunks)).decode()
                        await ws.send(json.dumps({"type": "audio.append", "audio": b64}))
                    await asyncio.sleep(0.02)

            async def receive_events():
                async for raw in ws:
                    event = json.loads(raw)
                    t = event.get("type", "")

                    if t == "session.ready":
                        print(f"{GREEN}Session ready — configuring tools...{RESET}")
                        await ws.send(json.dumps({
                            "type": "session.configure",
                            "session": {
                                "system_prompt": SYSTEM_PROMPT,
                                "tools": TOOLS,
                            },
                        }))
                        print(f"{GREEN}Tools registered. Speak now.{RESET}")

                    elif t == "transcript.user.delta":
                        print(f"\r{YELLOW}[You] {event.get('text', '')}{RESET}", end="", flush=True)

                    elif t == "transcript.user":
                        print(f"\r{GREEN}[You] {event.get('text', '')}{RESET}")

                    elif t == "response.audio":
                        data = base64.b64decode(event.get("data", ""))
                        if data:
                            playback_queue.put(data)

                    elif t == "response.transcript":
                        text = event.get("text", "")
                        if text:
                            print(f"{BLUE}[Agent] {text}{RESET}")

                    elif t == "function.call":
                        call_id = event.get("call_id", "")
                        name = event.get("name", "")
                        args = event.get("args", {})
                        print(f"{CYAN}[Tool call] {name}({args}){RESET}")

                        result = await dispatch_tool(name, args)
                        print(f"{CYAN}[Tool result] {result}{RESET}")

                        await ws.send(json.dumps({
                            "type": "function.result",
                            "call_id": call_id,
                            "result": result,
                        }))

                    elif t == "error":
                        msg = event.get("message") or str(event)
                        print(f"{RED}[Error] {msg}{RESET}", file=sys.stderr)

            try:
                await asyncio.gather(send_audio(), receive_events())
            except websockets.exceptions.ConnectionClosed:
                print(f"\n{YELLOW}Connection closed.{RESET}")
            finally:
                stop_event.set()
                t_mic.join(timeout=2)
                t_play.join(timeout=2)

    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted.{RESET}")
    except Exception as e:
        print(f"{RED}Error: {e}{RESET}", file=sys.stderr)
        sys.exit(1)


def main():
    args = parse_args()
    if not args.api_key:
        print(f"{RED}Error: ASSEMBLYAI_API_KEY not set.{RESET}", file=sys.stderr)
        sys.exit(1)
    asyncio.run(run(args.url, args.api_key))


if __name__ == "__main__":
    main()
