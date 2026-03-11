#
# Copyright (c) 2024-2026, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Pipecat Lead Capture Agent — AssemblyAI Speech-to-Speech.

Facebook Ads intake for a small business. The agent collects a caller's
name, callback number, and monthly budget, then saves the lead via a tool call.

Required env vars:
  ASSEMBLYAI_API_KEY
  ASSEMBLYAI_REALTIME_URL

Run the bot using::

    uv run bot.py
"""

import sys
import os

# Import plugin from parent directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'plugin'))

from dotenv import load_dotenv
from loguru import logger

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat_assemblyai_realtime import AssemblyAIRealtimeLLMService

load_dotenv(override=True)

SYSTEM_PROMPT = """
You are a friendly advertising consultant helping small business owners get
started with Facebook advertising. Collect the following from the caller,
one at a time:

1. Their full name
2. A phone number for a callback
3. Their monthly advertising budget

Once you have all three, call save_lead to record the information and let
them know a consultant will be in touch soon.
"""

TOOLS = [
    {
        "type": "function",
        "name": "save_lead",
        "description": "Save the caller's name, phone number, and monthly budget.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Customer's full name"},
                "phone": {"type": "string", "description": "Callback phone number"},
                "budget": {"type": "string", "description": "Monthly advertising budget"},
            },
            "required": ["name", "phone", "budget"],
        },
    }
]


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("Starting bot")

    llm = AssemblyAIRealtimeLLMService(
        url=os.getenv("ASSEMBLYAI_REALTIME_URL", "wss://speech-to-speech.us.assemblyai.com/v1/realtime"),
        api_key=os.getenv("ASSEMBLYAI_API_KEY", ""),
        system_prompt=SYSTEM_PROMPT,
    )

    async def save_lead(params: FunctionCallParams) -> None:
        args = params.arguments
        logger.info(f"Saving lead: {args}")
        await params.result_callback(
            f"Lead saved for {args.get('name')}. A consultant will call {args.get('phone')} shortly."
        )

    llm.register_function("save_lead", save_lead)

    pipeline = Pipeline(
        [
            transport.input(),
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
        logger.info("Client connected")
        await llm.set_tools(TOOLS)

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
