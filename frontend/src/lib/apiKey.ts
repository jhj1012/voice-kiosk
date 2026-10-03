// Sending the Gemini API key typed on the display to the backend (POST /api/key). The backend
// checks it with Google and saves it; the key never comes back to the display.

export type KeyResult = 'ok' | 'invalid' | 'rejected' | 'offline' | 'unavailable' | 'no_server';

export const KEY_MESSAGES: Record<KeyResult, string> = {
  ok: '저장했어요. 이제 수화기를 들고 말씀해 보세요.',
  invalid: 'API 키가 아닌 것 같아요. AI Studio에서 키 전체를 다시 복사해 붙여 넣어 주세요.',
  rejected: 'Google이 이 키를 받아 주지 않았어요. 키를 다시 복사하거나 새 키를 만들어 주세요.',
  offline: 'Google에 연결할 수 없어요. 인터넷 연결을 확인하고 다시 눌러 주세요.',
  unavailable: '이 키오스크에서는 키를 바꿀 수 없어요. .env 파일에 넣어 주세요.',
  no_server: '키오스크 프로그램이 꺼져 있어요. 프로그램을 다시 실행해 주세요.',
};

export async function saveApiKey(key: string, send: typeof fetch = fetch): Promise<KeyResult> {
  try {
    const response = await send('/api/key', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key }),
    });
    const body = (await response.json()) as { result?: string };
    return body.result && body.result in KEY_MESSAGES ? (body.result as KeyResult) : 'invalid';
  } catch {
    return 'no_server';
  }
}
