import { describe, expect, it } from 'vitest';
import { saveApiKey } from './apiKey';

function answering(body: unknown): typeof fetch {
  return (async (_url: RequestInfo | URL, init?: RequestInit) => {
    expect(JSON.parse(String(init?.body))).toEqual({ key: 'AIza-key' });
    return new Response(JSON.stringify(body));
  }) as typeof fetch;
}

describe('saveApiKey', () => {
  it("returns the backend's answer", async () => {
    expect(await saveApiKey('AIza-key', answering({ result: 'ok' }))).toBe('ok');
    expect(await saveApiKey('AIza-key', answering({ result: 'rejected' }))).toBe('rejected');
  });

  it('treats an unknown answer as an invalid key', async () => {
    expect(await saveApiKey('AIza-key', answering({ nope: 1 }))).toBe('invalid');
  });

  it('notices when the kiosk program is not running', async () => {
    const offline = (async () => {
      throw new TypeError('Failed to fetch');
    }) as typeof fetch;
    expect(await saveApiKey('AIza-key', offline)).toBe('no_server');
  });
});
