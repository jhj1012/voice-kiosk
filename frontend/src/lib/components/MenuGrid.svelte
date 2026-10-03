<script lang="ts">
  // The items the assistant chose, as a clean list with large pictures (customers choose by
  // the picture). When it shows other items, rows that stay move to their new places and the
  // others fade: the page never "changes".
  import { flip } from 'svelte/animate';
  import { fade } from 'svelte/transition';
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
  // More than five rows only fit when they are a little smaller.
  const compact = $derived(items.length > 5);
</script>

<div class="menu" class:compact>
  {#key view.title}
    <p class="caption" in:fade={{ duration: 400, delay: 200 }}>{view.title}</p>
  {/key}
  {#if items.length === 0}
    <p class="empty" in:fade>해당하는 메뉴가 없어요</p>
  {/if}
  <ul>
    {#each items as item, i (item.id)}
      <li
        animate:flip={{ duration: 550, easing: cubicOut }}
        in:fade|global={{ duration: 450, delay: 120 + i * 70, easing: cubicOut }}
        out:fade={{ duration: 200 }}
      >
        <div
          class="picture"
          data-fly-source={item.id}
          in:receive|global={{ key: item.id }}
          out:send|global={{ key: item.id }}
        >
          <ItemImage {item} />
        </div>
        <div class="what">
          <span class="name">{item.name}</span>
          <span class="description">{item.description}</span>
        </div>
        <span class="price">{won(item.price)}</span>
      </li>
    {/each}
  </ul>
</div>

<style>
  .menu {
    height: 100%;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    padding: 0 1rem;
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
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li {
    display: grid;
    grid-template-columns: 10.5rem 1fr auto;
    align-items: center;
    gap: 2.2rem;
    padding: 1.4rem 0;
    border-bottom: 1px solid var(--line);
  }
  li:last-child {
    border-bottom: none;
  }
  .compact li {
    grid-template-columns: 7.5rem 1fr auto;
    padding: 1rem 0;
  }
  .what {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    min-width: 0;
  }
  .name {
    font-size: 2.5rem;
    font-weight: 700;
    letter-spacing: -0.02em;
  }
  .description {
    font-size: 1.6rem;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .price {
    font-size: 2.3rem;
    font-weight: 600;
  }
  .compact .name {
    font-size: 2.1rem;
  }
</style>
