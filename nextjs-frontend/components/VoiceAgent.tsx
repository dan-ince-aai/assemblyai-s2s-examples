"use client";

import { useAssemblyAISession, SessionStatus } from "@/hooks/useAssemblyAISession";
import AudioVisualizer from "@/components/AudioVisualizer";
import { Mic, MicOff } from "lucide-react";

const STATUS_CONFIG: Record<
  SessionStatus,
  { label: string; color: string; dot: string }
> = {
  idle: {
    label: "Idle",
    color: "#6b7280",
    dot: "#6b7280",
  },
  connecting: {
    label: "Connecting...",
    color: "#f59e0b",
    dot: "#f59e0b",
  },
  listening: {
    label: "Listening",
    color: "#22c55e",
    dot: "#22c55e",
  },
  speaking: {
    label: "Agent Speaking",
    color: "#3b82f6",
    dot: "#3b82f6",
  },
};

export default function VoiceAgent() {
  const session = useAssemblyAISession();
  const { status, transcript, agentText, error, micStream } = session;

  const isConnected = status !== "idle";
  const isActive = status === "listening" || status === "speaking";
  const cfg = STATUS_CONFIG[status];

  function handleToggle() {
    if (isConnected) {
      session.disconnect();
    } else {
      session.connect();
    }
  }

  return (
    <div
      style={{
        width: "100%",
        maxWidth: "400px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "24px",
        padding: "32px 24px",
        borderRadius: "20px",
        background: "var(--surface)",
        border: "1px solid var(--border)",
        boxShadow: "0 25px 50px rgba(0,0,0,0.5)",
      }}
    >
      {/* Title */}
      <div style={{ textAlign: "center" }}>
        <h1
          style={{
            fontSize: "20px",
            fontWeight: 700,
            color: "var(--foreground)",
            letterSpacing: "-0.02em",
          }}
        >
          AssemblyAI Voice Agent
        </h1>
        <p style={{ fontSize: "13px", color: "#6b7280", marginTop: "4px" }}>
          Real-time speech-to-speech conversation
        </p>
      </div>

      {/* Mic button with pulse ring */}
      <div style={{ position: "relative", display: "flex", alignItems: "center", justifyContent: "center" }}>
        {isActive && (
          <span
            style={{
              position: "absolute",
              width: "96px",
              height: "96px",
              borderRadius: "50%",
              background: `${cfg.dot}22`,
              animation: "pulse 1.5s ease-in-out infinite",
            }}
          />
        )}
        <button
          onClick={handleToggle}
          style={{
            width: "72px",
            height: "72px",
            borderRadius: "50%",
            border: "none",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: isConnected
              ? "#ef4444"
              : "linear-gradient(135deg, #6366f1, #4f46e5)",
            color: "white",
            boxShadow: isConnected
              ? "0 0 0 4px rgba(239,68,68,0.2)"
              : "0 0 0 4px rgba(99,102,241,0.3), 0 8px 24px rgba(99,102,241,0.4)",
            transition: "transform 0.1s ease, box-shadow 0.2s ease",
            position: "relative",
            zIndex: 1,
          }}
          aria-label={isConnected ? "Disconnect" : "Connect"}
        >
          {isConnected ? <MicOff size={28} /> : <Mic size={28} />}
        </button>
      </div>

      {/* Status indicator */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          padding: "6px 14px",
          borderRadius: "999px",
          background: "rgba(255,255,255,0.04)",
          border: `1px solid ${cfg.dot}44`,
        }}
      >
        <span
          style={{
            width: "8px",
            height: "8px",
            borderRadius: "50%",
            background: cfg.dot,
            boxShadow: isActive ? `0 0 6px ${cfg.dot}` : "none",
            transition: "background 0.3s",
          }}
        />
        <span style={{ fontSize: "13px", color: cfg.color, fontWeight: 500 }}>
          {cfg.label}
        </span>
      </div>

      {/* User transcript */}
      {transcript && (
        <div
          style={{
            width: "100%",
            padding: "12px 16px",
            borderRadius: "10px",
            background: "rgba(255,255,255,0.04)",
            border: "1px solid var(--border)",
          }}
        >
          <p style={{ fontSize: "11px", color: "#6b7280", marginBottom: "4px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            You said
          </p>
          <p style={{ fontSize: "14px", color: "#d1d5db", lineHeight: 1.5 }}>
            {transcript}
          </p>
        </div>
      )}

      {/* Agent response */}
      {agentText && (
        <div
          style={{
            width: "100%",
            padding: "12px 16px",
            borderRadius: "10px",
            background: "rgba(99, 102, 241, 0.08)",
            border: "1px solid rgba(99, 102, 241, 0.25)",
          }}
        >
          <p style={{ fontSize: "11px", color: "#6366f1", marginBottom: "4px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Agent
          </p>
          <p style={{ fontSize: "14px", color: "#c7d2fe", lineHeight: 1.5 }}>
            {agentText}
          </p>
        </div>
      )}

      {/* Audio visualizer */}
      {isConnected && (
        <AudioVisualizer stream={micStream} />
      )}

      {/* Error */}
      {error && (
        <div
          style={{
            width: "100%",
            padding: "10px 14px",
            borderRadius: "8px",
            background: "rgba(239, 68, 68, 0.1)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
          }}
        >
          <p style={{ fontSize: "13px", color: "#fca5a5" }}>{error}</p>
        </div>
      )}

      {/* Idle hint */}
      {status === "idle" && (
        <p style={{ fontSize: "13px", color: "#4b5563", textAlign: "center" }}>
          Click the microphone to start a conversation
        </p>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { transform: scale(1); opacity: 0.7; }
          50% { transform: scale(1.3); opacity: 0.2; }
        }
      `}</style>
    </div>
  );
}
