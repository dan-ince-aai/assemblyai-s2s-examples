# Deployment Options

Every Python server in this repo (`phone/server.py`, websocket examples) can be deployed to any platform that runs Docker or Python.

## Railway (recommended for phone/server.py)

Railway is the fastest path to a public HTTPS URL with zero infrastructure setup.

```bash
npm i -g @railway/cli
railway login
cd phone && railway init && railway up
# Set env vars in the Railway dashboard -> Variables tab
```

The `railway.json` in this folder configures the build and start commands. Copy it into your service directory if Railway doesn't detect the settings automatically.

## Render

1. Push this repo to GitHub
2. Go to render.com -> New -> Web Service
3. Connect your repo and select the folder (e.g. `phone/`)
4. Build command: `pip install -r requirements.txt`
5. Start command: `uvicorn server:app --host 0.0.0.0 --port $PORT`
6. Add env vars in the Render dashboard

The `render.yaml` in this folder can be placed at the repo root to enable one-click Render deploys.

## Vercel (Next.js frontend only)

See `nextjs-frontend/README.md` for full instructions.

```bash
cd nextjs-frontend
npm i -g vercel
vercel login
vercel --prod
```

## Pipecat Cloud

See `pipecat/README.md` for full instructions.

```bash
pip install pipecat-ai[cloud]
uv run pipecat cloud auth login
uv run pipecat cloud secrets set assemblyai-secrets --file .env
uv run pipecat cloud docker build-push
uv run pipecat cloud deploy
```

## LiveKit Cloud

See `livekit/README.md` for full instructions.

```bash
brew install livekit-cli
lk cloud auth
lk agent create
```

## Fly.io

```bash
fly auth login
fly launch
fly deploy
```

## Docker (any VPS)

```bash
docker build -t assemblyai-voice-agent .
docker run -p 8080:8080 --env-file .env assemblyai-voice-agent
```
