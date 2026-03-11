"""AssemblyAI S2S Tool Calling — Example 3: Multi-Tool Stateful Agent.

A personal assistant with four tools demonstrating multi-turn tool usage
and in-memory per-session state.

Tools:
  - calculate:      safely evaluate a math expression
  - take_note:      add a note to the in-memory list
  - get_notes:      return all saved notes
  - get_current_time: return the current UTC time

State is stored in a module-level dict keyed by session ID, though for
this standalone script there is effectively one session per process run.

Usage:
  python 03_multi_tool_agent.py
"""

import asyncio
import base64
import json
import math
import operator
import os
import queue
import sys
import threading
from datetime import datetime, timezone

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
MAGENTA = "\033[95m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "name": "calculate",
        "description": (
            "Evaluate a mathematical expression and return the numeric result. "
            "Supports standard arithmetic operators, parentheses, and common math "
            "functions like sqrt, sin, cos, log, abs, round, pow."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "The math expression to evaluate, e.g. '2 ** 10 + sqrt(144)'",
                }
            },
            "required": ["expression"],
        },
    },
    {
        "type": "function",
        "name": "take_note",
        "description": "Save a note to the in-memory notes list.",
        "parameters": {
            "type": "object",
            "properties": {
                "note": {
                    "type": "string",
                    "description": "The note text to save.",
                }
            },
            "required": ["note"],
        },
    },
    {
        "type": "function",
        "name": "get_notes",
        "description": "Return all saved notes as a numbered list.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
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
]

SYSTEM_PROMPT = (
    "You are a personal assistant. "
    "You can do math using calculate, take notes using take_note, "
    "retrieve saved notes with get_notes, and tell the time with get_current_time. "
    "When the user asks you to remember something, always use take_note. "
    "When they ask what you have noted, always use get_notes."
)

# ── Session state ─────────────────────────────────────────────────────────────

# A simple module-level notes store (resets each run)
_notes: list[str] = []


# ── Sandboxed math evaluator ──────────────────────────────────────────────────

# Whitelist of safe names for eval
_SAFE_NAMES = {
    k: getattr(math, k)
    for k in dir(math)
    if not k.startswith("_")
}
_SAFE_NAMES.update({
    "abs": abs,
    "round": round,
    "pow": pow,
    "min": min,
    "max": max,
    "sum": sum,
})
_SAFE_BUILTINS = {"__builtins__": {}}


def safe_eval(expression: str) -> str:
    """Evaluate a math expression in a restricted namespace."""
    try:
        # Only allow alphanumerics, operators, whitespace, parentheses, dots
        import re
        if re.search(r"[^\w\s\+\-\*\/\%\(\)\.\,\*\*]", expression):
            return f"Unsafe characters in expression: {expression}"
        result = eval(expression, _SAFE_BUILTINS, _SAFE_NAMES)  # noqa: S307
        return str(result)
    except ZeroDivisionError:
        return "Error: division by zero"
    except Exception as e:
        return f"Error evaluating expression: {e}"


# ── Tool dispatch ─────────────────────────────────────────────────────────────

def dispatch_tool(name: str, args: dict) -> str:
    if name == "calculate":
        expr = args.get("expression", "")
        result = safe_eval(expr)
        return result

    elif name == "take_note":
        note = args.get("note", "").strip()
        if not note:
            return "Note is empty — nothing saved."
        _notes.append(note)
        return f"Note saved. You now have {len(_notes)} note(s)."

    elif name == "get_notes":
        if not _notes:
            return "No notes saved yet."
        numbered = "\n".join(f"{i + 1}. {n}" for i, n in enumerate(_notes))
        return f"Your notes:\n{numbered}"

    elif name == "get_current_time":
        return datetime.now(timezone.utc).isoformat()

    return f"Unknown tool: {name}"


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
    print(f"{BOLD}Personal Assistant — connecting...{RESET}")
    print(f"{YELLOW}Tools: calculate, take_note, get_notes, get_current_time{RESET}")

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
                        await ws.send(json.dumps({"type": "input.audio", "audio": b64}))
                    await asyncio.sleep(0.02)

            async def receive_events():
                async for raw in ws:
                    event = json.loads(raw)
                    t = event.get("type", "")

                    if t == "session.ready":
                        print(f"{GREEN}Session ready — registering tools...{RESET}")
                        await ws.send(json.dumps({
                            "type": "session.update",
                            "session": {
                                "system_prompt": SYSTEM_PROMPT,
                                "tools": TOOLS,
                            },
                        }))
                        print(f"{GREEN}Ready. Try: 'What is 2 to the power of 16?'{RESET}")
                        print(f"{GREEN}Or: 'Remember that I need milk.'{RESET}")

                    elif t == "transcript.user.delta":
                        print(f"\r{YELLOW}[You] {event.get('text', '')}{RESET}", end="", flush=True)

                    elif t == "transcript.user":
                        print(f"\r{GREEN}[You] {event.get('text', '')}{RESET}")

                    elif t == "reply.audio":
                        data = base64.b64decode(event.get("data", ""))
                        if data:
                            playback_queue.put(data)

                    elif t == "transcript.agent":
                        text = event.get("text", "")
                        if text:
                            print(f"{BLUE}[Agent] {text}{RESET}")

                    elif t == "tool.call":
                        call_id = event.get("call_id", "")
                        name = event.get("name", "")
                        args = event.get("args", {})

                        print(f"{CYAN}[Tool] {name}({args}){RESET}")
                        result = dispatch_tool(name, args)
                        print(f"{CYAN}[Result] {result}{RESET}")

                        await ws.send(json.dumps({
                            "type": "tool.result",
                            "call_id": call_id,
                            "result": result,
                        }))

                    elif t == "session.error":
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
