<script lang="ts">
  // The items the assistant chose. When it shows other items, the cards that stay move to their
  // new places and the others fade: the page never "changes".
  import { flip } from 'svelte/animate';
  import { fade, scale } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import { won } from '../format';
  import { itemById } from '../menu';
  import type { MenuItem } from '../events';
  import { ui } from '../store.svelte';
  import { receive, send } from '../transitions';
  import ItemImage from './ItemImage.svelte';

  const view = $derived(ui.state.view);
  const items = $derived(
    view.item_ids.map((id) => itemById(ui.menu, id)).filter((i): i is MenuItem => !!i),
  );
  const columns = $derived(items.length <= 4 ? 2 : items.length <= 6 ? 3 : 4);
</script>

<div class="menu" style:--columns={columns}>
  {#key view.title}
    <p class="caption" in:fade={{ duration: 400, delay: 200 }}>{view.title}</p>
  {/key}
  {#if items.length === 0}
    <p class="empty" in:fade>해당하는 메뉴가 없어요</p>
  {/if}
  <div class="grid">
    {#each items as item, i (item.id)}
      <article
        class="card"
        animate:flip={{ duration: 550, easing: cubicOut }}
        in:scale|global={{
          start: 0.94,
          opacity: 0,
          duration: 450,
          delay: 120 + i * 60,
          easing: cubicOut,
        }}
        out:fade={{ duration: 200 }}
      >
        <div
          data-fly-source={item.id}
          in:receive|global={{ key: item.id }}
          out:send|global={{ key: item.id }}
        >
          <ItemImage {item} />
        </div>
        <span class="name">{item.name}</span>
        <span class="price">{won(item.price)}</span>
      </article>
    {/each}
  </div>
</div>

<style>
  .menu {
    height: 100%;
    display: flex;
    flex-direction: column;
    gap: 1.6rem;
  }
  .caption {
    min-height: 2.2rem;
    font-size: 1.7rem;
    font-weight: 600;
    color: var(--muted);
    text-align: center;
  }
  .empty {
    font-size: 2.2rem;
    color: var(--muted);
    text-align: center;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(var(--columns), minmax(0, 23rem));
    justify-content: center;
    gap: 3rem 2.6rem;
    align-content: start;
  }
  .card {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .card > div {
    margin-bottom: 0.8rem;
  }
  .name {
    font-size: 2.1rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    word-break: keep-all;
  }
  .price {
    font-size: 1.7rem;
    color: var(--text-2);
  }
</style>
