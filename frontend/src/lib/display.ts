// The display's state and how each server event changes it. Pure functions, unit tested.

import type {
  ApiKeyStatus,
  AvatarFiles,
  Cafe,
  Menu,
  NoticeEvent,
  ServerEvent,
  Speaker,
  StateEvent,
  SubtitleEvent,
} from './events';

export interface Subtitle {
  id: number;
  speaker: Speaker;
  text: string;
  final: boolean;
}

export interface DisplayState {
  menu: Menu | null;
  cafe: Cafe | null;
  avatar: AvatarFiles | null;
  settings: Record<string, unknown>; // as saved; settings.ts gives them meaning
  state: StateEvent;
  subtitles: Subtitle[]; // the latest few utterances, oldest first
  level: { mic: number; out: number };
  notice: NoticeEvent | null;
  apiKey: ApiKeyStatus;
  lastAdded: { itemId: string; at: number } | null; // for the "fly into the order" animation
}

export const MAX_SUBTITLES = 2;

export function idleState(): StateEvent {
  return {
    type: 'state',
    seq: 0,
    phase: 'idle',
    assistant: 'idle',
    view: {
      screen: 'attract',
      title: '',
      item_ids: [],
      highlight: [],
      item_id: '',
      group: '',
      line: 0,
      topic: '',
    },
    pending: null,
    order: { lines: [], dining: null, notes: [], count: 0, total: 0 },
    payment: null,
  };
}

export function initialDisplay(): DisplayState {
  return {
    menu: null,
    cafe: null,
    avatar: null,
    settings: {},
    state: idleState(),
    subtitles: [],
    level: { mic: 0, out: 0 },
    notice: null,
    apiKey: 'ok',
    lastAdded: null,
  };
}

export function apply(display: DisplayState, event: ServerEvent, now = 0): DisplayState {
  switch (event.type) {
    case 'init':
      return { ...display, menu: event.menu, cafe: event.cafe, avatar: event.avatar ?? null };
    case 'settings':
      return { ...display, settings: event.values };
    case 'state':
      return applyState(display, event, now);
    case 'subtitle':
      return { ...display, subtitles: applySubtitle(display.subtitles, event) };
    case 'level':
      return { ...display, level: { mic: event.mic, out: event.out } };
    case 'notice':
      return { ...display, notice: event.text ? event : null };
    case 'setup':
      return { ...display, apiKey: event.api_key };
  }
}

function applyState(display: DisplayState, next: StateEvent, now: number): DisplayState {
  if (next.seq !== 0 && next.seq < display.state.seq && next.phase !== 'idle') {
    return display; // an old snapshot arriving late
  }
  const ended = next.phase === 'idle' && display.state.phase !== 'idle';
  // Nothing "flies" on the first snapshot (e.g. after the display connected mid-order).
  const added = display.state.seq > 0 ? addedItem(display.state, next) : null;
  return {
    ...display,
    state: next,
    subtitles: ended ? [] : display.subtitles,
    lastAdded: added ? { itemId: added, at: now } : ended ? null : display.lastAdded,
  };
}

/** The item that just went into the order (a new line, or more of an existing line). */
export function addedItem(before: StateEvent, after: StateEvent): string | null {
  const count = (state: StateEvent, itemId: string) =>
    state.order.lines.filter((l) => l.item_id === itemId).reduce((n, l) => n + l.quantity, 0);
  for (const line of after.order.lines) {
    if (count(after, line.item_id) > count(before, line.item_id)) {
      return line.item_id;
    }
  }
  return null;
}

function applySubtitle(subtitles: Subtitle[], event: SubtitleEvent): Subtitle[] {
  const next: Subtitle = {
    id: event.id,
    speaker: event.speaker,
    text: event.text,
    final: event.final,
  };
  const index = subtitles.findIndex((s) => s.id === event.id);
  if (index >= 0) {
    return subtitles.map((s, i) => (i === index ? next : s));
  }
  return [...subtitles, next].slice(-MAX_SUBTITLES);
}
