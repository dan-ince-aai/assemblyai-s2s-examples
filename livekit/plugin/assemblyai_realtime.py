"""AssemblyAI Native Realtime Plugin — livekit.agents RealtimeModel/RealtimeSession."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass
from typing import Literal

import aiohttp
from livekit import rtc
from livekit.agents import APIConnectionError, llm, utils
from livekit.agents.types import NOT_GIVEN, NotGivenOr
from livekit.agents.utils import is_given

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24000
NUM_CHANNELS = 1
# 100 ms chunks — matches OpenAI plugin convention
_SAMPLES_PER_CHUNK = SAMPLE_RATE // 10


@dataclass
class _Generation:
    response_id: str
    msg_ch: utils.aio.Chan[llm.MessageGeneration]
    fn_ch: utils.aio.Chan[llm.FunctionCall]
    text_ch: utils.aio.Chan[str]
    audio_ch: utils.aio.Chan[rtc.AudioFrame]
    modalities_fut: asyncio.Future[list[Literal["text", "audio"]]]


def _serialize_tool(tool: llm.Tool) -> dict | None:
    if isinstance(tool, llm.FunctionTool):
        desc = llm.utils.build_legacy_openai_schema(tool, internally_tagged=True)
        return desc
    elif isinstance(tool, llm.RawFunctionTool):
        raw = dict(tool.info.raw_schema)
        raw.pop("meta", None)
        raw["type"] = "function"
        return raw
    return None


class _SessionExpiredError(Exception):
    pass


class RealtimeModel(llm.RealtimeModel):
    def __init__(
        self,
        *,
        url: str,
        api_key: str,
        sample_rate: int = SAMPLE_RATE,
    ) -> None:
        super().__init__(
            capabilities=llm.RealtimeCapabilities(
                turn_detection=True,
                user_transcription=True,
                audio_output=True,
                manual_function_calls=False,
                auto_tool_reply_generation=True,
                message_truncation=False,
            )
        )
        self._url = url
        self._api_key = api_key
        self._sample_rate = sample_rate
        self._http_session: aiohttp.ClientSession | None = None

    def _ensure_http_session(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    def session(self) -> RealtimeSession:
        return RealtimeSession(self)

    async def aclose(self) -> None:
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()


class RealtimeSession(llm.RealtimeSession[Literal[()]]):
    def __init__(self, realtime_model: RealtimeModel) -> None:
        super().__init__(realtime_model)
        self._model = realtime_model
        self._tools = llm.ToolContext.empty()
        self._chat_ctx = llm.ChatContext.empty()

        self._msg_ch: utils.aio.Chan[dict] = utils.aio.Chan()
        self._current_gen: _Generation | None = None
        self._pending_reply_fut: asyncio.Future[llm.GenerationCreatedEvent] | None = (
            None
        )
        self._current_response_id: str | None = None

        self._pending_call_ids: set[str] = set()
        self._session_ready: bool = False
        self._session_id: str | None = None

        self._bstream = utils.audio.AudioByteStream(
            SAMPLE_RATE, NUM_CHANNELS, samples_per_channel=_SAMPLES_PER_CHUNK
        )
        self._input_resampler: rtc.AudioResampler | None = None

        self._main_task = asyncio.create_task(
            self._run(), name="AssemblyAIRealtimeSession._run"
        )

    # ── properties ────────────────────────────────────────────────────────

    @property
    def chat_ctx(self) -> llm.ChatContext:
        return self._chat_ctx

    @property
    def tools(self) -> llm.ToolContext:
        return self._tools.copy()

    # ── outbound helpers ──────────────────────────────────────────────────

    def _send(self, msg: dict) -> None:
        try:
            self._msg_ch.send_nowait(msg)
        except Exception:
            pass

    # ── public API ────────────────────────────────────────────────────────

    def push_audio(self, frame: rtc.AudioFrame) -> None:
        for f in self._resample_audio(frame):
            for chunk in self._bstream.write(f.data.tobytes()):
                self._send(
                    {
                        "type": "input.audio",
                        "audio": base64.b64encode(chunk.data).decode(),
                    }
                )

    def push_video(self, frame: rtc.VideoFrame) -> None:
        pass

    def generate_reply(
        self, *, instructions: NotGivenOr[str] = NOT_GIVEN
    ) -> asyncio.Future[llm.GenerationCreatedEvent]:
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[llm.GenerationCreatedEvent] = loop.create_future()
        self._pending_reply_fut = fut
        self._send({"type": "reply.create"})

        def _on_timeout() -> None:
            if not fut.done():
                fut.set_exception(llm.RealtimeError("generate_reply timed out."))

        handle = loop.call_later(5.0, _on_timeout)
        fut.add_done_callback(lambda _: handle.cancel())
        return fut

    def interrupt(self) -> None:
        if self._current_response_id:
            self._send({"type": "reply.cancel", "reply_id": self._current_response_id})

    def commit_audio(self) -> None:
        pass  # server-side VAD; no client commit needed

    def clear_audio(self) -> None:
        pass

    def truncate(
        self,
        *,
        message_id: str,
        modalities: list[Literal["text", "audio"]],
        audio_end_ms: int,
        audio_transcript: NotGivenOr[str] = NOT_GIVEN,
    ) -> None:
        pass  # no-op V1

    async def update_instructions(self, instructions: str) -> None:
        self._send(
            {"type": "session.update", "session": {"system_prompt": instructions}}
        )

    async def update_tools(self, tools: list[llm.Tool]) -> None:
        serialized = [s for t in tools if (s := _serialize_tool(t)) is not None]
        self._send({"type": "session.update", "session": {"tools": serialized}})
        self._tools = llm.ToolContext(
            [t for t in tools if isinstance(t, (llm.FunctionTool, llm.RawFunctionTool))]
        )

    def update_options(
        self, *, tool_choice: NotGivenOr[llm.ToolChoice | None] = NOT_GIVEN
    ) -> None:
        if is_given(tool_choice):
            self._send(
                {"type": "session.update", "session": {"tool_choice": tool_choice}}
            )

    async def update_chat_ctx(self, chat_ctx: llm.ChatContext) -> None:
        if self._session_ready:
            existing_ids = {item.id for item in self._chat_ctx.items}
            for item in chat_ctx.items:
                if item.id in existing_ids:
                    continue
                if (
                    isinstance(item, llm.FunctionCallOutput)
                    and item.call_id in self._pending_call_ids
                ):
                    self._send(
                        {
                            "type": "tool.result",
                            "call_id": item.call_id,
                            "result": item.output,
                        }
                    )
                    self._pending_call_ids.discard(item.call_id)
                elif isinstance(item, llm.ChatMessage) and item.role in (
                    "user",
                    "system",
                ):
                    if item.text_content:
                        self._send(
                            {
                                "type": "conversation.message",
                                "role": item.role,
                                "content": item.text_content,
                            }
                        )
        self._chat_ctx = chat_ctx

    async def aclose(self) -> None:
        self._msg_ch.close()
        await self._main_task

    # ── WS run loop ───────────────────────────────────────────────────────

    @utils.log_exceptions(logger=logger)
    async def _run(self) -> None:
        MAX_RECONNECT_ATTEMPTS = 3
        BACKOFF_SECONDS = [0.5, 1.0, 2.0]

        for attempt in range(MAX_RECONNECT_ATTEMPTS + 1):
            try:
                headers = {"Authorization": f"Bearer {self._model._api_key}"}
                try:
                    ws = await self._model._ensure_http_session().ws_connect(
                        self._model._url, headers=headers
                    )
                except aiohttp.ClientError as e:
                    raise APIConnectionError(
                        "AssemblyAI Realtime connection error"
                    ) from e

                if self._session_id is not None:
                    try:
                        await ws.send_str(
                            json.dumps(
                                {
                                    "type": "session.resume",
                                    "session_id": self._session_id,
                                }
                            )
                        )
                    except Exception as e:
                        raise APIConnectionError("Failed to send session.resume") from e

                # Reset per-connection state (preserve: _chat_ctx, _tools, _session_id,
                #                                         _pending_call_ids)
                self._session_ready = False
                self._current_response_id = None
                self._close_current_gen()
                if self._pending_reply_fut:
                    self._pending_reply_fut.cancel()
                    self._pending_reply_fut = None
                self._bstream = utils.audio.AudioByteStream(
                    SAMPLE_RATE, NUM_CHANNELS, samples_per_channel=_SAMPLES_PER_CHUNK
                )

                closing = False

                @utils.log_exceptions(logger=logger)
                async def _send_task() -> None:
                    nonlocal closing
                    async for msg in self._msg_ch:
                        try:
                            await ws.send_str(json.dumps(msg))
                        except Exception:
                            logger.exception("failed to send event")
                    closing = True
                    await ws.close()

                @utils.log_exceptions(logger=logger)
                async def _recv_task() -> None:
                    while True:
                        msg = await ws.receive()
                        if msg.type in (
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.CLOSE,
                            aiohttp.WSMsgType.CLOSING,
                        ):
                            if closing:
                                return
                            raise APIConnectionError(
                                "AssemblyAI Realtime connection closed unexpectedly"
                            )
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        try:
                            event = json.loads(msg.data)
                            self._handle_event(event)
                        except _SessionExpiredError:
                            # Server rejected resume — fall back to fresh session
                            self._session_id = None
                            self._pending_call_ids.clear()
                            raise APIConnectionError(
                                "Session expired; retrying as fresh session"
                            )
                        except Exception:
                            logger.exception(
                                "failed to handle event", extra={"data": msg.data}
                            )

                tasks = [
                    asyncio.create_task(_recv_task(), name="_recv_task"),
                    asyncio.create_task(_send_task(), name="_send_task"),
                ]
                try:
                    done, _ = await asyncio.wait(
                        tasks, return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        task.result()
                    return  # clean exit — do not retry
                finally:
                    await utils.aio.cancel_and_wait(*tasks)
                    await ws.close()

            except APIConnectionError:
                if attempt >= MAX_RECONNECT_ATTEMPTS:
                    raise
                backoff = BACKOFF_SECONDS[attempt]
                logger.warning(
                    "Connection lost, retrying (attempt %d/%d, backoff=%.1fs, session_id=%s)",
                    attempt + 1,
                    MAX_RECONNECT_ATTEMPTS,
                    backoff,
                    self._session_id,
                )
                await asyncio.sleep(backoff)

    # ── event routing ─────────────────────────────────────────────────────

    def _handle_event(self, event: dict) -> None:
        self.emit(f"aai.{event.get('type', '')}", event)
        t = event.get("type", "")
        if t == "session.ready":
            self._handle_session_ready(event)
        elif t == "input.speech.started":
            self.emit("input_speech_started", llm.InputSpeechStartedEvent())
        elif t == "input.speech.stopped":
            self.emit(
                "input_speech_stopped",
                llm.InputSpeechStoppedEvent(user_transcription_enabled=True),
            )
        elif t == "transcript.user":
            self.emit(
                "input_audio_transcription_completed",
                llm.InputTranscriptionCompleted(
                    item_id=event.get("item_id", ""),
                    transcript=event.get("text", ""),
                    is_final=True,
                ),
            )
        elif t == "reply.started":
            self._handle_response_started(event)
        elif t == "reply.audio":
            self._handle_response_audio(event)
        elif t == "transcript.agent":
            self._handle_transcript_done(event)
        elif t == "reply.done":
            self._handle_reply_done(event)
        elif t == "tool.call":
            self._handle_function_call(event)
        elif t == "session.updated":
            pass
        elif t == "transcript.user.delta":
            pass
        elif t == "session.error":
            self._handle_error(event)

    def _handle_session_ready(self, event: dict) -> None:
        self._session_ready = True
        self._session_id = event.get("session_id")
        # Flush FC results that completed locally but weren't sent during reconnect
        for item in self._chat_ctx.items:
            if (
                isinstance(item, llm.FunctionCallOutput)
                and item.call_id in self._pending_call_ids
            ):
                self._send(
                    {
                        "type": "tool.result",
                        "call_id": item.call_id,
                        "result": item.output,
                    }
                )
                self._pending_call_ids.discard(item.call_id)
        if self._pending_reply_fut and not self._pending_reply_fut.done():
            self._send({"type": "reply.create"})

    def _handle_response_started(self, event: dict) -> None:
        self._close_current_gen()
        response_id = event.get("reply_id", "")
        self._current_response_id = response_id

        text_ch: utils.aio.Chan[str] = utils.aio.Chan()
        audio_ch: utils.aio.Chan[rtc.AudioFrame] = utils.aio.Chan()
        modalities_fut: asyncio.Future[list[Literal["text", "audio"]]] = (
            asyncio.get_event_loop().create_future()
        )
        modalities_fut.set_result(["audio"])

        msg_gen = llm.MessageGeneration(
            message_id=response_id,
            text_stream=text_ch,
            audio_stream=audio_ch,
            modalities=modalities_fut,
        )
        msg_ch: utils.aio.Chan[llm.MessageGeneration] = utils.aio.Chan()
        fn_ch: utils.aio.Chan[llm.FunctionCall] = utils.aio.Chan()

        self._current_gen = _Generation(
            response_id=response_id,
            msg_ch=msg_ch,
            fn_ch=fn_ch,
            text_ch=text_ch,
            audio_ch=audio_ch,
            modalities_fut=modalities_fut,
        )
        msg_ch.send_nowait(msg_gen)

        gen_ev = llm.GenerationCreatedEvent(
            message_stream=msg_ch,
            function_stream=fn_ch,
            user_initiated=False,
            response_id=response_id,
        )

        if self._pending_reply_fut and not self._pending_reply_fut.done():
            gen_ev.user_initiated = True
            self._pending_reply_fut.set_result(gen_ev)
            self._pending_reply_fut = None

        self.emit("generation_created", gen_ev)

    def _handle_response_audio(self, event: dict) -> None:
        gen = self._current_gen
        if gen is None:
            return
        data = base64.b64decode(event.get("data", ""))
        if not data:
            return
        gen.audio_ch.send_nowait(
            rtc.AudioFrame(
                data=data,
                sample_rate=SAMPLE_RATE,
                num_channels=NUM_CHANNELS,
                samples_per_channel=len(data) // 2,
            )
        )

    def _handle_transcript_done(self, event: dict) -> None:
        gen = self._current_gen
        if gen is None:
            return
        text = event.get("text", "")
        if text:
            gen.text_ch.send_nowait(text)
        gen.text_ch.close()

    def _handle_reply_done(self, event: dict) -> None:
        self._close_current_gen()
        self._current_response_id = None

    def _handle_function_call(self, event: dict) -> None:
        gen = self._current_gen
        if gen is None:
            return
        call_id = event.get("call_id", "")
        if call_id in self._pending_call_ids:
            return
        for item in self._chat_ctx.items:
            if isinstance(item, llm.FunctionCallOutput) and item.call_id == call_id:
                self._pending_call_ids.add(call_id)
                return
        self._pending_call_ids.add(call_id)
        name = event.get("name", "")
        args = event.get("args", {})
        gen.fn_ch.send_nowait(
            llm.FunctionCall(
                call_id=call_id,
                name=name,
                arguments=json.dumps(args),
            )
        )

    def _handle_error(self, event: dict) -> None:
        code = event.get("code", "")
        if code in ("session_not_found", "session_forbidden"):
            raise _SessionExpiredError(event.get("message", ""))
        self.emit(
            "error",
            llm.RealtimeModelError(
                timestamp=time.time(),
                label=self._model.label,
                error=Exception(event.get("message", "unknown error")),
                recoverable=False,
            ),
        )

    def _close_current_gen(self) -> None:
        gen = self._current_gen
        if gen is None:
            return
        gen.audio_ch.close()
        gen.text_ch.close()
        gen.fn_ch.close()
        gen.msg_ch.close()
        self._current_gen = None

    # ── audio resampling ──────────────────────────────────────────────────

    def _resample_audio(self, frame: rtc.AudioFrame):  # type: ignore[return]
        if self._input_resampler is not None:
            if frame.sample_rate != self._input_resampler._input_rate:
                self._input_resampler = None

        if self._input_resampler is None and (
            frame.sample_rate != SAMPLE_RATE or frame.num_channels != NUM_CHANNELS
        ):
            self._input_resampler = rtc.AudioResampler(
                input_rate=frame.sample_rate,
                output_rate=SAMPLE_RATE,
                num_channels=NUM_CHANNELS,
            )

        if self._input_resampler:
            yield from self._input_resampler.push(frame)
        else:
            yield frame