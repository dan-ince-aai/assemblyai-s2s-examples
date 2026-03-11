"""AssemblyAI S2S Tool Calling — Example 2: Weather Agent.

Demonstrates async HTTP calls inside a tool handler using the wttr.in API.

Tool:
  - get_weather: fetches current weather conditions for a given city

The session.configure / function.call / function.result cycle is the same
as in 01_basic_tools.py — the key difference is the tool handler makes
an async HTTP request before returning the result.

Usage:
  python 02_weather_agent.py
"""

import asyncio
import base64
import json
import os
import queue
import sys
import threading

import aiohttp
import sounddevice as sd
import websockets
from dotenv import load_dotenv

load_dotenv()

SAMPLE_RATE = 24000
CHANNELS = 1
DTYPE = "int16"
CHUNK_FRAMES = 1024

ASSEMBLYAI_URL = os.getenv(
    "ASSEMBLYAI_REALTIME_URL",
    "wss://speech-to-speech.us.assemblyai.com/v1/realtime",
)
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY", "")

GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

TOOLS = [
    {
        "type": "function",
        "name": "get_weather",
        "description": "Get current weather conditions for any city in the world.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "The city name, e.g. 'London', 'Tokyo', or 'New York'",
                }
            },
            "required": ["city"],
        },
    }
]

SYSTEM_PROMPT = (
    "You are a weather assistant. "
    "Use the get_weather tool to look up weather for any city. "
    "Describe the weather in a friendly, conversational way."
)


# ── Tool implementation ───────────────────────────────────────────────────────

async def get_weather(city: str) -> str:
    """Fetch current weather from wttr.in JSON API."""
    url = f"https://wttr.in/{city}?format=j1"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    return f"Could not fetch weather for {city} (HTTP {resp.status})"
                data = await resp.json(content_type=None)

        current = data["current_condition"][0]
        desc = current["weatherDesc"][0]["value"]
        temp_c = current["temp_C"]
        temp_f = current["temp_F"]
        feels_c = current["FeelsLikeC"]
        humidity = current["humidity"]
        wind_kmph = current["windspeedKmph"]
        wind_dir = current["winddir16Point"]

        return (
            f"{city}: {desc}. "
            f"Temperature {temp_c}°C ({temp_f}°F), feels like {feels_c}°C. "
            f"Humidity {humidity}%, wind {wind_kmph} km/h {wind_dir}."
        )
    except aiohttp.ClientError as e:
        return f"Network error fetching weather: {e}"
    except (KeyError, IndexError, ValueError) as e:
        return f"Could not parse weather data for {city}: {e}"


# ── Main ──────────────────────────────────────────────────────────────────────

async def run() -> None:
    if not ASSEMBLYAI_API_KEY:
        print(f"{RED}Error: ASSEMBLYAI_API_KEY not set.{RESET}", file=sys.stderr)
        sys.exit(1)

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

    headers = {"Authorization": f"Bearer {ASSEMBLYAI_API_KEY}"}
    print(f"{BOLD}Weather Agent — connecting...{RESET}")

    try:
        async with websockets.connect(ASSEMBLYAI_URL, additional_headers=headers) as ws:
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
                        print(f"{GREEN}Session ready — registering weather tool...{RESET}")
                        await ws.send(json.dumps({
                            "type": "session.configure",
                            "session": {
                                "system_prompt": SYSTEM_PROMPT,
                                "tools": TOOLS,
                            },
                        }))
                        print(f"{GREEN}Ready. Ask about the weather anywhere.{RESET}")

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
                        # This is where the async HTTP call happens
                        call_id = event.get("call_id", "")
                        name = event.get("name", "")
                        args = event.get("args", {})
                        city = args.get("city", "London") if isinstance(args, dict) else "London"

                        print(f"{CYAN}[Tool] get_weather(city={city!r}){RESET}")
                        result = await get_weather(city)
                        print(f"{CYAN}[Result] {result}{RESET}")

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


if __name__ == "__main__":
    asyncio.run(run())
