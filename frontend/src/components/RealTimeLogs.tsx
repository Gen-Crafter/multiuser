'use client';

import { useEffect, useRef, useState } from 'react';
import { wsClient } from '@/lib/websocket';
import type { WSMessage } from '@/types';

export default function RealTimeLogs() {
  const [logs, setLogs] = useState<WSMessage[]>([]);
  const [connected, setConnected] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) return;

    wsClient.connect(token);
    setConnected(true);

    const unsub = wsClient.subscribe((msg) => {
      setLogs((prev) => [...prev.slice(-99), msg]);
    });

    return () => {
      unsub();
      wsClient.disconnect();
      setConnected(false);
    };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const typeColors: Record<string, string> = {
    log: 'text-gray-400',
    campaign_update: 'text-blue-400',
    alert: 'text-yellow-400',
    metric: 'text-green-400',
  };

  return (
    <div className="card">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900">Real-Time Logs</h3>
        <span className={`badge ${connected ? 'badge-green' : 'badge-red'}`}>
          {connected ? 'Connected' : 'Disconnected'}
        </span>
      </div>
      <div className="h-64 overflow-y-auto rounded-lg bg-gray-900 p-3 font-mono text-xs">
        {logs.length === 0 && (
          <p className="text-gray-500">Waiting for events...</p>
        )}
        {logs.map((log, i) => (
          <div key={i} className="mb-1">
            <span className="text-gray-500">{new Date(log.timestamp).toLocaleTimeString()}</span>{' '}
            <span className={typeColors[log.type] || 'text-gray-400'}>[{log.type}]</span>{' '}
            <span className="text-gray-300">{JSON.stringify(log.payload)}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
