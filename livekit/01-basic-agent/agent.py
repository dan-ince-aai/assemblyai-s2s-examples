"""LiveKit Basic Agent — AssemblyAI Speech-to-Speech.

Minimal voice assistant using AssemblyAI's native S2S API via the
RealtimeModel plugin.

Required env vars:
  ASSEMBLYAI_API_KEY
  LIVEKIT_URL
  LIVEKIT_API_KEY
  LIVEKIT_API_SECRET

Run with:
  python agent.py dev
"""

import sys
import os

# Import plugin from parent directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugin'))

import logging

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    cli,
    room_io,
)
from livekit.plugins import noise_cancellation, silero

from assemblyai_realtime import RealtimeModel as AssemblyAIRealtimeModel

logger = logging.getLogger("agent")

load_dotenv(override=True)

PRODUCTION_URL = "wss://speech-to-speech.us.assemblyai.com/v1/realtime"


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="You are a helpful voice assistant. Keep responses brief and conversational.",
        )


server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session()
async def my_agent(ctx: JobContext):
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    api_url = os.environ.get("ASSEMBLYAI_REALTIME_URL", PRODUCTION_URL)
    api_key = os.environ.get("ASSEMBLYAI_API_KEY")

    if not api_key:
        raise ValueError("ASSEMBLYAI_API_KEY environment variable is required")

    logger.info(f"Connecting to AssemblyAI S2S at {api_url}")

    session = AgentSession(
        llm=AssemblyAIRealtimeModel(url=api_url, api_key=api_key)
    )

    @session.on("user_input_transcribed")
    def on_user_transcript(event):
        if event.is_final:
            print(f"\n[User] {event.transcript}")

    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: noise_cancellation.BVCTelephony()
                if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                else noise_cancellation.BVC(),
            ),
        ),
    )

    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(server)
