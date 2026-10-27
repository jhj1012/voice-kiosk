// The settings from the developer panel (F2): the choices' background style, subtitles, the
// colours, whether the assistant ignores speech not meant for the kiosk (read by the backend when
// the next customer lifts the handset), how much of the phone's screen its case covers, and the
// phone's text sizes (all of it here; each place in the text size editor, F4). The
// backend saves them (configs/display.local.json) and sends them to every display; anything
// missing or malformed falls back to the defaults here. Pure, unit tested.

import { TEXT_ROLES } from './textRoles';

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
  { key: 'background', label: '배경', css: '--bg', value: '#b0b0b0' },
  { key: 'glow', label: '배경 빛', css: '--glow', value: '#c4c4c4' },
  { key: 'panel', label: '선택지 배경', css: '--panel', value: '#dceefe' },
  { key: 'imageBg', label: '메뉴 사진 배경', css: '--image-bg', value: '#ffffff' },
  { key: 'text', label: '글자', css: '--text', value: '#0e1a2b' },
  { key: 'text2', label: '보조 글자', css: '--text-2', value: '#4b5b71' },
  { key: 'muted', label: '흐린 글자', css: '--muted', value: '#212121' },
  { key: 'accent', label: '강조', css: '--accent', value: '#3d7eff' },
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

// The phone's text sizes, in % of the designed sizes (its own font may be wider): all of it, and
// each place on the screen on top of that (a role of textRoles.ts -> %, only those changed).
export const MIN_TEXT_SIZE = 30;
export const MAX_TEXT_SIZE = 300;

export interface Settings {
  backdrop: Backdrop;
  panelOpacity: number; // 0..1, the choices' background
  subtitles: boolean; // what the customer and the assistant say, as text
  ignoreUnrelated: boolean; // no answer to words not meant for the kiosk (next customer)
  colors: Record<string, string>;
  phoneInsets: PhoneInsets;
  phoneTextScale: number;
  phoneTextRoles: Record<string, number>;
}

export const DEFAULTS: Settings = {
  backdrop: 'boxes',
  panelOpacity: 0.88,
  subtitles: false,
  ignoreUnrelated: false,
  colors: Object.fromEntries(COLORS.map((c) => [c.key, c.value])),
  // Set on the team's 19.5 x 31.5 cm screen: 1.5 cm top, about 7 cm bottom, nothing at the sides.
  phoneInsets: { top: 4.8, bottom: 21.3, left: 0, right: 0 },
  phoneTextScale: 100,
  // Set with the text size editor (F4) on the team's phone.
  phoneTextRoles: {
    'stage-prompt': 55,
    'diningchoice-emoji': 75,
    'diningchoice-label': 60,
    'stage-prompt-small': 55,
    'itemdetail-h2': 65,
    'itemdetail-price': 65,
    'page-caption': 65,
    'itemdetail-choice': 60,
    'itemdetail-extra': 70,
    'itemdetail-chip': 70,
    'itemdetail-row-chosen-choice': 65,
    'phoneend-end': 45,
    'itemdetail-group': 80,
    'itemdetail-pill-small': 80,
    'itemdetail-pill': 60,
    'itemdetail-pill-on': 60,
    'orderbar-count': 60,
    'orderbar-total': 60,
    'menulist-name': 70,
    'menulist-price': 70,
    'categorylist-name': 80,
    'categorylist-count': 80,
    'categorylist-emoji': 60,
    'itemdetail-facts': 70,
    'review-amount': 75,
    'review-qty': 60,
    'review-name': 75,
    'review-options': 65,
    'review-value': 45,
    'review-label': 70,
    'review-dining': 60,
    'staffnotes-ul': 75,
    'payment-h2': 50,
    'staffnotes-label': 60,
    'payment-screen': 70,
    'info-icon': 60,
    'info-h2': 60,
    'info-p': 70,
    'done-label': 85,
    'done-number': 80,
    'done-note': 70,
  },
};

const isTextSize = (value: unknown): value is number =>
  typeof value === 'number' && value >= MIN_TEXT_SIZE && value <= MAX_TEXT_SIZE;

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
  // the saved places replace the default ones ("모두 되돌리기" saves none: all at 100%)
  const roles = values.phoneTextRoles ?? DEFAULTS.phoneTextRoles;
  const phoneTextRoles: Record<string, number> = {};
  if (roles && typeof roles === 'object') {
    for (const [role, value] of Object.entries(roles)) {
      if (role in TEXT_ROLES && isTextSize(value)) phoneTextRoles[role] = value;
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
    phoneTextScale: isTextSize(values.phoneTextScale)
      ? values.phoneTextScale
      : DEFAULTS.phoneTextScale,
    phoneTextRoles,
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

/** The phone's text sizes as CSS variables for the page (`--size-all`, `--fs-<role>`, factors). */
export function textSizeVariables(settings: Settings): Record<string, string> {
  const variables: Record<string, string> = { '--size-all': String(settings.phoneTextScale / 100) };
  for (const [role, size] of Object.entries(settings.phoneTextRoles)) {
    variables[`--fs-${role}`] = String(size / 100);
  }
  return variables;
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
