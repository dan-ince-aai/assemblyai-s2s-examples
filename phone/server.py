import os
import json
import base64
import audioop
import asyncio
import logging
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
import websockets
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

ASSEMBLYAI_API_KEY = os.environ.get("ASSEMBLYAI_API_KEY", "")
ASSEMBLYAI_REALTIME_URL = os.environ.get(
    "ASSEMBLYAI_REALTIME_URL",
    "wss://speech-to-speech.us.assemblyai.com/v1/realtime",
)
SERVER_URL = os.environ.get("SERVER_URL", "")

SYSTEM_PROMPT = (
    "You are a helpful voice assistant. You are speaking on a phone call. "
    "Keep your answers short and conversational. Speak clearly and naturally."
)

# Audio format constants
TWILIO_SAMPLE_RATE = 8000   # Twilio sends/receives mulaw at 8 kHz
ASSEMBLYAI_SAMPLE_RATE = 24000  # AssemblyAI S2S uses PCM16 at 24 kHz
SAMPLE_WIDTH = 2  # 16-bit = 2 bytes


def mulaw_to_pcm16_24k(mulaw_bytes: bytes) -> bytes:
    """Convert mulaw 8 kHz bytes to PCM16 24 kHz bytes."""
    # mulaw -> linear PCM16 at 8 kHz
    pcm_8k = audioop.ulaw2lin(mulaw_bytes, SAMPLE_WIDTH)
    # Resample 8 kHz -> 24 kHz (ratio 3:1)
    pcm_24k, _ = audioop.ratecv(
        pcm_8k, SAMPLE_WIDTH, 1, TWILIO_SAMPLE_RATE, ASSEMBLYAI_SAMPLE_RATE, None
    )
    return pcm_24k


def pcm16_24k_to_mulaw(pcm_24k_bytes: bytes) -> bytes:
    """Convert PCM16 24 kHz bytes to mulaw 8 kHz bytes."""
    # Resample 24 kHz -> 8 kHz
    pcm_8k, _ = audioop.ratecv(
        pcm_24k_bytes, SAMPLE_WIDTH, 1, ASSEMBLYAI_SAMPLE_RATE, TWILIO_SAMPLE_RATE, None
    )
    # linear PCM16 -> mulaw
    mulaw = audioop.lin2ulaw(pcm_8k, SAMPLE_WIDTH)
    return mulaw


@app.get("/")
async def health():
    return {"status": "ok"}


@app.post("/incoming-call")
async def incoming_call(request: Request):
    """Twilio webhook — responds with TwiML to connect the call to our media stream."""
    server_url = SERVER_URL.rstrip("/")
    # Convert https:// to wss:// for the stream URL
    ws_url = server_url.replace("https://", "wss://").replace("http://", "ws://")
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}/media-stream"/>
    </Connect>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


@app.websocket("/media-stream")
async def media_stream(twilio_ws: WebSocket):
    """WebSocket endpoint that bridges Twilio Media Streams <-> AssemblyAI S2S."""
    await twilio_ws.accept()
    logger.info("Twilio media stream connected")

    stream_sid = None
    aai_ws = None
    send_queue: asyncio.Queue = asyncio.Queue()

    async def connect_to_assemblyai():
        """Open the AssemblyAI S2S WebSocket and configure the session."""
        headers = {"Authorization": ASSEMBLYAI_API_KEY}
        ws = await websockets.connect(ASSEMBLYAI_REALTIME_URL, additional_headers=headers)
        logger.info("Connected to AssemblyAI S2S")

        # Configure the session
        await ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "system_prompt": SYSTEM_PROMPT,
            },
        }))
        return ws

    async def receive_from_twilio():
        """Read messages from Twilio and forward audio to AssemblyAI."""
        nonlocal stream_sid, aai_ws
        try:
            async for raw in twilio_ws.iter_text():
                msg = json.loads(raw)
                event = msg.get("event")

                if event == "start":
                    stream_sid = msg["start"]["streamSid"]
                    logger.info(f"Stream started: {stream_sid}")
                    # Connect to AssemblyAI once we know the stream is live
                    aai_ws = await connect_to_assemblyai()
                    asyncio.ensure_future(receive_from_assemblyai())

                elif event == "media" and aai_ws is not None:
                    # Twilio sends base64-encoded mulaw 8 kHz audio
                    mulaw_b64 = msg["media"]["payload"]
                    mulaw_bytes = base64.b64decode(mulaw_b64)
                    pcm_24k = mulaw_to_pcm16_24k(mulaw_bytes)
                    pcm_b64 = base64.b64encode(pcm_24k).decode("utf-8")

                    await aai_ws.send(json.dumps({
                        "type": "input.audio",
                        "audio": pcm_b64,
                    }))

                elif event == "stop":
                    logger.info("Twilio stream stopped")
                    break

        except Exception as e:
            logger.error(f"Error receiving from Twilio: {e}")
        finally:
            if aai_ws is not None:
                await aai_ws.close()

    async def receive_from_assemblyai():
        """Read events from AssemblyAI and forward audio back to Twilio."""
        nonlocal aai_ws
        try:
            async for raw in aai_ws:
                msg = json.loads(raw)
                event_type = msg.get("type")

                if event_type == "session.ready":
                    logger.info("AssemblyAI session ready")

                elif event_type == "reply.audio":
                    # AssemblyAI sends base64-encoded PCM16 24 kHz audio
                    pcm_b64 = msg.get("data", "")
                    if not pcm_b64:
                        continue
                    pcm_bytes = base64.b64decode(pcm_b64)
                    mulaw_bytes = pcm16_24k_to_mulaw(pcm_bytes)
                    mulaw_b64 = base64.b64encode(mulaw_bytes).decode("utf-8")

                    if stream_sid:
                        twilio_msg = json.dumps({
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {
                                "payload": mulaw_b64,
                            },
                        })
                        await twilio_ws.send_text(twilio_msg)

                elif event_type == "tool.call":
                    call_id = msg.get("call_id")
                    name = msg.get("name")
                    args = msg.get("arguments", {})
                    logger.info(f"Function call: {name}({args}) [call_id={call_id}]")
                    # Return a stub result — extend this to implement real tools
                    if aai_ws:
                        await aai_ws.send(json.dumps({
                            "type": "tool.result",
                            "call_id": call_id,
                            "result": f"Tool '{name}' is not implemented in the phone bridge.",
                        }))

                elif event_type == "session.error":
                    logger.error(f"AssemblyAI error: {msg.get('message')}")

                elif event_type in (
                    "transcript.user.delta",
                    "transcript.user",
                    "transcript.agent",
                    "reply.done",
                    "reply.started",
                    "reply.interrupted",
                    "input.speech.started",
                    "input.speech.stopped",
                ):
                    # Log but don't send to Twilio (audio only on phone)
                    if event_type in ("transcript.user", "transcript.agent"):
                        text = msg.get("text", "")
                        role = "User" if event_type == "transcript.user" else "Agent"
                        logger.info(f"[{role}] {text}")

        except websockets.exceptions.ConnectionClosed:
            logger.info("AssemblyAI WebSocket closed")
        except Exception as e:
            logger.error(f"Error receiving from AssemblyAI: {e}")

    await receive_from_twilio()
    logger.info("Media stream handler done")
