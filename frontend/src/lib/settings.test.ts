import { describe, expect, it } from 'vitest';
import { cssVariables, DEFAULTS, normalize, withAlpha } from './settings';

describe('display settings', () => {
  it('uses the defaults when nothing is saved', () => {
    expect(normalize({})).toEqual(DEFAULTS);
  });

  it('takes saved values and ignores malformed ones', () => {
    const settings = normalize({
      backdrop: 'boxes',
      subtitles: true,
      panelOpacity: 0.5,
      colors: { text: '#ABCDEF', accent: 'red', nope: '#000000' },
    });
    expect(settings.backdrop).toBe('boxes');
    expect(settings.subtitles).toBe(true);
    expect(settings.panelOpacity).toBe(0.5);
    expect(settings.colors.text).toBe('#abcdef');
    expect(settings.colors.accent).toBe(DEFAULTS.colors.accent);
    expect(settings.colors).not.toHaveProperty('nope');

    const odd = normalize({ backdrop: 'sparkles', subtitles: 'yes', panelOpacity: 3, colors: 1 });
    expect(odd).toEqual(DEFAULTS);
  });

  it('turns colours into CSS variables', () => {
    const variables = cssVariables(normalize({ colors: { panel: '#102030' }, panelOpacity: 0.4 }));
    expect(variables['--panel']).toBe('#102030');
    expect(variables['--panel-soft']).toBe('rgb(16 32 48 / 0.4)');
    expect(variables['--bg']).toBe(DEFAULTS.colors.background);
    expect(withAlpha('#ffffff', 1)).toBe('rgb(255 255 255 / 1)');
  });
});
