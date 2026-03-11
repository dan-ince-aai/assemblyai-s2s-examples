"""AssemblyAI S2S Basic WebSocket Client (Python).

Connect microphone to AssemblyAI Speech-to-Speech API and play back
the agent's audio response in real time.

Audio format: PCM16, 24kHz, mono

Usage:
  python basic_client.py
  python basic_client.py --url wss://... --api-key sk-...
"""

import argparse
import asyncio
import base64
import json
import os
import queue
import sys
import threading

import sounddevice as sd
import websockets
from dotenv import load_dotenv

load_dotenv()

SAMPLE_RATE = 24000
CHANNELS = 1
DTYPE = "int16"
CHUNK_FRAMES = 1024  # frames per mic callback

# ANSI colors for terminal output
GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"


def parse_args():
    parser = argparse.ArgumentParser(description="AssemblyAI S2S terminal client")
    parser.add_argument(
        "--url",
        default=os.getenv(
            "ASSEMBLYAI_REALTIME_URL",
            "wss://speech-to-speech.us.assemblyai.com/v1/realtime",
        ),
        help="AssemblyAI S2S WebSocket URL",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("ASSEMBLYAI_API_KEY", ""),
        help="AssemblyAI API key",
    )
    return parser.parse_args()


async def run(url: str, api_key: str) -> None:
    # Queue to hold audio chunks captured from the microphone
    mic_queue: queue.Queue[bytes] = queue.Queue()
    # Queue to hold decoded PCM audio from the agent
    playback_queue: queue.Queue[bytes] = queue.Queue()

    stop_event = threading.Event()

    # ── Microphone capture thread ─────────────────────────────────────────

    def mic_callback(indata, frames, time_info, status):
        """Called by sounddevice for each audio chunk from the mic."""
        if status:
            print(f"{YELLOW}Mic status: {status}{RESET}", file=sys.stderr)
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

    # ── Speaker playback thread ───────────────────────────────────────────

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

    # ── Main WebSocket loop ───────────────────────────────────────────────

    headers = {"Authorization": f"Bearer {api_key}"}

    print(f"{BOLD}Connecting to AssemblyAI S2S...{RESET}")

    try:
        async with websockets.connect(url, additional_headers=headers) as ws:
            print(f"{GREEN}Connected.{RESET} Speak into your microphone.")

            # Start audio threads
            t_mic = threading.Thread(target=mic_thread, daemon=True)
            t_play = threading.Thread(target=playback_thread, daemon=True)
            t_mic.start()
            t_play.start()

            async def send_audio():
                """Drain mic_queue and forward base64-encoded audio to the server."""
                while True:
                    # Drain whatever is buffered
                    chunks = []
                    try:
                        while True:
                            chunks.append(mic_queue.get_nowait())
                    except queue.Empty:
                        pass

                    if chunks:
                        combined = b"".join(chunks)
                        b64 = base64.b64encode(combined).decode()
                        await ws.send(json.dumps({"type": "input.audio", "audio": b64}))

                    await asyncio.sleep(0.02)  # 20 ms send cadence

            async def receive_events():
                """Handle server events."""
                async for raw in ws:
                    event = json.loads(raw)
                    t = event.get("type", "")

                    if t == "session.ready":
                        print(f"{GREEN}Session ready — you can speak now.{RESET}")

                    elif t == "input.speech.started":
                        print(f"\n{YELLOW}[listening...]{RESET}", end="", flush=True)

                    elif t == "transcript.user.delta":
                        text = event.get("text", "")
                        print(f"\r{YELLOW}[You] {text}{RESET}", end="", flush=True)

                    elif t == "transcript.user":
                        text = event.get("text", "")
                        print(f"\r{GREEN}[You] {text}{RESET}")

                    elif t == "reply.started":
                        print(f"{BLUE}[Agent speaking...]{RESET}")

                    elif t == "reply.audio":
                        data = base64.b64decode(event.get("data", ""))
                        if data:
                            playback_queue.put(data)

                    elif t == "transcript.agent":
                        text = event.get("text", "")
                        if text:
                            print(f"{BLUE}[Agent] {text}{RESET}")

                    elif t == "reply.done":
                        print(f"{BLUE}[Agent done]{RESET}")

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
        print(f"\n{YELLOW}Interrupted by user.{RESET}")
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
