// The WebSocket to the backend: receives display events, sends developer events. Reconnects
// on its own (the backend sends `init` and a full `state` on every connection).

import type { ClientEvent, ServerEvent } from './events';

export interface Connection {
  send(event: ClientEvent): void;
  close(): void;
}

export interface ConnectOptions {
  url?: string;
  socket?: (url: string) => WebSocket; // for tests
}

/** `onStatus` is called only when the status changes (not on every failed retry). */
export function connect(
  onEvent: (event: ServerEvent) => void,
  onStatus: (connected: boolean) => void,
  {
    url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`,
    socket: makeSocket = (u) => new WebSocket(u),
  }: ConnectOptions = {},
): Connection {
  let socket: WebSocket | null = null;
  let closed = false;
  let retry = 500;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let status: boolean | null = null;

  const report = (connected: boolean) => {
    if (connected !== status) {
      status = connected;
      onStatus(connected);
    }
  };

  const open = () => {
    socket = makeSocket(url);
    socket.onopen = () => {
      retry = 500;
      report(true);
    };
    socket.onmessage = (message) => {
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
  open();

  return {
    send(event) {
      if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(event));
    },
    close() {
      closed = true;
      clearTimeout(timer);
      socket?.close();
    },
  };
}
