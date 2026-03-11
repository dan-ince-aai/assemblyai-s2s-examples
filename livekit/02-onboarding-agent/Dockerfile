FROM python:3.12-slim

# Install uv
RUN pip install uv

WORKDIR /app

# Copy plugin dependency
COPY ../plugin/assemblyai_realtime.py /app/assemblyai_realtime.py

# Copy agent files
COPY . .

# Install dependencies
RUN uv pip install --system livekit-agents[silero,turn-detector]~=1.3 \
    livekit-plugins-noise-cancellation~=0.2 \
    python-dotenv \
    aiohttp

CMD ["python", "agent.py", "start"]
