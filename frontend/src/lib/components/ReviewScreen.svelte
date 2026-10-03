<script lang="ts">
  // The whole order, read back before payment (also "주문 내역 보여 주세요").
  import { fly } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import { won } from '../format';
  import { itemById, unitOf } from '../menu';
  import { ui } from '../store.svelte';
  import ItemImage from './ItemImage.svelte';

  const order = $derived(ui.state.order);
  const dining = $derived(
    order.dining === 'here' ? '매장에서 먹고 가요' : order.dining === 'to_go' ? '포장해요' : '',
  );
</script>

<div class="review">
  <div class="receipt">
    <h2>주문 내역을 확인해 주세요</h2>
    <ul>
      {#each order.lines as line, i (line.line)}
        {@const item = itemById(ui.menu, line.item_id)}
        <li in:fly|global={{ y: 18, duration: 450, delay: 200 + i * 90, easing: cubicOut }}>
          <div class="thumb">
            {#if item}<ItemImage {item} size="s" />{/if}
          </div>
          <div class="what">
            <span class="name">{line.name}</span>
            {#if line.options}<span class="options">{line.options}</span>{/if}
          </div>
          <span class="qty">{line.quantity}<small>{unitOf(ui.menu, line.item_id)}</small></span>
          <span class="amount">{won(line.total)}</span>
        </li>
      {/each}
    </ul>
    <div class="bottom">
      {#if dining}<span class="dining">{dining}</span>{/if}
      <span class="total-label">합계</span>
      <span class="total">{won(order.total)}</span>
    </div>
  </div>
</div>

<style>
  .review {
    height: 100%;
    display: grid;
    place-items: center;
  }
  .receipt {
    width: min(70rem, 85%);
    padding: 3.2rem 3.6rem;
    border-radius: var(--radius-l);
    background: var(--surface);
    box-shadow: var(--shadow-l);
    display: flex;
    flex-direction: column;
    gap: 1.8rem;
  }
  h2 {
    font-size: 2.6rem;
    font-weight: 800;
    letter-spacing: -0.03em;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
  }
  li {
    display: grid;
    grid-template-columns: 4.6rem 1fr 4rem 9rem;
    align-items: center;
    gap: 1.4rem;
    padding: 1rem 0;
    border-bottom: 1px solid var(--line);
  }
  .what {
    display: flex;
    flex-direction: column;
  }
  .name {
    font-size: 1.9rem;
    font-weight: 700;
  }
  .options {
    font-size: 1.35rem;
    color: var(--muted);
  }
  .qty {
    font-size: 1.7rem;
    text-align: right;
    color: var(--text-2);
  }
  .qty small {
    font-size: 1.2rem;
    margin-left: 0.15rem;
  }
  .amount {
    font-size: 1.8rem;
    font-weight: 600;
    text-align: right;
  }
  .bottom {
    display: flex;
    align-items: baseline;
    gap: 1.2rem;
  }
  .dining {
    padding: 0.5rem 1.2rem;
    border-radius: 999px;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 1.5rem;
    font-weight: 700;
  }
  .total-label {
    margin-left: auto;
    font-size: 1.6rem;
    color: var(--muted);
  }
  .total {
    font-size: 3.4rem;
    font-weight: 800;
    letter-spacing: -0.03em;
  }
</style>
