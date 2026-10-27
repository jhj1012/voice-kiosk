<script lang="ts">
  // The whole order, read back before payment.
  import { fade } from 'svelte/transition';
  import { won } from '../format';
  import { itemById, optionLabels, unitOf } from '../menu';
  import { ui } from '../store.svelte';
  import ItemImage from './ItemImage.svelte';
  import StaffNotes from './StaffNotes.svelte';

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
          {#if optionLabels(ui.menu, line.chosen)}<span class="options"
              >{optionLabels(ui.menu, line.chosen)}</span
            >{/if}
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
  <StaffNotes />
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
    --text-role: review-name;
    font-size: calc(2.3rem * var(--size-all) * var(--fs-review-name, 1));
    font-weight: 700;
  }
  .options {
    --text-role: review-options;
    font-size: calc(1.6rem * var(--size-all) * var(--fs-review-options, 1));
    color: var(--muted);
  }
  .qty {
    --text-role: review-qty;
    font-size: calc(2rem * var(--size-all) * var(--fs-review-qty, 1));
    color: var(--text-2);
  }
  .amount {
    --text-role: review-amount;
    font-size: calc(2.2rem * var(--size-all) * var(--fs-review-amount, 1));
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
    --text-role: review-dining;
    font-size: calc(1.8rem * var(--size-all) * var(--fs-review-dining, 1));
    font-weight: 700;
  }
  .label {
    margin-left: auto;
    --text-role: review-label;
    font-size: calc(1.9rem * var(--size-all) * var(--fs-review-label, 1));
    color: var(--muted);
  }
  .value {
    --text-role: review-value;
    font-size: calc(4.4rem * var(--size-all) * var(--fs-review-value, 1));
    font-weight: 800;
    letter-spacing: -0.03em;
  }
</style>
