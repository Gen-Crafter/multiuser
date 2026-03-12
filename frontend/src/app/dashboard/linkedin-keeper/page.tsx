'use client';

import { useState, useEffect } from 'react';

export default function LinkedInKeeperPage() {
  const [status, setStatus] = useState('Idle');
  const [error, setError] = useState(false);
  const [keeperApi, setKeeperApi] = useState('');
  const [vncUrl, setVncUrl] = useState('');

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const hostname = window.location.hostname;
      const protocol = window.location.protocol;
      setKeeperApi(`${protocol}//${hostname}:3001`);
      setVncUrl(`http://${hostname}:6080/vnc.html?autoconnect=1&resize=scale`);
    }
  }, []);

  const startAutomation = async () => {
    setStatus('Starting...');
    setError(false);
    try {
      const res = await fetch(`${keeperApi}/start`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to start');
      setStatus(data.message || 'Session active');
    } catch (err: any) {
      setStatus(`Error: ${err.message}`);
      setError(true);
    }
  };

  const clearSession = async () => {
    setStatus('Clearing session...');
    setError(false);
    try {
      const res = await fetch(`${keeperApi}/clear`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to clear');
      setStatus(data.message || 'Session cleared.');
    } catch (err: any) {
      setStatus(`Error: ${err.message}`);
      setError(true);
    }
  };

  const openVNC = () => {
    window.open(vncUrl, '_blank', 'noopener');
  };

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold mb-2">LinkedIn Session Keeper</h1>
        <p className="text-gray-600">
          Launch the Playwright automation that saves and reuses your LinkedIn session. 
          On the first run it opens headfully so you can log in manually.
        </p>
      </div>

      <div className="card p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">How it works</h2>
        <ul className="list-disc list-inside space-y-2 text-gray-700">
          <li>First run: click start, a browser opens — log in to LinkedIn and reach your feed.</li>
          <li>Next runs: session is reused; feed loads headless and stays alive with refreshes.</li>
          <li>Use the VNC console to view and interact with the browser during login.</li>
        </ul>
      </div>

      <div className="card p-6">
        <div className="flex gap-3 mb-4 flex-wrap">
          <button onClick={startAutomation} className="btn-primary">
            Start Automation
          </button>
          <button onClick={openVNC} className="btn-secondary">
            Open Browser Console (noVNC)
          </button>
          <button onClick={clearSession} className="btn-secondary">
            Clear Saved Session
          </button>
        </div>

        <div className={`p-4 rounded-lg font-mono text-sm whitespace-pre-line ${
          error ? 'bg-red-50 text-red-700 border border-red-200' : 'bg-gray-50 text-gray-700 border border-gray-200'
        }`}>
          {status}
        </div>
      </div>

      <div className="card p-6 mt-6">
        <h2 className="text-lg font-semibold mb-4">Session Status</h2>
        <p className="text-gray-600">
          Once the session is active, it will automatically keep your LinkedIn session alive 
          with periodic refreshes every 20 minutes. The saved session will be used for all 
          campaign automation tasks.
        </p>
      </div>
    </div>
  );
}
