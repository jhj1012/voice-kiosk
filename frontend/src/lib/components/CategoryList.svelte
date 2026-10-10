<script lang="ts">
  // The kinds of menu, for "다른 메뉴도 보여 주세요", as a list.
  import { cubicOut } from 'svelte/easing';
  import { fly } from 'svelte/transition';
  import { ui } from '../store.svelte';

  const categories = $derived(
    (ui.menu?.categories ?? []).map((c) => {
      const items = ui.menu!.items.filter((i) => i.category === c.id);
      const shown = items.find((i) => i.recommended) ?? items[0];
      return { ...c, emoji: shown?.emoji ?? '☕', count: items.length };
    }),
  );
</script>

<ul class="list">
  {#each categories as category, i (category.id)}
    <li
      class="row"
      in:fly|global={{ y: 16, opacity: 0, duration: 400, delay: 80 + i * 60, easing: cubicOut }}
    >
      <span class="emoji">{category.emoji}</span>
      <span class="name">{category.name}</span>
      <span class="count">{category.count}가지</span>
    </li>
  {/each}
</ul>

<style>
  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .emoji {
    width: 7.5rem;
    aspect-ratio: 1;
    display: grid;
    place-items: center;
    border-radius: var(--radius-s);
    background: var(--image-bg);
    font-size: 3.8rem;
  }
  .name {
    flex: 1;
    font-size: 2.6rem;
    font-weight: 700;
    letter-spacing: -0.02em;
  }
  .count {
    font-size: 1.8rem;
    color: var(--muted);
  }
</style>
