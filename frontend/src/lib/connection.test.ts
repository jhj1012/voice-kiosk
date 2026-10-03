import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { connect } from './connection';

class FakeSocket {
  static OPEN = 1;
  readyState = 0;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  sent: string[] = [];
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.onclose?.();
  }
}

describe('connect', () => {
  let sockets: FakeSocket[];
  const make = () => {
    const s = new FakeSocket();
    sockets.push(s);
    return s as unknown as WebSocket;
  };

  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal('WebSocket', FakeSocket);
    sockets = [];
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('reports "offline" once while retrying, and "connected" when it works', () => {
    const statuses: boolean[] = [];
    connect(
      () => {},
      (ok) => statuses.push(ok),
      { url: 'ws://x/ws', socket: make },
    );
    for (let i = 0; i < 4; i++) {
      sockets.at(-1)!.onclose!(); // the server is not running
      vi.advanceTimersByTime(5000);
    }
    expect(sockets.length).toBe(5);
    expect(statuses).toEqual([false]);
    sockets.at(-1)!.onopen!();
    expect(statuses).toEqual([false, true]);
  });

  it('passes events on and sends only while open', () => {
    const events: unknown[] = [];
    const connection = connect(
      (e) => events.push(e),
      () => {},
      { url: 'ws://x/ws', socket: make },
    );
    const socket = sockets[0];
    connection.send({ type: 'dev_text', text: '안녕' });
    expect(socket.sent).toEqual([]);
    socket.readyState = FakeSocket.OPEN;
    connection.send({ type: 'dev_text', text: '안녕' });
    expect(socket.sent).toEqual(['{"type":"dev_text","text":"안녕"}']);
    socket.onmessage!({ data: '{"type":"notice","level":"info","text":""}' });
    expect(events).toEqual([{ type: 'notice', level: 'info', text: '' }]);
  });
});
