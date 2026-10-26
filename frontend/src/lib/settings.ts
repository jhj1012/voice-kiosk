// The settings from the developer panel (F2): the choices' background style, subtitles, the
// colours, whether the assistant ignores speech not meant for the kiosk (read by the backend when
// the next customer lifts the handset), and how much of the phone's screen its case covers. The
// backend saves them (configs/display.local.json) and sends them to every display; anything
// missing or malformed falls back to the defaults here. Pure, unit tested.

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

/** The parts of the phone's screen its case covers, in % of the screen's height (top, bottom) and
 * width (left, right). The phone mode keeps the choices and the order out of them. */
export interface PhoneInsets {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

export const INSET_SIDES: { key: keyof PhoneInsets; label: string }[] = [
  { key: 'top', label: '위' },
  { key: 'bottom', label: '아래' },
  { key: 'left', label: '왼쪽' },
  { key: 'right', label: '오른쪽' },
];

export const MAX_INSET = 40;

export interface Settings {
  backdrop: Backdrop;
  panelOpacity: number; // 0..1, the choices' background
  subtitles: boolean; // what the customer and the assistant say, as text
  ignoreUnrelated: boolean; // no answer to words not meant for the kiosk (next customer)
  colors: Record<string, string>;
  phoneInsets: PhoneInsets;
}

export const DEFAULTS: Settings = {
  backdrop: 'blur',
  panelOpacity: 0.72,
  subtitles: false,
  ignoreUnrelated: false,
  colors: Object.fromEntries(COLORS.map((c) => [c.key, c.value])),
  // Measured on the team's 19.5 x 31.5 cm screen: 1.5 cm top, 7 cm bottom, 0.5 cm each side.
  phoneInsets: { top: 4.8, bottom: 22.2, left: 2.6, right: 2.6 },
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
  const phoneInsets = { ...DEFAULTS.phoneInsets };
  const insets = values.phoneInsets;
  if (insets && typeof insets === 'object') {
    for (const { key } of INSET_SIDES) {
      const value = (insets as Record<string, unknown>)[key];
      if (typeof value === 'number' && value >= 0 && value <= MAX_INSET) phoneInsets[key] = value;
    }
  }
  return {
    backdrop,
    panelOpacity:
      typeof opacity === 'number' && opacity >= 0 && opacity <= 1 ? opacity : DEFAULTS.panelOpacity,
    subtitles: typeof values.subtitles === 'boolean' ? values.subtitles : DEFAULTS.subtitles,
    ignoreUnrelated:
      typeof values.ignoreUnrelated === 'boolean'
        ? values.ignoreUnrelated
        : DEFAULTS.ignoreUnrelated,
    colors,
    phoneInsets,
  };
}

/** The phone mode's covered edges as CSS variables for the page (`--safe-*`, lengths). The
 * sides are measured from the screen's edges; the page may be narrower than the screen (it
 * keeps 9:16), so only what reaches into the page counts. Use them in `left` / `right` of
 * elements positioned in the page. */
export function insetVariables(insets: PhoneInsets): Record<string, string> {
  const side = (percent: number) => `max(0px, calc(${percent}vw - (100vw - 100%) / 2))`;
  return {
    '--safe-top': `${insets.top}dvh`,
    '--safe-bottom': `${insets.bottom}dvh`,
    '--safe-left': side(insets.left),
    '--safe-right': side(insets.right),
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
