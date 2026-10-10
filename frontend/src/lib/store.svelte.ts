// The display state as Svelte runes. Each part is its own raw state, so a 10 Hz level event
// only re-renders what reads the level, not the menu.

import { apply, initialDisplay, type DisplayState } from './display';
import type { ServerEvent } from './events';
import { normalize } from './settings';

const start = initialDisplay();
let menu = $state.raw(start.menu);
let cafe = $state.raw(start.cafe);
let avatar = $state.raw(start.avatar);
let savedSettings = $state.raw(start.settings);
let snapshot = $state.raw(start.state);
let subtitles = $state.raw(start.subtitles);
let level = $state.raw(start.level);
let notice = $state.raw(start.notice);
let apiKey = $state.raw(start.apiKey);
let keyFormOpen = $state(false); // the developer panel's "API 키 바꾸기"
let lastAdded = $state.raw(start.lastAdded);
const settings = $derived(normalize(savedSettings));

export const ui = {
  get menu() {
    return menu;
  },
  get cafe() {
    return cafe;
  },
  get avatar() {
    return avatar;
  },
  /** The developer panel's display settings (defaults for anything not saved). */
  get settings() {
    return settings;
  },
  get savedSettings() {
    return savedSettings;
  },
  get state() {
    return snapshot;
  },
  get subtitles() {
    return subtitles;
  },
  get level() {
    return level;
  },
  get notice() {
    return notice;
  },
  get lastAdded() {
    return lastAdded;
  },
  get apiKey() {
    return apiKey;
  },
  /** The API key form: when the key does not work, or when someone wants to change it. */
  get keyForm() {
    return apiKey !== 'ok' || keyFormOpen;
  },
};

export function openKeyForm(open: boolean): void {
  keyFormOpen = open;
}

/** Shows a settings change at once, before the backend saved it (and in demo mode). */
export function previewSettings(values: Record<string, unknown> | null): void {
  savedSettings = values === null ? {} : { ...savedSettings, ...values };
}

export function dispatch(event: ServerEvent): void {
  const before: DisplayState = {
    menu,
    cafe,
    avatar,
    settings: savedSettings,
    state: snapshot,
    subtitles,
    level,
    notice,
    apiKey,
    lastAdded,
  };
  const after = apply(before, event, performance.now());
  if (after.menu !== menu) menu = after.menu;
  if (after.cafe !== cafe) cafe = after.cafe;
  if (after.avatar !== avatar) avatar = after.avatar;
  if (after.settings !== savedSettings) savedSettings = after.settings;
  if (after.state !== snapshot) snapshot = after.state;
  if (after.subtitles !== subtitles) subtitles = after.subtitles;
  if (after.level !== level) level = after.level;
  if (after.notice !== notice) notice = after.notice;
  if (after.apiKey !== apiKey) apiKey = after.apiKey;
  if (after.lastAdded !== lastAdded) lastAdded = after.lastAdded;
}
