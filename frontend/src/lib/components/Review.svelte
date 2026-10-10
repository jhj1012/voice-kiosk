<script lang="ts">
  // The whole order, read back before payment.
  import { fade } from 'svelte/transition';
  import { won } from '../format';
  import { itemById, unitOf } from '../menu';
  import { ui } from '../store.svelte';
  import ItemImage from './ItemImage.svelte';

  const order = $derived(ui.state.order);
</script>

<div class="review">
  <ul class="list">
    {#each order.lines as line, i (line.line)}
      {@const item = itemById(ui.menu, line.item_id)}
      <li class="row" in:fade|global={{ duration: 400, delay: 150 + i * 80 }}>
        <div class="thumb">
          {#if item}<ItemImage {item} size="s" />{/if}
        </div>
        <div class="what">
          <span class="name">{line.name}</span>
          {#if line.options}<span class="options">{line.options}</span>{/if}
        </div>
        <span class="qty">{line.quantity}{unitOf(ui.menu, line.item_id)}</span>
        <span class="amount">{won(line.total)}</span>
      </li>
    {/each}
  </ul>
  <div class="total box">
    {#if order.dining}<span class="dining">{order.dining === 'here' ? '매장' : '포장'}</span>{/if}
    <span class="label">합계</span>
    <span class="value">{won(order.total)}</span>
  </div>
</div>

<style>
  .review {
    display: flex;
    flex-direction: column;
    gap: 1.8rem;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li.row {
    display: grid;
    grid-template-columns: 6rem 1fr auto 11rem;
  }
  .what {
    display: flex;
    flex-direction: column;
  }
  .name {
    font-size: 2.3rem;
    font-weight: 700;
  }
  .options {
    font-size: 1.6rem;
    color: var(--muted);
  }
  .qty {
    font-size: 2rem;
    color: var(--text-2);
  }
  .amount {
    font-size: 2.2rem;
    font-weight: 600;
    text-align: right;
  }
  .total {
    display: flex;
    align-items: baseline;
    gap: 1.4rem;
    padding: 1.2rem 1.6rem;
  }
  .dining {
    padding: 0.5rem 1.4rem;
    border-radius: 999px;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 1.8rem;
    font-weight: 700;
  }
  .label {
    margin-left: auto;
    font-size: 1.9rem;
    color: var(--muted);
  }
  .value {
    font-size: 4.4rem;
    font-weight: 800;
    letter-spacing: -0.03em;
  }
</style>
