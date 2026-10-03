// Demo mode: plays a recorded event timeline (src/dev/demo.json, written by
// scripts/make_demo_events.py) as if the backend sent it.

import type { ServerEvent } from './events';

export interface Timeline {
  title: string;
  duration: number; // ms
  events: [number, ServerEvent][];
}

export interface PlayOptions {
  startAt?: number; // ms: events up to this time are applied at once
  loop?: boolean;
  pause?: boolean; // stop at `startAt` (for screenshots)
}

const LOOP_GAP_MS = 1500;

/** Plays `timeline`, calling `emit` for each event at its time. Returns a stop function. */
export function play(
  timeline: Timeline,
  emit: (event: ServerEvent) => void,
  { startAt = 0, loop = true, pause = false }: PlayOptions = {},
): () => void {
  let timers: ReturnType<typeof setTimeout>[] = [];

  const run = (from: number) => {
    timers = [];
    // Catch up at once; old level events are skipped (only the current loudness matters).
    for (const [t, event] of timeline.events) {
      if (t > from) break;
      if (event.type === 'level' && t < from - 200) continue;
      emit(event);
    }
    if (pause) return;
    for (const [t, event] of timeline.events) {
      if (t > from) timers.push(setTimeout(() => emit(event), t - from));
    }
    if (loop) {
      timers.push(setTimeout(() => run(0), timeline.duration - from + LOOP_GAP_MS));
    }
  };

  run(startAt);
  return () => timers.forEach(clearTimeout);
}
