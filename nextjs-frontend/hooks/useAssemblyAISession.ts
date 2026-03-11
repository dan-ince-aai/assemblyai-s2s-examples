"use client";

import { useCallback, useRef, useState } from "react";

export type SessionStatus =
  | "idle"
  | "connecting"
  | "listening"
  | "speaking";

export interface AssemblyAISession {
  status: SessionStatus;
  transcript: string;
  agentText: string;
  error: string | null;
  micStream: MediaStream | null;
  connect: () => Promise<void>;
  disconnect: () => void;
}

function float32ToInt16(float32Array: Float32Array): Int16Array {
  const int16Array = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    const clamped = Math.max(-1, Math.min(1, float32Array[i]));
    int16Array[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  }
  return int16Array;
}

function int16ArrayToBase64(int16Array: Int16Array): string {
  const bytes = new Uint8Array(int16Array.buffer);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function base64ToInt16Array(base64: string): Int16Array {
  const binaryStr = atob(base64);
  const bytes = new Uint8Array(binaryStr.length);
  for (let i = 0; i < binaryStr.length; i++) {
    bytes[i] = binaryStr.charCodeAt(i);
  }
  return new Int16Array(bytes.buffer);
}

export function useAssemblyAISession(): AssemblyAISession {
  const [status, setStatus] = useState<SessionStatus>("idle");
  const [transcript, setTranscript] = useState("");
  const [agentText, setAgentText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [micStream, setMicStream] = useState<MediaStream | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const disconnect = useCallback(() => {
    // Stop mic
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      setMicStream(null);
    }

    // Disconnect script processor
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }

    // Close AudioContext
    if (audioCtxRef.current) {
      audioCtxRef.current.close();
      audioCtxRef.current = null;
    }

    // Close WebSocket
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setStatus("idle");
  }, []);

  const connect = useCallback(async () => {
    setError(null);
    setStatus("connecting");
    setTranscript("");
    setAgentText("");

    // Connect to the server-side WebSocket proxy at /ws.
    // server.ts handles the connection and adds the Authorization header.
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const wsUrl = `${proto}://${window.location.host}/ws`;

    // Request microphone access
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      setError("Microphone access denied.");
      setStatus("idle");
      return;
    }

    streamRef.current = stream;
    setMicStream(stream);

    // Set up AudioContext at 24 kHz
    const audioCtx = new AudioContext({ sampleRate: 24000 });
    audioCtxRef.current = audioCtx;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    // Create a ScriptProcessorNode to capture raw PCM from the mic
    const source = audioCtx.createMediaStreamSource(stream);
    const processor = audioCtx.createScriptProcessor(4096, 1, 1);
    processorRef.current = processor;

    processor.onaudioprocess = (e) => {
      if (ws.readyState !== WebSocket.OPEN) return;
      const float32 = e.inputBuffer.getChannelData(0);
      const int16 = float32ToInt16(float32);
      const b64 = int16ArrayToBase64(int16);
      ws.send(JSON.stringify({ type: "input.audio", audio: b64 }));
    };

    source.connect(processor);
    processor.connect(audioCtx.destination);

    // WebSocket event handlers
    ws.onopen = () => {
      // Connection open — wait for session.ready before doing anything
    };

    ws.onmessage = async (event) => {
      let msg: Record<string, unknown>;
      try {
        msg = JSON.parse(event.data as string);
      } catch {
        return;
      }

      const type = msg.type as string;

      if (type === "session.ready") {
        setStatus("listening");
      } else if (type === "input.speech.started") {
        setStatus("listening");
      } else if (type === "transcript.user") {
        setTranscript((msg.text as string) ?? "");
      } else if (type === "reply.started") {
        setStatus("speaking");
      } else if (type === "reply.audio") {
        const b64 = msg.data as string;
        if (!b64) return;

        const int16 = base64ToInt16Array(b64);
        const float32 = new Float32Array(int16.length);
        for (let i = 0; i < int16.length; i++) {
          float32[i] = int16[i] / (int16[i] < 0 ? 0x8000 : 0x7fff);
        }

        const buffer = audioCtx.createBuffer(1, float32.length, 24000);
        buffer.copyToChannel(float32, 0);

        const bufferSource = audioCtx.createBufferSource();
        bufferSource.buffer = buffer;
        bufferSource.connect(audioCtx.destination);
        bufferSource.start();
      } else if (type === "transcript.agent") {
        setAgentText((msg.text as string) ?? "");
      } else if (type === "reply.done") {
        setStatus("listening");
      } else if (type === "session.error") {
        const errMsg =
          (msg.message as string) ?? JSON.stringify(msg);
        setError(errMsg);
        setStatus("idle");
      }
    };

    ws.onerror = () => {
      setError("WebSocket connection error.");
      setStatus("idle");
    };

    ws.onclose = () => {
      if (status !== "idle") {
        setStatus("idle");
      }
    };
  }, [status]);

  return {
    status,
    transcript,
    agentText,
    error,
    micStream,
    connect,
    disconnect,
  };
}
