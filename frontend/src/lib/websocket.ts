import type { WSMessage } from '@/types';

const WS_BASE =
  process.env.NEXT_PUBLIC_WS_URL ||
  (typeof window !== 'undefined'
    ? `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`
    : 'ws://localhost:8000/ws');

type WSCallback = (msg: WSMessage) => void;

class WebSocketClient {
  private ws: WebSocket | null = null;
  private listeners: Set<WSCallback> = new Set();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay = 2000;
  private maxReconnectDelay = 30000;

  connect(token: string) {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    this.ws = new WebSocket(`${WS_BASE}?token=${token}`);

    this.ws.onopen = () => {
      this.reconnectDelay = 2000;
      console.log('[WS] Connected');
    };

    this.ws.onmessage = (event) => {
      try {
        const data: WSMessage = JSON.parse(event.data);
        this.listeners.forEach((cb) => cb(data));
      } catch {
        // raw text (e.g. pong)
      }
    };

    this.ws.onclose = () => {
      console.log('[WS] Disconnected, reconnecting...');
      this.scheduleReconnect(token);
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };

    // Keepalive ping every 30s
    const pingInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send('ping');
      } else {
        clearInterval(pingInterval);
      }
    }, 30000);
  }

  private scheduleReconnect(token: string) {
    if (this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, this.maxReconnectDelay);
      this.connect(token);
    }, this.reconnectDelay);
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  subscribe(cb: WSCallback) {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }
}

export const wsClient = new WebSocketClient();
