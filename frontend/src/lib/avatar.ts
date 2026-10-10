// Which of the avatar's animations plays. Loops (idle, listening, talking) follow the kiosk;
// the one-time clips (pick_up, put_down) play to their end first. A missing one-time clip is
// skipped. Pure, unit tested.

import type { AvatarClip } from './events';

export const LOOPS: AvatarClip[] = ['idle', 'listening', 'talking'];

/**
 * The clip after `current`.
 * onLine: a customer holds the handset; speaking: the assistant's voice plays;
 * ended: `current` (a one-time clip) just finished; has: whether a clip's file exists.
 */
export function nextClip(
  current: AvatarClip,
  onLine: boolean,
  speaking: boolean,
  ended: boolean,
  has: (clip: AvatarClip) => boolean,
): AvatarClip {
  const talk: AvatarClip = speaking ? 'talking' : 'listening';
  let next: AvatarClip;
  switch (current) {
    case 'idle':
      next = onLine ? 'pick_up' : 'idle';
      break;
    case 'pick_up':
      next = !onLine ? 'put_down' : ended ? talk : 'pick_up';
      break;
    case 'listening':
    case 'talking':
      next = onLine ? talk : 'put_down';
      break;
    case 'put_down':
      next = onLine ? 'pick_up' : ended ? 'idle' : 'put_down';
      break;
  }
  if (next !== current && !LOOPS.includes(next) && !has(next)) {
    return nextClip(next, onLine, speaking, true, has); // no file: as if it had played
  }
  return next;
}
