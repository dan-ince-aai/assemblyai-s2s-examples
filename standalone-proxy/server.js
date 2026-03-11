'use strict';

require('dotenv').config();

const http = require('http');
const { WebSocket, WebSocketServer } = require('ws');

const PORT = parseInt(process.env.PORT || '8080', 10);
const AAI_URL =
  process.env.ASSEMBLYAI_REALTIME_URL ||
  'wss://speech-to-speech.us.assemblyai.com/v1/realtime';
const AAI_KEY = process.env.ASSEMBLYAI_API_KEY || '';

// Optional: comma-separated list of allowed origins, e.g. "https://myapp.com,https://staging.myapp.com"
// If not set, all origins are permitted.
const ALLOWED_ORIGINS = process.env.ALLOWED_ORIGINS
  ? process.env.ALLOWED_ORIGINS.split(',').map((o) => o.trim())
  : null;

if (!AAI_KEY) {
  console.warn(
    '[proxy] WARNING: ASSEMBLYAI_API_KEY is not set. Connections to AssemblyAI will be rejected.',
  );
}

// ─── Connection tracking ────────────────────────────────────────────────────

let connectionCount = 0;

// ─── HTTP server ─────────────────────────────────────────────────────────────

const httpServer = http.createServer((req, res) => {
  // CORS preflight
  const origin = req.headers.origin || '*';
  if (ALLOWED_ORIGINS && !ALLOWED_ORIGINS.includes(origin)) {
    res.writeHead(403, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Origin not allowed' }));
    return;
  }

  res.setHeader('Access-Control-Allow-Origin', origin);
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Vary', 'Origin');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  if (req.method === 'GET' && (req.url === '/' || req.url === '/health')) {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', connections: connectionCount }));
    return;
  }

  res.writeHead(404, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ error: 'Not found' }));
});

// ─── WebSocket server ────────────────────────────────────────────────────────

const wss = new WebSocketServer({ noServer: true });

httpServer.on('upgrade', (req, socket, head) => {
  // Origin check
  const origin = req.headers.origin || '';
  if (ALLOWED_ORIGINS && origin && !ALLOWED_ORIGINS.includes(origin)) {
    console.log(`[proxy] Rejected connection from origin: ${origin}`);
    socket.write('HTTP/1.1 403 Forbidden\r\n\r\n');
    socket.destroy();
    return;
  }

  wss.handleUpgrade(req, socket, head, (browserWs) => {
    wss.emit('connection', browserWs, req);
  });
});

wss.on('connection', (browserWs, req) => {
  connectionCount++;
  const id = `conn-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  const remoteAddr =
    req.headers['x-forwarded-for']?.toString().split(',')[0].trim() ||
    req.socket.remoteAddress ||
    'unknown';
  console.log(`[proxy] [${id}] Browser connected from ${remoteAddr}. Active: ${connectionCount}`);

  // ── Open upstream connection to AssemblyAI ──────────────────────────────
  const aaiWs = new WebSocket(AAI_URL, {
    headers: {
      Authorization: `Bearer ${AAI_KEY}`,
    },
  });

  let aaiReady = false;
  /** Messages buffered while upstream is still connecting */
  const pendingMessages = [];

  // ── Browser → AssemblyAI ─────────────────────────────────────────────────
  browserWs.on('message', (data) => {
    if (aaiWs.readyState === WebSocket.OPEN) {
      aaiWs.send(data, { binary: Buffer.isBuffer(data) });
    } else if (!aaiReady) {
      // Buffer messages until AssemblyAI connection is established
      pendingMessages.push(data);
    }
    // If aaiWs is closing/closed, silently drop
  });

  browserWs.on('close', (code, reason) => {
    console.log(`[proxy] [${id}] Browser disconnected (${code}). Active: ${--connectionCount}`);
    if (aaiWs.readyState === WebSocket.OPEN || aaiWs.readyState === WebSocket.CONNECTING) {
      aaiWs.close(1000, 'browser closed');
    }
  });

  browserWs.on('error', (err) => {
    console.error(`[proxy] [${id}] Browser WS error:`, err.message);
    if (aaiWs.readyState === WebSocket.OPEN || aaiWs.readyState === WebSocket.CONNECTING) {
      aaiWs.close(1011, 'browser error');
    }
  });

  // ── AssemblyAI → Browser ─────────────────────────────────────────────────
  aaiWs.on('open', () => {
    aaiReady = true;
    console.log(`[proxy] [${id}] Upstream AssemblyAI connected.`);

    // Flush any messages that arrived before upstream was ready
    for (const msg of pendingMessages) {
      aaiWs.send(msg, { binary: Buffer.isBuffer(msg) });
    }
    pendingMessages.length = 0;
  });

  aaiWs.on('message', (data) => {
    if (browserWs.readyState === WebSocket.OPEN) {
      browserWs.send(data, { binary: Buffer.isBuffer(data) });
    }
  });

  aaiWs.on('close', (code, reason) => {
    const reasonStr = reason?.toString() || '';
    console.log(`[proxy] [${id}] Upstream AssemblyAI closed (${code}${reasonStr ? ' ' + reasonStr : ''}).`);
    if (browserWs.readyState === WebSocket.OPEN) {
      // Forward close to browser — use a valid WebSocket close code
      const forwardCode = code >= 1000 && code <= 4999 ? code : 1000;
      browserWs.close(forwardCode, reasonStr);
    }
  });

  aaiWs.on('error', (err) => {
    console.error(`[proxy] [${id}] Upstream AssemblyAI error:`, err.message);
    if (browserWs.readyState === WebSocket.OPEN) {
      // Send a JSON error event so the browser SDK can surface it nicely
      try {
        browserWs.send(
          JSON.stringify({
            type: 'session.error',
            message: `Upstream connection error: ${err.message}`,
          }),
        );
      } catch {
        // ignore if browser already closing
      }
      browserWs.close(1011, 'upstream error');
    }
  });
});

// ─── Start ───────────────────────────────────────────────────────────────────

httpServer.listen(PORT, () => {
  console.log(`[proxy] Listening on port ${PORT}`);
  console.log(`[proxy] Forwarding to: ${AAI_URL}`);
  if (ALLOWED_ORIGINS) {
    console.log(`[proxy] Allowed origins: ${ALLOWED_ORIGINS.join(', ')}`);
  } else {
    console.log('[proxy] All origins permitted (set ALLOWED_ORIGINS to restrict)');
  }
});

// ─── Graceful shutdown ───────────────────────────────────────────────────────

function shutdown(signal) {
  console.log(`\n[proxy] Received ${signal}, shutting down...`);
  wss.clients.forEach((ws) => ws.close(1001, 'server shutting down'));
  httpServer.close(() => {
    console.log('[proxy] Server closed.');
    process.exit(0);
  });
  // Force exit if clients don't close in time
  setTimeout(() => process.exit(0), 5000).unref();
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
