"""Pipecat Basic Agent — AssemblyAI Speech-to-Speech.

Minimal voice assistant using AssemblyAIRealtimeLLMService in a 3-stage pipeline:
  transport.input → llm → transport.output

Required env vars:
  ASSEMBLYAI_API_KEY
  ASSEMBLYAI_REALTIME_URL

Run with:
  uv run bot.py
"""

import sys
import os

# Import plugin from parent directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugin'))

from dotenv import load_dotenv
from loguru import logger

from pipecat.frames.frames import TranscriptionFrame, InterimTranscriptionFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat_assemblyai_realtime import AssemblyAIRealtimeLLMService

load_dotenv(override=True)

SYSTEM_PROMPT = "You are a helpful voice assistant. Be concise and friendly."


class TranscriptLogger(FrameProcessor):
    """Log user and agent transcripts as they flow through the pipeline."""

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            logger.info(f"[User] {frame.text}")
        elif isinstance(frame, InterimTranscriptionFrame):
            logger.debug(f"[User partial] {frame.text}")
        await self.push_frame(frame, direction)


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("Starting basic AssemblyAI voice agent")

    llm = AssemblyAIRealtimeLLMService(
        url=os.getenv("ASSEMBLYAI_REALTIME_URL", "wss://speech-to-speech.us.assemblyai.com/v1/realtime"),
        api_key=os.getenv("ASSEMBLYAI_API_KEY", ""),
        system_prompt=SYSTEM_PROMPT,
    )

    transcript_logger = TranscriptLogger()

    pipeline = Pipeline(
        [
            transport.input(),
            transcript_logger,
            llm,
            transport.output(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected — voice session started")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point for the bot starter."""

    transport_params = {
        "daily": lambda: DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    }

    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
