// The display settings from the developer panel (F2): the choices' background style, subtitles
// and the colours. The backend saves them (configs/display.local.json) and sends them to every
// display; anything missing or malformed falls back to the defaults here. Pure, unit tested.

export type Backdrop = 'blur' | 'gradient' | 'boxes';

export const BACKDROPS: { id: Backdrop; label: string }[] = [
  { id: 'blur', label: '흐림' },
  { id: 'gradient', label: '아래에서 그라데이션' },
  { id: 'boxes', label: '상자' },
];

export interface ColorSetting {
  key: string;
  label: string;
  css: string; // the CSS variable it sets
  value: string; // the default, #rrggbb
}

export const COLORS: ColorSetting[] = [
  { key: 'background', label: '배경', css: '--bg', value: '#ffffff' },
  { key: 'glow', label: '배경 빛', css: '--glow', value: '#dcebff' },
  { key: 'panel', label: '선택지 배경', css: '--panel', value: '#ffffff' },
  { key: 'imageBg', label: '메뉴 사진 배경', css: '--image-bg', value: '#eef4ff' },
  { key: 'text', label: '글자', css: '--text', value: '#0e1a2b' },
  { key: 'text2', label: '보조 글자', css: '--text-2', value: '#4b5b71' },
  { key: 'muted', label: '흐린 글자', css: '--muted', value: '#94a3b8' },
  { key: 'accent', label: '강조', css: '--accent', value: '#2f6fed' },
  { key: 'onAccent', label: '강조 위 글자', css: '--on-accent', value: '#ffffff' },
  { key: 'line', label: '구분선', css: '--line', value: '#e2ebf8' },
];

export interface Settings {
  backdrop: Backdrop;
  panelOpacity: number; // 0..1, the choices' background
  subtitles: boolean; // what the customer and the assistant say, as text
  colors: Record<string, string>;
}

export const DEFAULTS: Settings = {
  backdrop: 'blur',
  panelOpacity: 0.72,
  subtitles: false,
  colors: Object.fromEntries(COLORS.map((c) => [c.key, c.value])),
};

const HEX = /^#[0-9a-f]{6}$/i;

/** The saved values on top of the defaults; unknown or malformed values are ignored. */
export function normalize(values: Record<string, unknown>): Settings {
  const colors = { ...DEFAULTS.colors };
  const saved = values.colors;
  if (saved && typeof saved === 'object') {
    for (const { key } of COLORS) {
      const value = (saved as Record<string, unknown>)[key];
      if (typeof value === 'string' && HEX.test(value)) colors[key] = value.toLowerCase();
    }
  }
  const backdrop = BACKDROPS.some((b) => b.id === values.backdrop)
    ? (values.backdrop as Backdrop)
    : DEFAULTS.backdrop;
  const opacity = values.panelOpacity;
  return {
    backdrop,
    panelOpacity:
      typeof opacity === 'number' && opacity >= 0 && opacity <= 1 ? opacity : DEFAULTS.panelOpacity,
    subtitles: typeof values.subtitles === 'boolean' ? values.subtitles : DEFAULTS.subtitles,
    colors,
  };
}

/** The CSS variables for the page (colours, and the choices' see-through background). */
export function cssVariables(settings: Settings): Record<string, string> {
  const variables: Record<string, string> = {};
  for (const { key, css } of COLORS) variables[css] = settings.colors[key];
  variables['--panel-soft'] = withAlpha(settings.colors.panel, settings.panelOpacity);
  return variables;
}

export function withAlpha(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgb(${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255} / ${Math.round(alpha * 100) / 100})`;
}
