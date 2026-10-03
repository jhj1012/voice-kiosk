// The display state as Svelte runes. Each part is its own raw state, so a 10 Hz level event
// only re-renders what reads the level, not the menu.

import { apply, initialDisplay, type DisplayState } from './display';
import type { ServerEvent } from './events';

const start = initialDisplay();
let menu = $state.raw(start.menu);
let cafe = $state.raw(start.cafe);
let snapshot = $state.raw(start.state);
let subtitles = $state.raw(start.subtitles);
let level = $state.raw(start.level);
let notice = $state.raw(start.notice);
let lastAdded = $state.raw(start.lastAdded);

export const ui = {
  get menu() {
    return menu;
  },
  get cafe() {
    return cafe;
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
};

export function dispatch(event: ServerEvent): void {
  const before: DisplayState = {
    menu,
    cafe,
    state: snapshot,
    subtitles,
    level,
    notice,
    lastAdded,
  };
  const after = apply(before, event, performance.now());
  if (after.menu !== menu) menu = after.menu;
  if (after.cafe !== cafe) cafe = after.cafe;
  if (after.state !== snapshot) snapshot = after.state;
  if (after.subtitles !== subtitles) subtitles = after.subtitles;
  if (after.level !== level) level = after.level;
  if (after.notice !== notice) notice = after.notice;
  if (after.lastAdded !== lastAdded) lastAdded = after.lastAdded;
}
