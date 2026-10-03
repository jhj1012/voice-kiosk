import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ServerEvent } from './events';
import { play, type Timeline } from './player';

const notice = (text: string): ServerEvent => ({ type: 'notice', level: 'info', text });
const level = (mic: number): ServerEvent => ({ type: 'level', mic, out: 0 });

const timeline: Timeline = {
  title: 'test',
  duration: 3000,
  events: [
    [0, notice('a')],
    [100, level(0.1)],
    [1000, notice('b')],
    [1900, level(0.9)],
    [3000, notice('c')],
  ],
};

describe('play', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('emits events at their times and loops', () => {
    const got: ServerEvent[] = [];
    const stop = play(timeline, (e) => got.push(e));
    expect(got).toEqual([notice('a')]);
    vi.advanceTimersByTime(1000);
    expect(got.at(-1)).toEqual(notice('b'));
    vi.advanceTimersByTime(2000);
    expect(got.at(-1)).toEqual(notice('c'));
    vi.advanceTimersByTime(1500);
    expect(got.at(-1)).toEqual(notice('a')); // started again
    stop();
    vi.advanceTimersByTime(10000);
    expect(got.at(-1)).toEqual(notice('a'));
  });

  it('catches up to startAt, skipping old levels, and can pause there', () => {
    const got: ServerEvent[] = [];
    play(timeline, (e) => got.push(e), { startAt: 2000, pause: true });
    expect(got).toEqual([notice('a'), notice('b'), level(0.9)]);
    vi.advanceTimersByTime(10000);
    expect(got.length).toBe(3);
  });
});
