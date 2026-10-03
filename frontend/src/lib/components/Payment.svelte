<script lang="ts">
  // The simulated card terminal: insert the card -> processing.
  import { fade } from 'svelte/transition';
  import { won } from '../format';
  import { ui } from '../store.svelte';

  const step = $derived(ui.state.payment?.step ?? 'insert_card');
</script>

<div class="payment">
  <div class="terminal" class:processing={step !== 'insert_card'}>
    <div class="card"><span class="chip"></span></div>
    <div class="slot"></div>
    <div class="body">
      <div class="screen">
        {#if step === 'insert_card'}
          <span in:fade>{won(ui.state.order.total)}</span>
        {:else}
          <span class="spinner" in:fade></span>
        {/if}
      </div>
    </div>
  </div>
  {#key step}
    <h2 in:fade={{ duration: 300 }}>
      {step === 'insert_card' ? '카드를 단말기에 꽂아 주세요' : '결제 중...'}
    </h2>
  {/key}
</div>

<style>
  .payment {
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 4rem;
  }
  .terminal {
    position: relative;
    width: 20rem;
    height: 30rem;
  }
  .body {
    position: absolute;
    z-index: 2;
    inset: 9rem 0 0;
    border-radius: 2.6rem;
    background: linear-gradient(170deg, #26364d, #142033);
    padding: 2.2rem;
  }
  .screen {
    height: 8rem;
    border-radius: 1.2rem;
    background: #dbe9ff;
    display: grid;
    place-items: center;
    font-size: 2.2rem;
    font-weight: 700;
    color: #142033;
  }
  .slot {
    position: absolute;
    z-index: 3;
    top: 8.4rem;
    left: 3rem;
    right: 3rem;
    height: 1.2rem;
    border-radius: 0.6rem;
    background: #0b1422;
  }
  .card {
    position: absolute;
    z-index: 1;
    left: 50%;
    width: 9rem;
    margin-left: -4.5rem;
    height: 14rem;
    top: -4rem;
    border-radius: 1rem;
    background: linear-gradient(160deg, var(--accent-2), var(--accent));
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
    width: 2.2rem;
    height: 2.8rem;
    border-radius: 0.4rem;
    background: #e8f1ff;
  }
  .spinner {
    width: 3.4rem;
    height: 3.4rem;
    border-radius: 50%;
    border: 0.4rem solid rgb(20 32 51 / 0.15);
    border-top-color: #142033;
    animation: spin 0.8s linear infinite;
  }
  h2 {
    font-size: 3.6rem;
    font-weight: 800;
    letter-spacing: -0.03em;
  }
  @keyframes insert {
    0% {
      transform: translateY(-2rem);
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
