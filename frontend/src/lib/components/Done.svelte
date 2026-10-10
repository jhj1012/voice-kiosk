<script lang="ts">
  // Paid: the order number, large. The backend returns to the start.
  import { fade, scale } from 'svelte/transition';
  import { backOut } from 'svelte/easing';
  import { ui } from '../store.svelte';
</script>

<div class="done box">
  <svg class="check" viewBox="0 0 52 52" in:scale|global={{ duration: 500, easing: backOut }}>
    <circle cx="26" cy="26" r="24" />
    <path d="M15 27 l7 7 l15 -16" />
  </svg>
  <p class="label" in:fade|global={{ delay: 250, duration: 400 }}>주문 번호</p>
  <p class="number" in:fade|global={{ delay: 400, duration: 500 }}>
    {ui.state.payment?.order_number ?? ''}
  </p>
  <p class="note" in:fade|global={{ delay: 600, duration: 500 }}>
    번호가 불리면 픽업대에서 받아 가세요
  </p>
</div>

<style>
  .done {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1.2rem;
    padding: 3rem;
  }
  .check {
    width: 7rem;
    height: 7rem;
    margin-bottom: 1.6rem;
  }
  .check circle {
    fill: var(--accent);
  }
  .check path {
    fill: none;
    stroke: var(--on-accent);
    stroke-width: 4;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-dasharray: 40;
    stroke-dashoffset: 40;
    animation: draw 0.6s 0.35s var(--ease-out) forwards;
  }
  .label {
    font-size: 2rem;
    color: var(--muted);
  }
  .number {
    font-size: 14rem;
    font-weight: 800;
    line-height: 1;
    letter-spacing: -0.05em;
    color: var(--accent);
  }
  .note {
    margin-top: 1rem;
    font-size: 2.1rem;
    color: var(--text-2);
  }
  @keyframes draw {
    to {
      stroke-dashoffset: 0;
    }
  }
</style>
