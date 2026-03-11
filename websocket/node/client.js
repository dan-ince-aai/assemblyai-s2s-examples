"use strict";
/**
 * AssemblyAI S2S WebSocket Client — Node.js terminal client.
 *
 * Streams microphone audio to AssemblyAI Speech-to-Speech API and
 * plays back the agent's audio response in real time.
 *
 * Audio format: PCM16, 24 kHz, mono
 *
 * Usage:
 *   node client.js
 */

require("dotenv").config();

const WebSocket = require("ws");
const recorder = require("node-record-lpcm16");
const Speaker = require("node-speaker");

const API_KEY = process.env.ASSEMBLYAI_API_KEY;
const API_URL =
  process.env.ASSEMBLYAI_REALTIME_URL ||
  "wss://speech-to-speech.us.assemblyai.com/v1/realtime";

const SAMPLE_RATE = 24000;
const CHANNELS = 1;
const BIT_DEPTH = 16;

// ANSI colors
const GREEN = "\x1b[32m";
const BLUE = "\x1b[34m";
const YELLOW = "\x1b[33m";
const RED = "\x1b[31m";
const RESET = "\x1b[0m";
const BOLD = "\x1b[1m";

if (!API_KEY) {
  console.error(`${RED}Error: ASSEMBLYAI_API_KEY environment variable not set.${RESET}`);
  process.exit(1);
}

console.log(`${BOLD}Connecting to AssemblyAI S2S...${RESET}`);

const ws = new WebSocket(API_URL, {
  headers: {
    Authorization: `Bearer ${API_KEY}`,
  },
});

// Speaker for PCM16 audio playback
const speaker = new Speaker({
  channels: CHANNELS,
  bitDepth: BIT_DEPTH,
  sampleRate: SAMPLE_RATE,
  signed: true,
});

// Microphone recording
let micStream = null;

function startMic() {
  micStream = recorder.record({
    sampleRate: SAMPLE_RATE,
    channels: CHANNELS,
    audioType: "raw",
    recorder: "sox",
    encoding: "signed-integer",
    endian: "little",
  });

  micStream.stream().on("data", (chunk) => {
    if (ws.readyState === WebSocket.OPEN) {
      const b64 = chunk.toString("base64");
      ws.send(JSON.stringify({ type: "audio.append", audio: b64 }));
    }
  });

  micStream.stream().on("error", (err) => {
    console.error(`${RED}Mic error: ${err.message}${RESET}`);
  });
}

function cleanup() {
  if (micStream) {
    try {
      micStream.stop();
    } catch (_) {}
  }
  try {
    speaker.end();
  } catch (_) {}
  if (ws.readyState === WebSocket.OPEN) {
    ws.close();
  }
}

// Handle WebSocket events
ws.on("open", () => {
  console.log(`${GREEN}Connected.${RESET} Waiting for session...`);
});

ws.on("message", (data) => {
  let event;
  try {
    event = JSON.parse(data.toString());
  } catch (e) {
    return;
  }

  const type = event.type || "";

  if (type === "session.ready") {
    console.log(`${GREEN}Session ready — speak into your microphone.${RESET}`);
    startMic();
  } else if (type === "speech.started") {
    process.stdout.write(`\n${YELLOW}[listening...]${RESET}`);
  } else if (type === "transcript.user.delta") {
    const text = event.text || "";
    process.stdout.write(`\r${YELLOW}[You] ${text}${RESET}`);
  } else if (type === "transcript.user") {
    const text = event.text || "";
    console.log(`\r${GREEN}[You] ${text}${RESET}`);
  } else if (type === "response.started") {
    console.log(`${BLUE}[Agent speaking...]${RESET}`);
  } else if (type === "response.audio") {
    const audioData = Buffer.from(event.data || "", "base64");
    if (audioData.length > 0) {
      speaker.write(audioData);
    }
  } else if (type === "response.transcript") {
    const text = event.text || "";
    if (text) {
      console.log(`${BLUE}[Agent] ${text}${RESET}`);
    }
  } else if (type === "response.done") {
    console.log(`${BLUE}[Agent done]${RESET}`);
  } else if (type === "error") {
    const msg = event.message || JSON.stringify(event);
    console.error(`${RED}[Error] ${msg}${RESET}`);
  }
});

ws.on("close", (code, reason) => {
  console.log(`\n${YELLOW}Connection closed (${code}).${RESET}`);
  cleanup();
  process.exit(0);
});

ws.on("error", (err) => {
  console.error(`${RED}WebSocket error: ${err.message}${RESET}`);
  cleanup();
  process.exit(1);
});

// Graceful shutdown
process.on("SIGINT", () => {
  console.log(`\n${YELLOW}Interrupted — shutting down.${RESET}`);
  cleanup();
  process.exit(0);
});

process.on("SIGTERM", () => {
  cleanup();
  process.exit(0);
});
