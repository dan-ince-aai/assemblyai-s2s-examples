"""AssemblyAI S2S Tool Calling — Example 1: Basic Tools.

Demonstrates the function.call / function.result protocol with two simple tools:
  - get_current_time: returns the current ISO timestamp
  - flip_coin:        returns heads or tails

The script:
1. Connects to the AssemblyAI S2S WebSocket
2. On session.ready, sends session.configure with tools + system prompt
3. Streams microphone audio to the server
4. Handles function.call events and sends function.result back
5. Plays back the agent's audio response

Audio format: PCM16, 24 kHz, mono

Usage:
  python 01_basic_tools.py
"""

import asyncio
import base64
import json
import os
import queue
import random
import sys
import threading
from datetime import datetime, timezone

import sounddevice as sd
import websockets
from dotenv import load_dotenv

load_dotenv()

# ── Constants ─────────────────────────────────────────────────────────────────

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

# ── Tool definitions (sent in session.configure) ──────────────────────────────

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
        "name": "flip_coin",
        "description": "Flip a fair coin and return heads or tails.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

SYSTEM_PROMPT = (
    "You are a helpful assistant. "
    "You can tell the time using get_current_time and flip a coin using flip_coin."
)

# ── Tool implementations ──────────────────────────────────────────────────────

def handle_get_current_time(_args: dict) -> str:
    """Return the current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def handle_flip_coin(_args: dict) -> str:
    """Return 'heads' or 'tails' with equal probability."""
    return random.choice(["heads", "tails"])


def dispatch_tool(name: str, args: dict) -> str:
    """Dispatch a tool call to the appropriate handler."""
    if name == "get_current_time":
        return handle_get_current_time(args)
    elif name == "flip_coin":
        return handle_flip_coin(args)
    else:
        return f"Unknown tool: {name}"


# ── Main async loop ───────────────────────────────────────────────────────────

async def run() -> None:
    if not ASSEMBLYAI_API_KEY:
        print(f"{RED}Error: ASSEMBLYAI_API_KEY not set.{RESET}", file=sys.stderr)
        sys.exit(1)

    # Queues for inter-thread communication
    mic_queue: queue.Queue[bytes] = queue.Queue()
    playback_queue: queue.Queue[bytes] = queue.Queue()
    stop_event = threading.Event()

    # ── Mic capture thread ────────────────────────────────────────────────

    def mic_callback(indata, frames, time_info, status):
        """sounddevice callback — called from a background thread."""
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

    # ── Playback thread ───────────────────────────────────────────────────

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

    # ── WebSocket ─────────────────────────────────────────────────────────

    headers = {"Authorization": f"Bearer {ASSEMBLYAI_API_KEY}"}
    print(f"{BOLD}Connecting to {ASSEMBLYAI_URL}...{RESET}")

    try:
        async with websockets.connect(ASSEMBLYAI_URL, additional_headers=headers) as ws:
            print(f"{GREEN}Connected.{RESET}")

            # Start audio threads once connected
            t_mic = threading.Thread(target=mic_thread, daemon=True)
            t_play = threading.Thread(target=playback_thread, daemon=True)
            t_mic.start()
            t_play.start()

            async def send_audio():
                """Forward microphone audio to the server every 20 ms."""
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
                """Handle all server-sent events."""
                async for raw in ws:
                    event = json.loads(raw)
                    t = event.get("type", "")

                    if t == "session.ready":
                        # Configure tools and system prompt after session is ready
                        print(f"{GREEN}Session ready — registering tools...{RESET}")
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
                        # Decode and enqueue for playback
                        data = base64.b64decode(event.get("data", ""))
                        if data:
                            playback_queue.put(data)

                    elif t == "response.transcript":
                        text = event.get("text", "")
                        if text:
                            print(f"{BLUE}[Agent] {text}{RESET}")

                    elif t == "function.call":
                        # Handle tool call
                        call_id = event.get("call_id", "")
                        name = event.get("name", "")
                        args = event.get("args", {})

                        print(f"{CYAN}[Tool] {name}({args}){RESET}")
                        result = dispatch_tool(name, args)
                        print(f"{CYAN}[Result] {result}{RESET}")

                        # Send the result back so the agent can continue
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
