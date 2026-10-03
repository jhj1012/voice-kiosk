<script lang="ts">
  // The simulated card terminal: insert the card -> processing.
  import { fade } from 'svelte/transition';
  import { won } from '../format';
  import { ui } from '../store.svelte';

  const step = $derived(ui.state.payment?.step ?? 'insert_card');
</script>

<div class="payment">
  <div class="terminal" class:processing={step !== 'insert_card'}>
    <div class="slot"></div>
    <div class="card"><span class="chip"></span></div>
    <div class="body">
      <div class="screen">
        {#if step === 'insert_card'}
          <span in:fade>{won(ui.state.order.total)}</span>
        {:else}
          <span class="spinner" in:fade></span>
        {/if}
      </div>
      <div class="keys">
        {#each [1, 2, 3, 4, 5, 6, 7, 8, 9] as key (key)}<i></i>{/each}
      </div>
    </div>
  </div>

  <div class="text">
    {#key step}
      <h2 in:fade={{ duration: 300 }}>
        {step === 'insert_card' ? '카드를 단말기에 꽂아 주세요' : '결제 중...'}
      </h2>
    {/key}
    <p>결제 금액 <strong>{won(ui.state.order.total)}</strong></p>
  </div>
</div>

<style>
  .payment {
    height: 100%;
    display: grid;
    grid-template-columns: auto auto;
    justify-content: center;
    align-items: center;
    gap: 7rem;
  }
  .terminal {
    position: relative;
    width: 18rem;
    height: 30rem;
  }
  .body {
    position: absolute;
    z-index: 2;
    inset: 4rem 0 0;
    border-radius: 2.4rem;
    background: linear-gradient(160deg, #3b332d, #1f1915);
    box-shadow: var(--shadow-l);
    padding: 2rem 1.8rem;
    display: flex;
    flex-direction: column;
    gap: 1.8rem;
  }
  .screen {
    height: 7rem;
    border-radius: 1rem;
    background: #d9eadf;
    display: grid;
    place-items: center;
    font-size: 1.8rem;
    font-weight: 700;
    color: #24392c;
  }
  .keys {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.9rem;
  }
  .keys i {
    height: 2.4rem;
    border-radius: 0.6rem;
    background: #4a413a;
  }
  .slot {
    position: absolute;
    top: 3.4rem;
    left: 2.5rem;
    right: 2.5rem;
    height: 1.2rem;
    border-radius: 0.6rem;
    background: #120e0b;
    z-index: 3;
  }
  .card {
    position: absolute;
    left: 50%;
    width: 8.6rem;
    margin-left: -4.3rem;
    height: 13.6rem;
    top: -11rem;
    border-radius: 0.9rem;
    background: linear-gradient(160deg, var(--accent-2), var(--accent));
    box-shadow: var(--shadow-m);
    z-index: 1;
    animation: insert 2.6s var(--ease-out) infinite;
  }
  .processing .card {
    animation: none;
    transform: translateY(9rem);
  }
  .chip {
    position: absolute;
    left: 1.4rem;
    bottom: 2.2rem;
    width: 2rem;
    height: 2.6rem;
    border-radius: 0.4rem;
    background: #f3d9a4;
  }
  .spinner {
    width: 3rem;
    height: 3rem;
    border-radius: 50%;
    border: 0.35rem solid rgb(36 57 44 / 0.2);
    border-top-color: #24392c;
    animation: spin 0.8s linear infinite;
  }
  .text {
    display: flex;
    flex-direction: column;
    gap: 1.4rem;
  }
  h2 {
    font-size: 4rem;
    font-weight: 800;
    letter-spacing: -0.035em;
  }
  p {
    font-size: 2rem;
    color: var(--text-2);
  }
  strong {
    color: var(--text);
  }
  @keyframes insert {
    0% {
      transform: translateY(-3rem);
      opacity: 0;
    }
    20% {
      opacity: 1;
    }
    60%,
    85% {
      transform: translateY(9rem);
      opacity: 1;
    }
    100% {
      transform: translateY(9rem);
      opacity: 0;
    }
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
