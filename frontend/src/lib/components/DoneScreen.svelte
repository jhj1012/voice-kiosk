<script lang="ts">
  // Paid: the order number, large. The backend returns to the attract screen.
  import { fly, scale } from 'svelte/transition';
  import { backOut, cubicOut } from 'svelte/easing';
  import { ui } from '../store.svelte';
</script>

<div class="done">
  <svg class="check" viewBox="0 0 52 52" in:scale|global={{ duration: 500, easing: backOut }}>
    <circle cx="26" cy="26" r="24" />
    <path d="M15 27 l7 7 l15 -16" />
  </svg>
  <h2 in:fly|global={{ y: 16, delay: 250, duration: 500, easing: cubicOut }}>
    주문이 완료되었어요
  </h2>
  <div class="number" in:fly|global={{ y: 24, delay: 400, duration: 600, easing: cubicOut }}>
    <span class="label">주문 번호</span>
    <span class="value">{ui.state.payment?.order_number ?? ''}</span>
  </div>
  <p in:fly|global={{ y: 16, delay: 600, duration: 500, easing: cubicOut }}>
    번호가 불리면 픽업대에서 받아 가세요 · 수화기를 내려놓아 주세요
  </p>
</div>

<style>
  .done {
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1.6rem;
  }
  .check {
    width: 7rem;
    height: 7rem;
  }
  .check circle {
    fill: var(--ok);
  }
  .check path {
    fill: none;
    stroke: white;
    stroke-width: 4;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-dasharray: 40;
    stroke-dashoffset: 40;
    animation: draw 0.6s 0.35s var(--ease-out) forwards;
  }
  h2 {
    font-size: 3rem;
    font-weight: 800;
    letter-spacing: -0.03em;
  }
  .number {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 1.6rem 5rem 2rem;
    border-radius: var(--radius-l);
    background: var(--surface);
    box-shadow: var(--shadow-l);
  }
  .label {
    font-size: 1.6rem;
    color: var(--muted);
    font-weight: 600;
  }
  .value {
    font-size: 10rem;
    font-weight: 800;
    line-height: 1;
    letter-spacing: -0.05em;
    color: var(--accent);
  }
  p {
    font-size: 1.8rem;
    color: var(--text-2);
  }
  @keyframes draw {
    to {
      stroke-dashoffset: 0;
    }
  }
</style>
