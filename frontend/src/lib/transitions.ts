import { cubicOut } from 'svelte/easing';
import { fade, scale } from 'svelte/transition';

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
