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

// The phone's text sizes, in % of the designed sizes (text came out larger there): all of it, and
// each place on the screen on top of that (a role of textRoles.ts -> %, only those changed).
export const MIN_TEXT_SIZE = 30;
export const MAX_TEXT_SIZE = 300;
export const MAX_NOISE_GATE = 32767; // 16-bit RMS

export interface Settings {
  backdrop: Backdrop;
  panelOpacity: number; // 0..1, the choices' background
  subtitles: boolean; // what the customer and the assistant say, as text
  ignoreUnrelated: boolean; // no answer to words not meant for the kiosk (next customer)
  colors: Record<string, string>;
  phoneInsets: PhoneInsets;
  phoneTextScale: number;
  phoneTextRoles: Record<string, number>;
  noiseGate: number | null; // the microphone's noise gate (16-bit RMS, 0: off); null: settings.yaml's
}

export const DEFAULTS: Settings = {
  backdrop: 'boxes',
  panelOpacity: 0.88,
  subtitles: false,
  ignoreUnrelated: true, // the backend's default too (`KioskController.ignore_unrelated`)
  colors: Object.fromEntries(COLORS.map((c) => [c.key, c.value])),
  // Set on the team's 19.5 x 31.5 cm screen: 1.5 cm top, about 7 cm bottom, nothing at the sides.
  phoneInsets: { top: 4.8, bottom: 21.3, left: 0, right: 0 },
  phoneTextScale: 100,
  noiseGate: null,
  // Set with the text size editor (F4) on the team's phone.
  phoneTextRoles: {
    'diningchoice-emoji': 95,
    'itemdetail-row-chosen-choice': 65,
    'categorylist-emoji': 100,
    'done-number': 85,
    'stage-prompt': 105,
    'diningchoice-label': 130,
    'stage-prompt-small': 125,
    'itemdetail-h2': 135,
    'itemdetail-price': 135,
    'page-caption': 170,
    'itemdetail-choice': 120,
    'itemdetail-extra': 110,
    'itemdetail-pill': 140,
    'itemdetail-group': 150,
    'itemdetail-pill-small': 135,
    'itemdetail-chip': 125,
    'itemdetail-pill-on': 150,
    'itemimage-s-emoji': 190,
    'orderbar-count': 135,
    'orderbar-total': 115,
    'menulist-name': 155,
    'menulist-price': 160,
    'review-qty': 145,
    'payment-screen': 125,
    'done-label': 140,
    'done-note': 140,
    'categorylist-name': 160,
    'categorylist-count': 155,
    'itemdetail-facts': 140,
    'info-p': 140,
    'info-h2': 115,
    'review-name': 150,
    'review-options': 160,
    'staffnotes-ul': 135,
    'review-amount': 135,
    'review-dining': 180,
    'review-label': 185,
    'staffnotes-label': 135,
    'review-value': 110,
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
    noiseGate:
      typeof values.noiseGate === 'number' &&
      values.noiseGate >= 0 &&
      values.noiseGate <= MAX_NOISE_GATE
        ? values.noiseGate
        : null,
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
