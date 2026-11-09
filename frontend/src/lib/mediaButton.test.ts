import { describe, expect, it, vi } from 'vitest';
import { keepPlaying, loopWav, pressGate } from './mediaButton';

/** An audio element that Android can pause (the handset unplugged). */
class FakeAudio {
  paused = false;
  plays = 0;
  private onPause: (() => void) | null = null;
  play() {
    this.plays++;
    this.paused = false;
    return Promise.resolve();
  }
  addEventListener(_type: 'pause', listener: () => void) {
    this.onPause = listener;
  }
  pauseByAndroid() {
    this.paused = true;
    this.onPause?.();
  }
}

describe('keeping the silent loop playing', () => {
  it('plays again soon after it was paused, and when checked', () => {
    vi.useFakeTimers();
    const audio = new FakeAudio();
    let check = () => {};
    const resume = keepPlaying(audio, 2000, (run) => (check = run));
    audio.pauseByAndroid();
    expect(audio.paused).toBe(true);
    vi.advanceTimersByTime(300);
    expect(audio.paused).toBe(false);
    audio.paused = true; // paused without an event
    check();
    expect(audio.paused).toBe(false);
    resume(); // playing: nothing to do
    expect(audio.plays).toBe(2);
    vi.useRealTimers();
  });
});

describe('silent loop', () => {
  it('is 10 s of 8 kHz 16-bit mono WAV', () => {
    const data = new DataView(loopWav());
    const text = (at: number) => String.fromCharCode(...new Uint8Array(data.buffer, at, 4));
    expect([text(0), text(8), text(36)]).toEqual(['RIFF', 'WAVE', 'data']);
    expect(data.getUint32(24, true)).toBe(8000);
    expect(data.getUint32(40, true)).toBe(8000 * 10 * 2);
    expect(data.getInt16(44 + 1000, true)).toBe(0);
  });

  it('or noise far below hearing', () => {
    const data = new DataView(loopWav(true, () => 1));
    expect(data.getInt16(44, true)).toBe(16);
  });
});

describe('press gate', () => {
  it('lets one press through per gap', () => {
    let now = 0;
    const pass = pressGate(800, () => now);
    expect(pass()).toBe(true);
    now = 300;
    expect(pass()).toBe(false);
    now = 900;
    expect(pass()).toBe(true);
  });
});
