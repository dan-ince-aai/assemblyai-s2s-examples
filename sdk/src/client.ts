export type AgentState = 'idle' | 'connecting' | 'listening' | 'speaking';

export interface AssemblyAIS2SOptions {
  /** WebSocket URL of the proxy server, e.g. wss://my-proxy.railway.app or /ws */
  proxyUrl: string;
  /** System prompt sent after session.ready */
  systemPrompt?: string;
  /** Tool schemas to register with the agent */
  tools?: object[];
  onStateChange?: (state: AgentState) => void;
  onTranscript?: (text: string, isFinal: boolean) => void;
  onAgentText?: (text: string) => void;
  onError?: (error: Error) => void;
}

interface CustomEventMap {
  statechange: CustomEvent<AgentState>;
  transcript: CustomEvent<{ text: string; isFinal: boolean }>;
  agenttext: CustomEvent<{ text: string }>;
  toolcall: CustomEvent<{ callId: string; name: string; args: object }>;
  error: CustomEvent<Error>;
}

export class AssemblyAIS2S extends EventTarget {
  private options: AssemblyAIS2SOptions;
  private _state: AgentState = 'idle';
  private ws: WebSocket | null = null;
  private audioContext: AudioContext | null = null;
  private mediaStream: MediaStream | null = null;
  private scriptProcessor: ScriptProcessorNode | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  /** Queue of audio buffers to play in order */
  private playbackQueue: AudioBuffer[] = [];
  private isPlaying = false;
  private nextPlayTime = 0;

  constructor(options: AssemblyAIS2SOptions) {
    super();
    this.options = options;
  }

  get state(): AgentState {
    return this._state;
  }

  private setState(state: AgentState): void {
    if (this._state === state) return;
    this._state = state;
    this.options.onStateChange?.(state);
    this.dispatchEvent(
      new CustomEvent('statechange', { detail: state }) as CustomEventMap['statechange'],
    );
  }

  async start(): Promise<void> {
    if (this._state !== 'idle') return;
    this.setState('connecting');

    try {
      // 1. Request microphone
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });

      // 2. Set up AudioContext at 24 kHz to match AssemblyAI S2S
      this.audioContext = new AudioContext({ sampleRate: 24000 });

      // 3. Open WebSocket to proxy
      const url = this.resolveUrl(this.options.proxyUrl);
      this.ws = new WebSocket(url);
      this.ws.binaryType = 'arraybuffer';

      this.ws.addEventListener('open', () => {
        this.startMicCapture();
      });

      this.ws.addEventListener('message', (event) => {
        this.handleMessage(event);
      });

      this.ws.addEventListener('close', () => {
        this.cleanup();
      });

      this.ws.addEventListener('error', () => {
        const err = new Error('WebSocket connection failed');
        this.options.onError?.(err);
        this.dispatchEvent(new CustomEvent('error', { detail: err }));
        this.cleanup();
      });
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      this.options.onError?.(error);
      this.dispatchEvent(new CustomEvent('error', { detail: error }));
      this.cleanup();
      throw error;
    }
  }

  stop(): void {
    this.cleanup();
  }

  /**
   * Send a tool result back to the agent after handling a toolcall event.
   */
  sendToolResult(callId: string, result: unknown): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(
      JSON.stringify({
        type: 'tool.result',
        call_id: callId,
        result,
      }),
    );
  }

  // ─── Private ──────────────────────────────────────────────────────────────

  private resolveUrl(proxyUrl: string): string {
    // Allow relative paths like /ws — convert to ws(s):// using current origin
    if (proxyUrl.startsWith('/')) {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      return `${proto}://${location.host}${proxyUrl}`;
    }
    return proxyUrl;
  }

  private startMicCapture(): void {
    if (!this.audioContext || !this.mediaStream) return;

    this.sourceNode = this.audioContext.createMediaStreamSource(this.mediaStream);

    // ScriptProcessorNode gives us raw Float32 PCM frames
    // bufferSize 4096 is a safe cross-browser choice
    // eslint-disable-next-line deprecation/deprecation
    this.scriptProcessor = this.audioContext.createScriptProcessor(4096, 1, 1);

    this.scriptProcessor.onaudioprocess = (event) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;

      const float32 = event.inputBuffer.getChannelData(0);
      const int16 = float32ToInt16(float32);
      const base64 = arrayBufferToBase64(int16.buffer);

      this.ws.send(
        JSON.stringify({
          type: 'input.audio',
          audio: base64,
        }),
      );
    };

    this.sourceNode.connect(this.scriptProcessor);
    // Connect to destination to keep the graph alive (output is silent)
    this.scriptProcessor.connect(this.audioContext.destination);
  }

  private handleMessage(event: MessageEvent): void {
    let msg: Record<string, unknown>;
    try {
      msg = JSON.parse(event.data as string) as Record<string, unknown>;
    } catch {
      return;
    }

    const type = msg.type as string;

    switch (type) {
      case 'session.ready': {
        // Optionally configure the session with a system prompt / tools
        if (this.options.systemPrompt || this.options.tools?.length) {
          const session: Record<string, unknown> = {};
          if (this.options.systemPrompt) session.system_prompt = this.options.systemPrompt;
          if (this.options.tools?.length) session.tools = this.options.tools;
          this.ws?.send(JSON.stringify({ type: 'session.update', session }));
        }
        this.setState('listening');
        break;
      }

      case 'input.speech.started': {
        this.setState('listening');
        break;
      }

      case 'reply.started': {
        this.setState('speaking');
        break;
      }

      case 'reply.audio': {
        const data = msg.data as string | undefined;
        if (data && this.audioContext) {
          this.enqueueAudio(data);
        }
        break;
      }

      case 'transcript.user': {
        const text = (msg.text as string) ?? '';
        const isFinal = (msg.is_final as boolean) ?? false;
        this.options.onTranscript?.(text, isFinal);
        this.dispatchEvent(
          new CustomEvent('transcript', { detail: { text, isFinal } }) as CustomEventMap['transcript'],
        );
        break;
      }

      case 'transcript.agent': {
        const text = (msg.text as string) ?? '';
        this.options.onAgentText?.(text);
        this.dispatchEvent(
          new CustomEvent('agenttext', { detail: { text } }) as CustomEventMap['agenttext'],
        );
        break;
      }

      case 'reply.done': {
        this.setState('listening');
        break;
      }

      case 'tool.call': {
        const callId = (msg.call_id as string) ?? '';
        const name = (msg.name as string) ?? '';
        const args = (msg.args as object) ?? {};
        this.dispatchEvent(
          new CustomEvent('toolcall', {
            detail: { callId, name, args },
          }) as CustomEventMap['toolcall'],
        );
        break;
      }

      case 'session.error': {
        const message = (msg.message as string) ?? 'Session error';
        const err = new Error(message);
        this.options.onError?.(err);
        this.dispatchEvent(new CustomEvent('error', { detail: err }));
        break;
      }

      default:
        break;
    }
  }

  /**
   * Decode base64 PCM16 audio and schedule it for seamless playback.
   */
  private enqueueAudio(base64: string): void {
    if (!this.audioContext) return;

    const binary = base64ToArrayBuffer(base64);
    const int16 = new Int16Array(binary);
    const float32 = int16ToFloat32(int16);

    const buffer = this.audioContext.createBuffer(1, float32.length, 24000);
    buffer.copyToChannel(float32, 0);

    this.playbackQueue.push(buffer);
    if (!this.isPlaying) {
      this.drainQueue();
    }
  }

  private drainQueue(): void {
    if (!this.audioContext || this.playbackQueue.length === 0) {
      this.isPlaying = false;
      return;
    }

    this.isPlaying = true;
    const buffer = this.playbackQueue.shift()!;
    const source = this.audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(this.audioContext.destination);

    const now = this.audioContext.currentTime;
    // Schedule at least 10ms in the future for the first chunk; chain subsequent ones
    const startAt = Math.max(now + 0.01, this.nextPlayTime);
    source.start(startAt);
    this.nextPlayTime = startAt + buffer.duration;

    source.onended = () => {
      this.drainQueue();
    };
  }

  private cleanup(): void {
    // Stop mic tracks
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((t) => t.stop());
      this.mediaStream = null;
    }

    // Disconnect audio graph
    if (this.scriptProcessor) {
      this.scriptProcessor.disconnect();
      this.scriptProcessor.onaudioprocess = null;
      this.scriptProcessor = null;
    }
    if (this.sourceNode) {
      this.sourceNode.disconnect();
      this.sourceNode = null;
    }
    if (this.audioContext) {
      this.audioContext.close().catch(() => {});
      this.audioContext = null;
    }

    // Close WebSocket
    if (this.ws) {
      if (
        this.ws.readyState === WebSocket.OPEN ||
        this.ws.readyState === WebSocket.CONNECTING
      ) {
        this.ws.close();
      }
      this.ws = null;
    }

    // Reset playback state
    this.playbackQueue = [];
    this.isPlaying = false;
    this.nextPlayTime = 0;

    this.setState('idle');
  }
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function float32ToInt16(float32: Float32Array): Int16Array {
  const int16 = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const clamped = Math.max(-1, Math.min(1, float32[i]));
    int16[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  }
  return int16;
}

function int16ToFloat32(int16: Int16Array): Float32Array {
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / (int16[i] < 0 ? 0x8000 : 0x7fff);
  }
  return float32;
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}
