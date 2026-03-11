/**
 * Custom Next.js server with WebSocket proxy.
 *
 * Why: Browsers cannot send custom headers (e.g. Authorization) on WebSocket
 * connections. AssemblyAI S2S requires `Authorization: Bearer <key>`. This
 * server-side proxy sits between the browser and AssemblyAI, adding the
 * header before forwarding — keeping the API key server-side only.
 *
 * Usage:
 *   dev:   npm run dev   (uses tsx for hot reload)
 *   prod:  npm run build && npm start
 *
 * Deploy to Railway or Render (not Vercel — serverless doesn't support
 * long-lived WebSocket connections).
 */

import "dotenv/config";
import { createServer } from "http";
import { parse } from "url";
import next from "next";
import { WebSocketServer, WebSocket } from "ws";
import type { IncomingMessage } from "http";
import type { Duplex } from "stream";

const dev = process.env.NODE_ENV !== "production";
const port = parseInt(process.env.PORT ?? "3000", 10);
const app = next({ dev });
const handle = app.getRequestHandler();

const AAI_URL =
  process.env.ASSEMBLYAI_REALTIME_URL ??
  "wss://speech-to-speech.us.assemblyai.com/v1/realtime";
const AAI_KEY = process.env.ASSEMBLYAI_API_KEY ?? "";

app.prepare().then(() => {
  const server = createServer((req, res) => {
    const parsedUrl = parse(req.url!, true);
    handle(req, res, parsedUrl);
  });

  // WebSocket proxy — browser connects to /ws, we forward to AssemblyAI
  const wss = new WebSocketServer({ noServer: true });

  server.on(
    "upgrade",
    (req: IncomingMessage, socket: Duplex, head: Buffer) => {
      const { pathname } = parse(req.url ?? "");
      if (pathname !== "/ws") {
        socket.destroy();
        return;
      }
      wss.handleUpgrade(req, socket, head, (browserWs) => {
        wss.emit("connection", browserWs, req);
      });
    }
  );

  wss.on("connection", (browserWs: WebSocket) => {
    if (!AAI_KEY) {
      browserWs.send(
        JSON.stringify({ type: "session.error", message: "ASSEMBLYAI_API_KEY not set on server." })
      );
      browserWs.close();
      return;
    }

    const aaiWs = new WebSocket(AAI_URL, {
      headers: { Authorization: `Bearer ${AAI_KEY}` },
    });

    aaiWs.on("open", () => {
      console.log("[proxy] Connected to AssemblyAI S2S");
    });

    // Browser → AssemblyAI
    browserWs.on("message", (data) => {
      if (aaiWs.readyState === WebSocket.OPEN) {
        aaiWs.send(data);
      }
    });

    // AssemblyAI → Browser
    aaiWs.on("message", (data) => {
      if (browserWs.readyState === WebSocket.OPEN) {
        browserWs.send(data);
      }
    });

    aaiWs.on("close", (code, reason) => {
      console.log(`[proxy] AssemblyAI closed: ${code}`);
      if (browserWs.readyState === WebSocket.OPEN) browserWs.close(code, reason);
    });

    aaiWs.on("error", (err) => {
      console.error("[proxy] AssemblyAI error:", err.message);
      browserWs.send(JSON.stringify({ type: "session.error", message: err.message }));
      browserWs.close();
    });

    browserWs.on("close", () => {
      if (aaiWs.readyState === WebSocket.OPEN) aaiWs.close();
    });

    browserWs.on("error", (err) => {
      console.error("[proxy] Browser WS error:", err.message);
      aaiWs.close();
    });
  });

  server.listen(port, () => {
    console.log(`> Ready on http://localhost:${port}`);
    console.log(`> WebSocket proxy at ws://localhost:${port}/ws`);
  });
});
