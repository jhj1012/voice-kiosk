import { describe, expect, it } from 'vitest';
import { FRAME_SAMPLES, Framer, fromPcm16, loudness, toPcm16 } from './phone';

describe('phone audio', () => {
  it('converts between float samples and 16-bit PCM', () => {
    const pcm = toPcm16(new Float32Array([0, 1, -1, 0.5, 2, -2]));
    expect(Array.from(pcm)).toEqual([0, 32767, -32768, 16384, 32767, -32768]);
    const back = fromPcm16(pcm.buffer);
    expect(back[1]).toBeCloseTo(1, 3);
    expect(back[2]).toBe(-1);
    expect(fromPcm16(new ArrayBuffer(3)).length).toBe(1); // a stray odd byte is ignored
  });

  it('sends 20 ms frames whatever the size of the blocks', () => {
    const framer = new Framer();
    expect(framer.push(new Float32Array(128))).toEqual([]);
    expect(framer.push(new Float32Array(128))).toEqual([]);
    const frames = framer.push(new Float32Array(128 * 4).fill(0.5));
    expect(frames.length).toBe(2); // 640 samples: 2 frames, 0 left
    expect(frames[0].length).toBe(FRAME_SAMPLES);
    expect(frames[0][FRAME_SAMPLES - 1]).toBe(16384);
    framer.push(new Float32Array(100));
    framer.reset(); // a new conversation starts with a fresh frame
    expect(framer.push(new Float32Array(FRAME_SAMPLES)).length).toBe(1);
  });

  it('measures loudness as the laptop does', () => {
    expect(loudness(new Float32Array(0))).toBe(0);
    expect(loudness(new Float32Array(10))).toBe(0);
    expect(loudness(new Float32Array(10).fill(3000 / 32768))).toBeCloseTo(0.5, 5);
    expect(loudness(new Float32Array(10).fill(1))).toBe(1);
  });
});
