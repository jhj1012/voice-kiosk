import { cubicOut } from 'svelte/easing';
import { crossfade, fade, fly } from 'svelte/transition';

// A menu card's image grows into the item screen's large image (and back), keyed by item id.
export const [send, receive] = crossfade({
  duration: 650,
  easing: cubicOut,
  fallback: (node) => fade(node, { duration: 250 }),
});

export function screenIn(node: Element) {
  return fly(node, { y: 28, duration: 520, delay: 120, easing: cubicOut });
}

export function screenOut(node: Element) {
  return fade(node, { duration: 220 });
}
