#!/usr/bin/env bash
# deploy-api.sh — Expose a locally running bot with ngrok.
#
# Usage:
#   ./scripts/deploy-api.sh [PORT]
#
# Default port: 8080

set -euo pipefail

PORT="${1:-8080}"

YELLOW="\033[93m"
GREEN="\033[92m"
RED="\033[91m"
RESET="\033[0m"
BOLD="\033[1m"

echo -e "${BOLD}AssemblyAI S2S — Local Bot Tunnel${RESET}"
echo -e "${YELLOW}Exposing port ${PORT} via ngrok...${RESET}\n"

if ! command -v ngrok &>/dev/null; then
  echo -e "${RED}Error: ngrok is not installed.${RESET}"
  echo "Install it from https://ngrok.com/download or with:"
  echo "  brew install ngrok/ngrok/ngrok"
  exit 1
fi

echo -e "${GREEN}Starting ngrok tunnel on port ${PORT}...${RESET}"
echo -e "${YELLOW}Once running, copy the https:// URL from the ngrok output.${RESET}"
echo ""
echo -e "To use with a Pipecat bot:"
echo -e "  Set DAILY_ROOM_URL or your transport webhook URL to the ngrok https URL."
echo ""
echo -e "To use with a LiveKit agent:"
echo -e "  Set the LIVEKIT_URL env var to point to your LiveKit server."
echo -e "  The agent connects outbound — no ngrok needed for LiveKit."
echo ""
echo -e "To call the WebSocket endpoint directly:"
echo -e "  Replace wss://speech-to-speech.us.assemblyai.com with your ngrok WSS URL"
echo -e "  (ngrok provides a wss:// forwarding URL when you use 'ngrok http')."
echo ""

ngrok http "${PORT}"
