import { describe, expect, it } from 'vitest';
import { won } from './format';

describe('won', () => {
  it('adds thousands separators and the unit', () => {
    expect(won(4500)).toBe('4,500원');
    expect(won(0)).toBe('0원');
  });
});
