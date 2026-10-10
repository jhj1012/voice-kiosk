<script lang="ts">
  // The order, always visible while ordering: a quiet bar at the bottom.
  import { fade } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import { Tween } from 'svelte/motion';
  import { won } from '../format';
  import { itemById } from '../menu';
  import { ui } from '../store.svelte';
  import ItemImage from './ItemImage.svelte';

  const order = $derived(ui.state.order);
  const total = new Tween(0, { duration: 700, easing: cubicOut });
  $effect(() => {
    total.target = order.total;
  });
</script>

<div class="bar" data-fly-target>
  <div class="thumbs">
    {#each order.lines.slice(-4) as line (`${line.item_id}|${line.options}`)}
      {@const item = itemById(ui.menu, line.item_id)}
      <div class="thumb" in:fade={{ duration: 300, delay: 650 }}>
        {#if item}<ItemImage {item} size="s" />{/if}
      </div>
    {/each}
  </div>
  <span class="count">주문 {order.count}개</span>
  <span class="total">{won(Math.round(total.current))}</span>
</div>

<style>
  .bar {
    display: flex;
    align-items: center;
    gap: 1.6rem;
    padding: 1.4rem 2.4rem 1.4rem 1.4rem;
    border-radius: var(--radius-l);
    background: var(--panel-soft);
    backdrop-filter: blur(2rem);
  }
  .thumbs {
    display: flex;
    gap: 0.6rem;
  }
  .thumb {
    width: 5rem;
  }
  .count {
    margin-left: 0.6rem;
    font-size: 1.9rem;
    color: var(--text-2);
  }
  .total {
    margin-left: auto;
    font-size: 2.8rem;
    font-weight: 800;
    letter-spacing: -0.02em;
  }
</style>
