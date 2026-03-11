#!/usr/bin/env bash
# setup.sh — Install dependencies for all Python examples using uv.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

GREEN="\033[92m"
YELLOW="\033[93m"
RED="\033[91m"
BLUE="\033[94m"
RESET="\033[0m"
BOLD="\033[1m"

echo -e "${BOLD}AssemblyAI S2S Examples — Setup${RESET}"
echo -e "${YELLOW}Installing dependencies for all Python examples...${RESET}\n"

# Check that uv is available
if ! command -v uv &>/dev/null; then
  echo -e "${RED}Error: uv is not installed.${RESET}"
  echo "Install it with:  pip install uv"
  echo "Or:               curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

install_pyproject() {
  local dir="$1"
  local name="$2"
  echo -e "${BLUE}[$name]${RESET} Installing from pyproject.toml..."
  (cd "$dir" && uv sync) && echo -e "${GREEN}[$name] Done.${RESET}\n" || \
    echo -e "${RED}[$name] Failed — check errors above.${RESET}\n"
}

install_requirements() {
  local dir="$1"
  local name="$2"
  echo -e "${BLUE}[$name]${RESET} Installing from requirements.txt..."
  (cd "$dir" && uv pip install --system -r requirements.txt) && \
    echo -e "${GREEN}[$name] Done.${RESET}\n" || \
    echo -e "${RED}[$name] Failed — check errors above.${RESET}\n"
}

# Pipecat examples
install_pyproject "$REPO_ROOT/pipecat/01-basic-agent"          "pipecat/01-basic-agent"
install_pyproject "$REPO_ROOT/pipecat/02-lead-capture-agent"   "pipecat/02-lead-capture-agent"

# LiveKit examples
install_pyproject "$REPO_ROOT/livekit/01-basic-agent"          "livekit/01-basic-agent"
install_pyproject "$REPO_ROOT/livekit/02-onboarding-agent"     "livekit/02-onboarding-agent"

# WebSocket examples
install_requirements "$REPO_ROOT/websocket/python"             "websocket/python"

# Tool calling examples
install_requirements "$REPO_ROOT/tool-calling"                 "tool-calling"

echo -e "${BOLD}${GREEN}All Python dependencies installed.${RESET}"
echo -e "\nNext steps:"
echo "  1. Copy .env.example → .env in each example directory"
echo "  2. Add your ASSEMBLYAI_API_KEY"
echo "  3. Run an example, e.g.: cd pipecat/01-basic-agent && uv run bot.py"
