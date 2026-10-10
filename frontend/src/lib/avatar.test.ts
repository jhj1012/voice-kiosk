import { describe, expect, it } from 'vitest';
import { nextClip } from './avatar';
import type { AvatarClip } from './events';

const all = () => true;
const loopsOnly = (clip: AvatarClip) => clip !== 'pick_up' && clip !== 'put_down';

describe('avatar clips', () => {
  it('picks up the handset, listens and talks, puts it down', () => {
    expect(nextClip('idle', false, false, false, all)).toBe('idle');
    expect(nextClip('idle', true, false, false, all)).toBe('pick_up');
    // The pick-up plays to its end, even when the greeting starts.
    expect(nextClip('pick_up', true, true, false, all)).toBe('pick_up');
    expect(nextClip('pick_up', true, true, true, all)).toBe('talking');
    expect(nextClip('talking', true, false, false, all)).toBe('listening');
    expect(nextClip('listening', true, true, false, all)).toBe('talking');
    expect(nextClip('talking', false, true, false, all)).toBe('put_down');
    expect(nextClip('put_down', false, false, false, all)).toBe('put_down');
    expect(nextClip('put_down', false, false, true, all)).toBe('idle');
  });

  it('turns around when the handset changes mid-clip', () => {
    expect(nextClip('pick_up', false, false, false, all)).toBe('put_down');
    expect(nextClip('put_down', true, false, false, all)).toBe('pick_up');
  });

  it('skips one-time clips that do not exist', () => {
    expect(nextClip('idle', true, false, false, loopsOnly)).toBe('listening');
    expect(nextClip('idle', true, true, false, loopsOnly)).toBe('talking');
    expect(nextClip('talking', false, false, false, loopsOnly)).toBe('idle');
  });
});
