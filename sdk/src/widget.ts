/**
 * AssemblyAI S2S — Embeddable Voice Widget
 *
 * Drop one line into any page:
 *   <script src="https://cdn.jsdelivr.net/gh/dan-ince-aai/assemblyai-s2s-examples@main/sdk/dist/widget.js"
 *           data-proxy="wss://your-proxy.railway.app"
 *           data-prompt="You are a helpful assistant.">
 *   </script>
 */

import { AssemblyAIS2S, AgentState } from './client';

const scriptEl = (document.currentScript ?? findScript()) as HTMLScriptElement | null;
const proxyUrl  = scriptEl?.dataset?.proxy  ?? '';
const prompt    = scriptEl?.dataset?.prompt;
const position  = (scriptEl?.dataset?.position ?? 'bottom-right') as string;

if (!proxyUrl) {
  console.warn('[aai-widget] Missing data-proxy on <script> tag.');
}

function findScript(): HTMLScriptElement | null {
  for (const s of document.querySelectorAll<HTMLScriptElement>('script[src]')) {
    if (s.src.includes('widget')) return s;
  }
  return null;
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const positionCss = position.includes('left')
  ? 'left: 24px; right: auto;'
  : 'right: 24px;';
const bubbleAlignCss = position.includes('left')
  ? 'align-items: flex-start;'
  : 'align-items: flex-end;';

const CSS = `
  #aai-root {
    position: fixed;
    bottom: 24px;
    ${positionCss}
    z-index: 2147483647;
    display: flex;
    flex-direction: column;
    ${bubbleAlignCss}
    gap: 12px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    pointer-events: none;
  }

  #aai-bubble {
    pointer-events: none;
    max-width: 240px;
    padding: 10px 14px;
    border-radius: 16px;
    font-size: 13px;
    line-height: 1.5;
    color: #fff;
    background: rgba(15, 15, 20, 0.85);
    backdrop-filter: blur(12px) saturate(180%);
    -webkit-backdrop-filter: blur(12px) saturate(180%);
    border: 1px solid rgba(255,255,255,0.09);
    box-shadow: 0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.07);
    opacity: 0;
    transform: translateY(8px) scale(0.97);
    transition: opacity 0.22s cubic-bezier(.4,0,.2,1),
                transform 0.22s cubic-bezier(.4,0,.2,1);
    word-break: break-word;
  }

  #aai-bubble.show {
    opacity: 1;
    transform: translateY(0) scale(1);
  }

  #aai-bubble .aai-label {
    display: block;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-bottom: 3px;
    opacity: 0.5;
  }

  #aai-btn-wrap {
    pointer-events: all;
    position: relative;
    width: 60px;
    height: 60px;
    flex-shrink: 0;
  }

  /* Outer glow ring — animated per state */
  #aai-ring {
    position: absolute;
    inset: -5px;
    border-radius: 50%;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.3s ease;
  }

  #aai-btn-wrap.listening  #aai-ring { opacity: 1; animation: aai-glow-green  1.6s ease-in-out infinite; }
  #aai-btn-wrap.speaking   #aai-ring { opacity: 1; animation: aai-glow-blue   1.1s ease-in-out infinite; }
  #aai-btn-wrap.connecting #aai-ring { opacity: 1; animation: aai-glow-amber  2s   ease-in-out infinite; }

  @keyframes aai-glow-green {
    0%,100% { box-shadow: 0 0 0 0 rgba(52,211,153,0.0), 0 0 0 3px rgba(52,211,153,0.25); }
    50%      { box-shadow: 0 0 0 10px rgba(52,211,153,0.0), 0 0 0 3px rgba(52,211,153,0.5); }
  }
  @keyframes aai-glow-blue {
    0%,100% { box-shadow: 0 0 0 0 rgba(99,179,255,0.0),  0 0 0 3px rgba(99,179,255,0.3); }
    50%      { box-shadow: 0 0 0 12px rgba(99,179,255,0.0), 0 0 0 3px rgba(99,179,255,0.6); }
  }
  @keyframes aai-glow-amber {
    0%,100% { box-shadow: 0 0 0 0 rgba(251,191,36,0.0),  0 0 0 3px rgba(251,191,36,0.2); }
    50%      { box-shadow: 0 0 0 8px rgba(251,191,36,0.0),  0 0 0 3px rgba(251,191,36,0.45); }
  }

  #aai-btn {
    width: 60px;
    height: 60px;
    border-radius: 50%;
    border: none;
    cursor: pointer;
    outline: none;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    overflow: hidden;
    -webkit-tap-highlight-color: transparent;
    user-select: none;

    /* Glossy dark gradient */
    background: linear-gradient(145deg, #1e1e2e 0%, #16161f 60%, #0f0f18 100%);
    box-shadow:
      0 4px 6px -1px rgba(0,0,0,0.5),
      0 10px 30px -5px rgba(0,0,0,0.6),
      inset 0 1px 0 rgba(255,255,255,0.1),
      inset 0 -1px 0 rgba(0,0,0,0.3);

    transition: transform 0.15s cubic-bezier(.4,0,.2,1),
                box-shadow  0.15s cubic-bezier(.4,0,.2,1);
  }

  /* Subtle shimmer layer */
  #aai-btn::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: 50%;
    background: radial-gradient(ellipse at 35% 25%, rgba(255,255,255,0.12) 0%, transparent 65%);
    pointer-events: none;
  }

  /* Listening: green tint overlay */
  #aai-btn-wrap.listening  #aai-btn { box-shadow: 0 4px 6px -1px rgba(0,0,0,0.5), 0 10px 30px -5px rgba(0,0,0,0.6), 0 0 0 1px rgba(52,211,153,0.3), inset 0 1px 0 rgba(255,255,255,0.1); }
  /* Speaking: blue tint overlay */
  #aai-btn-wrap.speaking   #aai-btn { box-shadow: 0 4px 6px -1px rgba(0,0,0,0.5), 0 10px 30px -5px rgba(0,0,0,0.6), 0 0 0 1px rgba(99,179,255,0.3), inset 0 1px 0 rgba(255,255,255,0.1); }

  #aai-btn:hover  { transform: scale(1.07); box-shadow: 0 6px 10px -1px rgba(0,0,0,0.55), 0 16px 40px -5px rgba(0,0,0,0.65), inset 0 1px 0 rgba(255,255,255,0.12); }
  #aai-btn:active { transform: scale(0.95); }

  #aai-btn svg {
    width: 26px;
    height: 26px;
    fill: rgba(255,255,255,0.92);
    filter: drop-shadow(0 1px 2px rgba(0,0,0,0.5));
    pointer-events: none;
    transition: transform 0.2s ease, opacity 0.15s ease;
  }

  #aai-btn-wrap.speaking #aai-btn svg {
    opacity: 0.75;
  }

  /* Waveform bars (shown when speaking) */
  #aai-bars {
    display: flex;
    align-items: center;
    gap: 3px;
    position: absolute;
    opacity: 0;
    transition: opacity 0.2s ease;
  }
  #aai-btn-wrap.speaking #aai-bars  { opacity: 1; }
  #aai-btn-wrap.speaking #aai-btn svg { opacity: 0; }

  #aai-bars span {
    display: block;
    width: 3px;
    border-radius: 2px;
    background: rgba(255,255,255,0.85);
    animation: aai-bar 1s ease-in-out infinite;
  }
  #aai-bars span:nth-child(1) { height: 8px;  animation-delay: 0s; }
  #aai-bars span:nth-child(2) { height: 16px; animation-delay: 0.15s; }
  #aai-bars span:nth-child(3) { height: 22px; animation-delay: 0.05s; }
  #aai-bars span:nth-child(4) { height: 16px; animation-delay: 0.2s; }
  #aai-bars span:nth-child(5) { height: 8px;  animation-delay: 0.1s; }

  @keyframes aai-bar {
    0%,100% { transform: scaleY(0.4); opacity: 0.6; }
    50%      { transform: scaleY(1.0); opacity: 1.0; }
  }

  /* Tooltip */
  #aai-tooltip {
    position: absolute;
    bottom: calc(100% + 10px);
    ${position.includes('left') ? 'left: 0;' : 'right: 0;'}
    background: rgba(10,10,15,0.9);
    backdrop-filter: blur(8px);
    color: rgba(255,255,255,0.8);
    font-size: 11px;
    font-weight: 500;
    white-space: nowrap;
    padding: 5px 10px;
    border-radius: 8px;
    pointer-events: none;
    opacity: 0;
    transform: translateY(4px);
    transition: opacity 0.15s ease, transform 0.15s ease;
    border: 1px solid rgba(255,255,255,0.07);
  }
  #aai-btn-wrap:hover #aai-tooltip { opacity: 1; transform: translateY(0); }
`;

// ─── SVG icons ───────────────────────────────────────────────────────────────

const ICON_MIC = `<svg viewBox="0 0 24 24"><path d="M12 2a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3zm-1 15.93V20H8v2h8v-2h-3v-2.07A7 7 0 0 0 19 11h-2a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.93z"/></svg>`;
const ICON_STOP = `<svg viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2.5"/></svg>`;
const BARS_HTML = `<div id="aai-bars">${'<span></span>'.repeat(5)}</div>`;

// ─── Mount ────────────────────────────────────────────────────────────────────

function mount(): void {
  const style = document.createElement('style');
  style.textContent = CSS;
  document.head.appendChild(style);

  const root = document.createElement('div');
  root.id = 'aai-root';

  const bubble = document.createElement('div');
  bubble.id = 'aai-bubble';
  bubble.innerHTML = '<span class="aai-label"></span><span class="aai-text"></span>';

  const wrap = document.createElement('div');
  wrap.id = 'aai-btn-wrap';

  const ring = document.createElement('div');
  ring.id = 'aai-ring';

  const btn = document.createElement('button');
  btn.id = 'aai-btn';
  btn.setAttribute('aria-label', 'Start voice assistant');
  btn.innerHTML = ICON_MIC + BARS_HTML;

  const tooltip = document.createElement('div');
  tooltip.id = 'aai-tooltip';
  tooltip.textContent = 'Talk to AI';

  wrap.append(ring, btn, tooltip);
  root.append(bubble, wrap);
  document.body.appendChild(root);

  // ─── Agent ──────────────────────────────────────────────────────────────

  const agent = new AssemblyAIS2S({
    proxyUrl,
    systemPrompt: prompt,
    onStateChange: (s) => applyState(wrap, btn, tooltip, s),
    onTranscript: (text, isFinal) => {
      if (text.trim()) showBubble(bubble, 'You', text, isFinal ? 4500 : 0);
    },
    onAgentText: (text) => {
      if (text.trim()) showBubble(bubble, 'Assistant', text, 5500);
    },
    onError: (err) => showBubble(bubble, 'Error', err.message, 5000),
  });

  let active = false;

  btn.addEventListener('click', async () => {
    if (!active) {
      active = true;
      tooltip.textContent = 'Stop';
      try { await agent.start(); } catch { active = false; tooltip.textContent = 'Talk to AI'; }
    } else {
      agent.stop();
      active = false;
      hideBubble(bubble);
    }
  });

  // Reset when agent stops itself (e.g. on error)
  agent.addEventListener('statechange', (e) => {
    const s = (e as CustomEvent<AgentState>).detail;
    if (s === 'idle') {
      active = false;
      setIcon(btn, ICON_MIC);
      tooltip.textContent = 'Talk to AI';
      btn.setAttribute('aria-label', 'Start voice assistant');
    } else {
      setIcon(btn, ICON_STOP);
      btn.setAttribute('aria-label', 'Stop voice assistant');
    }
  });
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function applyState(wrap: HTMLElement, _btn: HTMLButtonElement, tooltip: HTMLElement, state: AgentState): void {
  wrap.className = '';
  if (state !== 'idle') wrap.classList.add(state);
  const labels: Record<AgentState, string> = {
    idle: 'Talk to AI',
    connecting: 'Connecting…',
    listening: 'Listening…',
    speaking: 'Speaking…',
  };
  tooltip.textContent = labels[state];
}

let hideTimer: ReturnType<typeof setTimeout> | null = null;

function showBubble(el: HTMLElement, label: string, text: string, autohideMs: number): void {
  (el.querySelector('.aai-label') as HTMLElement).textContent = label;
  (el.querySelector('.aai-text') as HTMLElement).textContent = text;
  el.classList.add('show');
  if (hideTimer) clearTimeout(hideTimer);
  if (autohideMs > 0) hideTimer = setTimeout(() => hideBubble(el), autohideMs);
}

function hideBubble(el: HTMLElement): void {
  el.classList.remove('show');
  if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
}

function setIcon(btn: HTMLButtonElement, svg: string): void {
  const old = btn.querySelector('svg');
  if (old) old.remove();
  const tmp = document.createElement('div');
  tmp.innerHTML = svg;
  btn.insertBefore(tmp.firstElementChild!, btn.firstChild);
}

// ─── Auto-mount ───────────────────────────────────────────────────────────────

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', mount);
} else {
  mount();
}
