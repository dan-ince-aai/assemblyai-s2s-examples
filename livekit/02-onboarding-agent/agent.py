"""LiveKit Onboarding Agent — AssemblyAI Speech-to-Speech.

DeliveryHero onboarding buddy. Helps new riders before their first shift
through a natural, scenario-based conversation.

Required env vars:
  ASSEMBLYAI_API_KEY
  ASSEMBLYAI_REALTIME_URL (optional, defaults to production)
  LIVEKIT_URL
  LIVEKIT_API_KEY
  LIVEKIT_API_SECRET

Run with:
  python agent.py dev
"""

import sys
import os

# Import plugin from parent directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'plugin'))

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
            instructions="""
You are a friendly onboarding buddy for DeliveryHero helping a new rider before their first shift. Have a natural back-and-forth conversation — like a colleague over the phone, not a trainer giving a lecture.

Rules:
- Never say more than 2-3 sentences at a time
- Always end your turn with either a question or waiting for the rider to respond
- Don't explain everything upfront — let understanding emerge through the conversation
- If they ask something, answer it briefly then hand it back to them

Work through these topics by asking scenario questions, not explaining procedures:
1. Restaurant pickup
2. Customer not home
3. Can't complete a delivery
4. How ratings work

Start by introducing yourself briefly and asking if they're ready to run through a few quick scenarios.
""",
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
