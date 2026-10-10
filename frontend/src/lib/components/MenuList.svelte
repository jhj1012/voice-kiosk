<script lang="ts">
  // The items the assistant chose, as a list. When it shows other items, the rows that stay
  // move to their new places and the others fade: the page never "changes".
  import { flip } from 'svelte/animate';
  import { fade, fly } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import { won } from '../format';
  import { itemById } from '../menu';
  import type { MenuItem } from '../events';
  import { ui } from '../store.svelte';
  import ItemImage from './ItemImage.svelte';

  const view = $derived(ui.state.view);
  const items = $derived(
    view.item_ids.map((id) => itemById(ui.menu, id)).filter((i): i is MenuItem => !!i),
  );
  // A long list (the whole menu) takes two columns so it still fits over the avatar.
  const wide = $derived(items.length > 6);
</script>

<div class="menu">
  {#if view.title}
    {#key view.title}
      <p class="caption" in:fade={{ duration: 400, delay: 200 }}>{view.title}</p>
    {/key}
  {/if}
  {#if items.length === 0}
    <p class="caption" in:fade>해당하는 메뉴가 없어요</p>
  {/if}
  <ul class="list" class:wide>
    {#each items as item, i (item.id)}
      <li
        class="row"
        class:highlight={view.highlight.includes(item.id)}
        animate:flip={{ duration: 450, easing: cubicOut }}
        in:fly|global={{ y: 16, opacity: 0, duration: 400, delay: 80 + i * 50, easing: cubicOut }}
        out:fade={{ duration: 180 }}
      >
        <div class="thumb" data-fly-source={item.id}><ItemImage {item} size="s" /></div>
        <span class="name">{item.name}</span>
        <span class="price">{won(item.price)}</span>
      </li>
    {/each}
  </ul>
</div>

<style>
  .menu {
    display: flex;
    flex-direction: column;
    gap: 1.4rem;
  }
  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .wide {
    display: grid;
    grid-template-columns: 1fr 1fr;
    column-gap: 1.6rem;
  }
  .wide .row {
    border-top: none;
  }
  .thumb {
    width: 7.5rem;
    flex: none;
  }
  .wide .thumb {
    width: 5.5rem;
  }
  .name {
    flex: 1;
    font-size: 2.5rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    word-break: keep-all;
  }
  .wide .name {
    font-size: 2rem;
  }
  .price {
    font-size: 2rem;
    color: var(--text-2);
  }
  .wide .price {
    font-size: 1.6rem;
  }
  .highlight .name {
    color: var(--accent);
  }
</style>
