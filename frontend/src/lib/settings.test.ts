import { describe, expect, it } from 'vitest';
import { cssVariables, DEFAULTS, insetVariables, normalize, withAlpha } from './settings';

describe('display settings', () => {
  it('uses the defaults when nothing is saved', () => {
    expect(normalize({})).toEqual(DEFAULTS);
  });

  it('takes saved values and ignores malformed ones', () => {
    const settings = normalize({
      backdrop: 'boxes',
      subtitles: true,
      ignoreUnrelated: true,
      panelOpacity: 0.5,
      colors: { text: '#ABCDEF', accent: 'red', nope: '#000000' },
    });
    expect(settings.backdrop).toBe('boxes');
    expect(settings.subtitles).toBe(true);
    expect(settings.ignoreUnrelated).toBe(true);
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

describe('phone insets', () => {
  it('takes saved sides and keeps the defaults for the rest', () => {
    const settings = normalize({ phoneInsets: { top: 3, bottom: 'x', left: 99, right: 0 } });
    expect(settings.phoneInsets).toEqual({ ...DEFAULTS.phoneInsets, top: 3, right: 0 });
    expect(normalize({ phoneInsets: 5 }).phoneInsets).toEqual(DEFAULTS.phoneInsets);
  });

  it('become CSS lengths', () => {
    const variables = insetVariables({ top: 4.8, bottom: 22.2, left: 2.6, right: 0 });
    expect(variables['--safe-top']).toBe('4.8dvh');
    expect(variables['--safe-bottom']).toBe('22.2dvh');
    expect(variables['--safe-left']).toBe('max(0px, calc(2.6vw - (100vw - 100%) / 2))');
  });
});
