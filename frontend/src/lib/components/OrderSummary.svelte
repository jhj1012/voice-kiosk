<script lang="ts">
  // The small order summary that is always visible while ordering.
  import { flip } from 'svelte/animate';
  import { fly } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import { Tween } from 'svelte/motion';
  import { won } from '../format';
  import { itemById } from '../menu';
  import { ui } from '../store.svelte';
  import ItemImage from './ItemImage.svelte';

  const MAX_LINES = 4;
  const order = $derived(ui.state.order);
  const total = new Tween(0, { duration: 700, easing: cubicOut });
  $effect(() => {
    total.target = order.total;
  });
</script>

<aside class="summary" data-fly-target>
  <header>
    <span class="title">주문 <b>{order.count}</b>개</span>
    <span class="total">{won(Math.round(total.current))}</span>
  </header>
  <ul>
    {#each order.lines.slice(-MAX_LINES) as line (`${line.item_id}|${line.options}`)}
      {@const item = itemById(ui.menu, line.item_id)}
      <li
        animate:flip={{ duration: 400 }}
        in:fly={{ x: 30, duration: 450, delay: 350, easing: cubicOut }}
      >
        <div class="thumb">
          {#if item}<ItemImage {item} size="s" />{/if}
        </div>
        <div class="what">
          <span class="name">{line.name}</span>
          {#if line.options}<span class="options">{line.options}</span>{/if}
        </div>
        <span class="qty">×{line.quantity}</span>
      </li>
    {/each}
  </ul>
  {#if order.lines.length > MAX_LINES}
    <p class="more">외 {order.lines.length - MAX_LINES}개 메뉴</p>
  {/if}
  {#if order.dining}
    <p class="dining">{order.dining === 'here' ? '매장' : '포장'}</p>
  {/if}
</aside>

<style>
  .summary {
    width: 30rem;
    flex: none;
    align-self: flex-end;
    padding: 1.4rem 1.6rem;
    border-radius: var(--radius-m);
    background: var(--surface);
    box-shadow: var(--shadow-m);
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }
  .title {
    font-size: 1.4rem;
    color: var(--text-2);
  }
  .title b {
    color: var(--text);
  }
  .total {
    font-size: 2rem;
    font-weight: 800;
    letter-spacing: -0.02em;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  li {
    display: grid;
    grid-template-columns: 2.8rem 1fr auto;
    gap: 0.8rem;
    align-items: center;
  }
  .what {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .name {
    font-size: 1.3rem;
    font-weight: 600;
  }
  .options {
    font-size: 1rem;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .qty {
    font-size: 1.3rem;
    color: var(--text-2);
  }
  .more,
  .dining {
    font-size: 1.1rem;
    color: var(--muted);
  }
  .dining {
    align-self: flex-start;
    padding: 0.2rem 0.7rem;
    border-radius: 999px;
    background: var(--accent-soft);
    color: var(--accent);
    font-weight: 700;
  }
</style>
