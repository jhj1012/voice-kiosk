import { describe, expect, it } from 'vitest';
import demo from '../dev/demo.json';
import { addedItem, apply, idleState, initialDisplay, MAX_SUBTITLES } from './display';
import type { ServerEvent, StateEvent } from './events';

function state(overrides: Partial<StateEvent> = {}): StateEvent {
  return { ...idleState(), phase: 'ordering', seq: 1, ...overrides };
}

const line = (item_id: string, quantity: number, n = 1) => ({
  line: n,
  item_id,
  name: item_id,
  options: '',
  chosen: {},
  quantity,
  unit_price: 1000,
  total: 1000 * quantity,
});

describe('apply', () => {
  it('stores the menu from init', () => {
    const init = demo.init as ServerEvent;
    const display = apply(initialDisplay(), init);
    expect(display.menu?.items.length).toBe(12);
    expect(display.cafe?.name).toBe('대홍단감자 카페');
  });

  it('replaces the snapshot and ignores older ones', () => {
    let display = apply(initialDisplay(), state({ seq: 5 }));
    display = apply(display, state({ seq: 3, assistant: 'speaking' }));
    expect(display.state.seq).toBe(5);
    expect(display.state.assistant).toBe('idle');
  });

  it('accepts the idle snapshot of a new session even with a lower seq', () => {
    let display = apply(initialDisplay(), state({ seq: 9 }));
    display = apply(display, { ...idleState(), seq: 1 });
    expect(display.state.phase).toBe('idle');
  });

  it('grows subtitles by id and keeps the latest few', () => {
    let display = initialDisplay();
    const sub = (id: number, text: string, final = false): ServerEvent => ({
      type: 'subtitle',
      id,
      speaker: 'assistant',
      text,
      final,
    });
    display = apply(display, sub(1, '안녕'));
    display = apply(display, sub(1, '안녕하세요', true));
    expect(display.subtitles).toEqual([
      { id: 1, speaker: 'assistant', text: '안녕하세요', final: true },
    ]);
    display = apply(display, sub(2, '둘'));
    display = apply(display, sub(3, '셋'));
    expect(display.subtitles.map((s) => s.id)).toEqual([2, 3]);
    expect(display.subtitles.length).toBe(MAX_SUBTITLES);
  });

  it('clears subtitles when the session ends', () => {
    let display = apply(initialDisplay(), state({ seq: 2 }));
    display = apply(display, {
      type: 'subtitle',
      id: 1,
      speaker: 'customer',
      text: '네',
      final: true,
    });
    display = apply(display, { ...idleState(), seq: 3 });
    expect(display.subtitles).toEqual([]);
  });

  it('notices: empty text clears', () => {
    let display = apply(initialDisplay(), { type: 'notice', level: 'warn', text: '연결 중' });
    expect(display.notice?.text).toBe('연결 중');
    display = apply(display, { type: 'notice', level: 'info', text: '' });
    expect(display.notice).toBeNull();
  });

  it('knows whether the API key works (assumed until the backend says otherwise)', () => {
    let display = initialDisplay();
    expect(display.apiKey).toBe('ok');
    display = apply(display, { type: 'setup', api_key: 'missing' });
    expect(display.apiKey).toBe('missing');
  });

  it('remembers the item that was just added', () => {
    let display = apply(initialDisplay(), state({ seq: 1 }));
    const order = { lines: [line('americano', 2)], dining: null, notes: [], count: 2, total: 2000 };
    display = apply(display, state({ seq: 2, order }), 1234);
    expect(display.lastAdded).toEqual({ itemId: 'americano', at: 1234 });
  });

  it('does not animate the first snapshot after connecting', () => {
    const order = { lines: [line('americano', 2)], dining: null, notes: [], count: 2, total: 2000 };
    const display = apply(initialDisplay(), state({ seq: 40, order }));
    expect(display.lastAdded).toBeNull();
  });
});

describe('addedItem', () => {
  const withLines = (lines: ReturnType<typeof line>[]) =>
    state({ order: { lines, dining: null, notes: [], count: 0, total: 0 } });

  it('finds a new line or a higher quantity', () => {
    expect(addedItem(withLines([]), withLines([line('latte', 1)]))).toBe('latte');
    expect(addedItem(withLines([line('latte', 1)]), withLines([line('latte', 3)]))).toBe('latte');
  });

  it('ignores removals and option changes', () => {
    expect(addedItem(withLines([line('latte', 2)]), withLines([line('latte', 1)]))).toBeNull();
    expect(addedItem(withLines([line('latte', 1)]), withLines([line('latte', 1)]))).toBeNull();
  });
});

describe('demo timelines', () => {
  it('are sorted by time and start idle', () => {
    for (const scenario of Object.values(demo.scenarios)) {
      const times = scenario.events.map(([t]) => t as number);
      expect(times).toEqual([...times].sort((a, b) => a - b));
      const first = scenario.events[0][1] as StateEvent;
      expect(first.phase).toBe('idle');
    }
  });
});
