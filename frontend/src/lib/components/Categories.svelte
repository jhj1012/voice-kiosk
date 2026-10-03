<script lang="ts">
  // The kinds of menu, for "다른 메뉴도 보여 주세요".
  import { cubicOut } from 'svelte/easing';
  import { scale } from 'svelte/transition';
  import { ui } from '../store.svelte';

  const categories = $derived(
    (ui.menu?.categories ?? []).map((c) => {
      const items = ui.menu!.items.filter((i) => i.category === c.id);
      const shown = items.find((i) => i.recommended) ?? items[0];
      return { ...c, emoji: shown?.emoji ?? '☕', count: items.length };
    }),
  );
</script>

<div class="categories">
  {#each categories as category, i (category.id)}
    <div
      class="kind"
      in:scale|global={{
        start: 0.94,
        opacity: 0,
        duration: 450,
        delay: 120 + i * 70,
        easing: cubicOut,
      }}
    >
      <span class="emoji">{category.emoji}</span>
      <span class="name">{category.name}</span>
      <span class="count">{category.count}가지</span>
    </div>
  {/each}
</div>

<style>
  .categories {
    display: grid;
    grid-template-columns: repeat(2, 18rem);
    justify-content: center;
    gap: 2.6rem;
    align-content: start;
  }
  .kind {
    aspect-ratio: 1;
    border-radius: var(--radius-l);
    background: linear-gradient(160deg, #f6f9ff, var(--tint-2));
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.6rem;
  }
  .emoji {
    font-size: 5rem;
  }
  .name {
    font-size: 2.4rem;
    font-weight: 700;
    letter-spacing: -0.02em;
  }
  .count {
    font-size: 1.5rem;
    color: var(--muted);
  }
</style>
