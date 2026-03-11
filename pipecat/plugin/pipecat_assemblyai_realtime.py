"""AssemblyAI Native Speech-to-Speech Plugin for PipeCat.

Implements LLMService using AssemblyAI's native S2S WebSocket protocol.
The protocol is distinct from the OpenAI-compatible endpoint — it uses
event types like session.configure, audio.append, response.started, etc.

Protocol summary (→ = client sends, ← = server sends):
  → audio.append          { audio: <base64 PCM> }
  → session.configure     { session: { system_prompt, tools, ... } }
  → response.create       (trigger a response manually)
  → response.cancel       { response_id }
  → function.result       { call_id, result }
  ← session.ready
  ← speech.started / speech.stopped
  ← transcript.user.delta { text } / transcript.user { text, item_id }
  ← response.started      { response_id }
  ← response.audio        { data: <base64 PCM> }
  ← response.transcript   { text }  (full agent turn transcript)
  ← response.done / response.interrupted
  ← function.call         { call_id, name, args }
  ← error                 { message }
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone

import websockets
import websockets.asyncio.client

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    CancelFrame,
    EndFrame,
    ErrorFrame,
    Frame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    LLMContextFrame,
    StartFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.llm_service import LLMService

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24000
NUM_CHANNELS = 1


class AssemblyAIRealtimeLLMService(LLMService):
    """PipeCat LLM service for AssemblyAI's native speech-to-speech API.

    Usage::

        service = AssemblyAIRealtimeLLMService(
            url="ws://localhost:8777/v1/realtime",  # or production URL
            api_key="your-key",
            system_prompt="You are a helpful assistant.",
        )
    """

    def __init__(
        self,
        *,
        url: str,
        api_key: str,
        system_prompt: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._url = url
        self._api_key = api_key
        self._system_prompt = system_prompt

        self._websocket: websockets.asyncio.client.ClientConnection | None = None
        self._receive_task: asyncio.Task | None = None
        self._session_ready = False
        self._current_response_id: str | None = None
        self._bot_speaking = False

        # Accumulates delta text so we can emit correct interim frames
        self._user_transcript_buf: str = ""

        # Tools queued before session.ready fires
        self._pending_tools: list[dict] = []

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)
        await self._connect()

    async def stop(self, frame: EndFrame) -> None:
        await super().stop(frame)
        await self._disconnect()

    async def cancel(self, frame: CancelFrame) -> None:
        await super().cancel(frame)
        await self._disconnect()

    # ── WebSocket ─────────────────────────────────────────────────────────────

    async def _connect(self) -> None:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            self._websocket = await websockets.asyncio.client.connect(
                self._url,
                additional_headers=headers,
            )
            self._receive_task = asyncio.create_task(
                self._receive_task_handler(),
                name="AssemblyAIRealtime._recv",
            )
            logger.info(f"Connected to AssemblyAI S2S at {self._url}")
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            await self.push_frame(ErrorFrame(str(e)))

    async def _disconnect(self) -> None:
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except (asyncio.CancelledError, Exception):
                pass
            self._receive_task = None
        if self._websocket:
            await self._websocket.close()
            self._websocket = None
        self._session_ready = False
        self._bot_speaking = False
        self._current_response_id = None

    async def _send(self, msg: dict) -> None:
        if self._websocket:
            try:
                await self._websocket.send(json.dumps(msg))
            except Exception as e:
                logger.error(f"WebSocket send error: {e}")
                await self.push_frame(ErrorFrame(str(e)))

    # ── Frame Processing ──────────────────────────────────────────────────────

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, InputAudioRawFrame):
            await self._send_user_audio(frame)
        elif isinstance(frame, LLMContextFrame):
            await self._handle_context(frame)
        else:
            await self.push_frame(frame, direction)

    async def _send_user_audio(self, frame: InputAudioRawFrame) -> None:
        audio_b64 = base64.b64encode(frame.audio).decode()
        await self._send({"type": "audio.append", "audio": audio_b64})

    async def _handle_context(self, frame: LLMContextFrame) -> None:
        """Extract the system prompt from the context and configure the session."""
        for msg in frame.context.messages:
            if msg.get("role") == "system":
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = " ".join(
                        c.get("text", "") for c in content if isinstance(c, dict)
                    )
                if content:
                    await self._send({
                        "type": "session.configure",
                        "session": {"system_prompt": content},
                    })
                break
        # Always forward so other pipeline processors see the context frame
        await self.push_frame(frame, FrameDirection.DOWNSTREAM)

    # ── Receive Loop ──────────────────────────────────────────────────────────

    async def _receive_task_handler(self) -> None:
        try:
            async for raw in self._websocket:
                try:
                    event = json.loads(raw)
                    await self._handle_event(event)
                except Exception:
                    logger.exception("Error handling event")
        except websockets.exceptions.ConnectionClosed:
            logger.info("AssemblyAI S2S connection closed")
        except Exception:
            logger.exception("Unexpected error in receive loop")

    async def _handle_event(self, event: dict) -> None:
        t = event.get("type", "")

        # Debug log everything except high-frequency audio
        if t != "response.audio":
            logger.debug(f"← {t}  {event}")

        if t == "session.ready":
            await self._on_session_ready(event)
        elif t == "speech.started":
            await self._on_speech_started()
        elif t == "speech.stopped":
            await self._on_speech_stopped()
        elif t == "transcript.user.delta":
            await self._on_user_transcript_delta(event)
        elif t == "transcript.user":
            await self._on_user_transcript(event)
        elif t == "response.started":
            await self._on_response_started(event)
        elif t == "response.audio":
            await self._on_response_audio(event)
        elif t == "response.transcript":
            await self._on_response_transcript(event)
        elif t == "response.done":
            await self._on_response_done()
        elif t == "response.interrupted":
            await self._on_response_interrupted()
        elif t == "function.call":
            await self._on_function_call(event)
        elif t == "error":
            await self._on_error(event)

    # ── Server Event Handlers ─────────────────────────────────────────────────

    async def _on_session_ready(self, event: dict) -> None:
        self._session_ready = True
        logger.info("AssemblyAI session ready")

        # Send system prompt
        if self._system_prompt:
            await self._send({
                "type": "session.configure",
                "session": {"system_prompt": self._system_prompt},
            })

        # Flush any tools that were registered before session was ready
        if self._pending_tools:
            await self._send({
                "type": "session.configure",
                "session": {"tools": self._pending_tools},
            })
            self._pending_tools = []

    @staticmethod
    def _ts() -> str:
        return datetime.now(timezone.utc).isoformat()

    async def _on_speech_started(self) -> None:
        self._user_transcript_buf = ""  # reset accumulator for new utterance
        await self.push_frame(UserStartedSpeakingFrame(), FrameDirection.UPSTREAM)
        # Interrupt the bot if it was speaking
        if self._bot_speaking and self._current_response_id:
            await self._send({
                "type": "response.cancel",
                "response_id": self._current_response_id,
            })

    async def _on_speech_stopped(self) -> None:
        await self.push_frame(UserStoppedSpeakingFrame(), FrameDirection.UPSTREAM)

    async def _on_user_transcript_delta(self, event: dict) -> None:
        # The native API sends cumulative partial text (not word-by-word deltas),
        # so replace the buffer with the latest full partial rather than appending.
        text = event.get("text", "")
        if text and text != self._user_transcript_buf:
            self._user_transcript_buf = text
            await self.push_frame(
                InterimTranscriptionFrame(text=text, user_id="user", timestamp=self._ts()),
                FrameDirection.UPSTREAM,
            )

    async def _on_user_transcript(self, event: dict) -> None:
        text = event.get("text", "")
        self._user_transcript_buf = ""  # clear accumulator on final transcript
        if text:
            logger.info(f"[User] {text}")
            await self.push_frame(
                TranscriptionFrame(text=text, user_id="user", timestamp=self._ts()),
                FrameDirection.UPSTREAM,
            )

    async def _on_response_started(self, event: dict) -> None:
        self._current_response_id = event.get("response_id", "")
        self._bot_speaking = True
        await self.push_frame(TTSStartedFrame())
        await self.push_frame(BotStartedSpeakingFrame())

    async def _on_response_audio(self, event: dict) -> None:
        data = base64.b64decode(event.get("data", ""))
        if data:
            await self.push_frame(
                TTSAudioRawFrame(
                    audio=data,
                    sample_rate=SAMPLE_RATE,
                    num_channels=NUM_CHANNELS,
                )
            )

    async def _on_response_transcript(self, event: dict) -> None:
        text = event.get("text", "")
        if text:
            logger.info(f"[Agent] {text}")

    async def _on_response_done(self) -> None:
        self._current_response_id = None
        self._bot_speaking = False
        await self.push_frame(TTSStoppedFrame())
        await self.push_frame(BotStoppedSpeakingFrame())

    async def _on_response_interrupted(self) -> None:
        self._current_response_id = None
        self._bot_speaking = False
        await self.push_frame(TTSStoppedFrame())
        await self.push_frame(BotStoppedSpeakingFrame())

    async def _on_function_call(self, event: dict) -> None:
        call_id = event.get("call_id", "")
        name = event.get("name", "")
        args = event.get("args", {})
        if isinstance(args, dict):
            args = json.dumps(args)

        logger.info(f"Function call: {name}({args})")

        result = ""
        if self.has_function(name):
            try:
                result = await self._execute_function(name, call_id, args)
            except Exception as e:
                logger.exception(f"Function {name} raised an error")
                result = f"Error: {e}"

        await self._send({
            "type": "function.result",
            "call_id": call_id,
            "result": result if result is not None else "",
        })

    async def _execute_function(
        self, name: str, call_id: str, arguments: str
    ) -> str:
        """Call a registered PipeCat function and return its string result."""
        try:
            from pipecat.adapters.schemas.direct_function import DirectFunctionWrapper
            from pipecat.processors.aggregators.llm_context import LLMContext
            from pipecat.services.llm_service import FunctionCallParams

            args = json.loads(arguments) if isinstance(arguments, str) else arguments
            result_holder: list = []

            async def result_callback(result, **_kwargs):
                result_holder.append(result)

            params = FunctionCallParams(
                function_name=name,
                tool_call_id=call_id,
                arguments=args,
                llm=self,
                context=LLMContext(),
                result_callback=result_callback,
            )
            item = self._functions[name]
            if isinstance(item.handler, DirectFunctionWrapper):
                await item.handler.invoke(args=args, params=params)
            else:
                await item.handler(params)

            return str(result_holder[0]) if result_holder else ""
        except Exception:
            logger.exception(f"Error executing function {name}")
            return ""

    async def _on_error(self, event: dict) -> None:
        msg = (
            event.get("message")
            or (event.get("error") or {}).get("message")
            or str(event)
        )
        logger.error(f"AssemblyAI S2S error: {msg}")
        await self.push_frame(ErrorFrame(msg))

    # ── Public helpers ────────────────────────────────────────────────────────

    async def set_tools(self, tools: list[dict]) -> None:
        """Send tool definitions to the session (call after session is ready)."""
        if self._session_ready:
            await self._send({
                "type": "session.configure",
                "session": {"tools": tools},
            })
        else:
            self._pending_tools = tools

    async def trigger_response(self) -> None:
        """Manually trigger a response (useful when VAD is disabled)."""
        await self._send({"type": "response.create"})
