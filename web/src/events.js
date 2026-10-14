import { request } from './api.js';
import { parseSSE } from './data.js';

export function connectEvents({ onStatus, onRevision }) {
  let stopped = false; let controller; let timer; let wake; let attempt = 0;
  const delays = [1000, 2000, 5000, 10000];
  const wait = ms => new Promise(resolve => { wake = resolve; timer = setTimeout(resolve, ms); });
  async function run() {
    while (!stopped) {
      controller = new AbortController();
      onStatus(attempt ? 'reconnecting' : 'connecting');
      try {
        const response = await request('events', { signal: controller.signal, headers: { Accept: 'text/event-stream' } });
        if (!(response instanceof Response) || !response.body) throw new Error('SSE недоступен');
        onStatus('connected');
        const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
        try {
          while (!stopped) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const parsed = parseSSE(buffer); buffer = parsed.rest;
            for (const event of parsed.events) {
              attempt = 0;
              if (event.type === 'revision') {
                try { onRevision(JSON.parse(event.data)); } catch { /* malformed event must not crash UI */ }
              }
            }
          }
        } finally { reader.releaseLock(); }
        if (!stopped) throw new Error('Поток событий прерван');
      } catch (error) {
        if (stopped || error.name === 'AbortError') break;
        onStatus('offline');
        await wait(delays[Math.min(attempt++, delays.length - 1)]);
      }
    }
  }
  run();
  return () => { stopped = true; controller?.abort(); clearTimeout(timer); wake?.(); };
}
