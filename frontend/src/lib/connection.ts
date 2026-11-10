// The WebSocket to the backend: receives display events, sends developer events. Reconnects
// on its own (the backend sends `init` and a full `state` on every connection). The backend
// sends a `ping` whenever nothing else was sent for 5 s, so a connection that hears nothing
// for `STALE_MS` died without closing (team test: the phone kept the idle screen until it was
// reloaded): it is dropped and a new one opened, also as soon as the page is shown again.

import type { ClientEvent, ServerEvent } from './events';

export const STALE_MS = 15000;
const CHECK_MS = 2000;

export interface Connection {
  send(event: ClientEvent): void;
  /** Drop the connection and open a new one (the backend sends everything again). */
  reconnect(): void;
  close(): void;
}

export interface ConnectOptions {
  url?: string;
  socket?: (url: string) => WebSocket; // for tests
  now?: () => number; // for tests
}

/** `onStatus` is called only when the status changes (not on every failed retry). */
export function connect(
  onEvent: (event: ServerEvent) => void,
  onStatus: (connected: boolean) => void,
  {
    url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`,
    socket: makeSocket = (u) => new WebSocket(u),
    now = () => Date.now(),
  }: ConnectOptions = {},
): Connection {
  let socket: WebSocket | null = null;
  let closed = false;
  let retry = 500;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let status: boolean | null = null;
  let heard = now();

  const report = (connected: boolean) => {
    if (connected !== status) {
      status = connected;
      onStatus(connected);
    }
  };

  const open = () => {
    heard = now();
    socket = makeSocket(url);
    socket.onopen = () => {
      retry = 500;
      heard = now();
      report(true);
    };
    socket.onmessage = (message) => {
      heard = now();
      try {
        onEvent(JSON.parse(message.data as string) as ServerEvent);
      } catch (error) {
        console.warn('bad event', error);
      }
    };
    socket.onclose = () => {
      report(false);
      if (!closed) {
        timer = setTimeout(open, retry);
        retry = Math.min(retry * 2, 5000);
      }
    };
  };

  /** Let the connection go (its close may never come) and open a new one. */
  const reopen = () => {
    if (closed || !socket) return;
    const old = socket;
    old.onopen = old.onmessage = old.onclose = null;
    old.close();
    clearTimeout(timer);
    report(false);
    open();
  };
  const reopenIfStale = () => {
    if (closed || !socket || now() - heard < STALE_MS) return;
    console.warn('no word from the kiosk: connecting again');
    reopen();
  };
  const watch = setInterval(reopenIfStale, CHECK_MS);
  const onShown = () => {
    if (document.visibilityState === 'visible') reopenIfStale();
  };
  if (typeof document !== 'undefined') document.addEventListener('visibilitychange', onShown);
  open();

  return {
    send(event) {
      if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(event));
    },
    reconnect: reopen,
    close() {
      closed = true;
      clearTimeout(timer);
      clearInterval(watch);
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onShown);
      }
      socket?.close();
    },
  };
}
