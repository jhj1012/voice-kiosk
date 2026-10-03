import { cubicOut } from 'svelte/easing';
import { crossfade, fade, scale } from 'svelte/transition';

// A menu card's image grows into the item's large image (and back), keyed by item id.
export const [send, receive] = crossfade({
  duration: 600,
  easing: cubicOut,
  fallback: (node) => fade(node, { duration: 250 }),
});

// Content on the one continuous page appears and disappears in place (no "next screen").
export function appear(node: Element, { delay = 0 } = {}) {
  return scale(node, {
    start: 0.97,
    opacity: 0,
    duration: 450,
    delay: 120 + delay,
    easing: cubicOut,
  });
}

export function disappear(node: Element) {
  return fade(node, { duration: 220 });
}
