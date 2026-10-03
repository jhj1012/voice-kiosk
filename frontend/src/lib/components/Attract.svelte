<script lang="ts">
  // Waiting for a customer: calm, slow motion, one instruction.
  import { ui } from '../store.svelte';
  import AssistantPresence from './AssistantPresence.svelte';
  import ItemImage from './ItemImage.svelte';

  const items = $derived(ui.menu?.items ?? []);
</script>

<div class="attract">
  <div class="blob b1"></div>
  <div class="blob b2"></div>
  <div class="blob b3"></div>

  <div class="center">
    <AssistantPresence state="idle" size={13} />
    <h1>{ui.cafe?.name ?? ''}</h1>
    <p class="cta">
      <span class="handset" aria-hidden="true">📞</span>
      수화기를 들고 말씀해 주세요
    </p>
    <p class="sub">버튼 없이, 목소리로 주문해요</p>
  </div>

  {#if items.length}
    <div class="strip" aria-hidden="true">
      <div class="track">
        {#each [...items, ...items] as item, i (i)}
          <div class="mini">
            <ItemImage {item} size="m" />
            <span>{item.name}</span>
          </div>
        {/each}
      </div>
    </div>
  {/if}
</div>

<style>
  .attract {
    position: absolute;
    inset: 0;
    overflow: hidden;
    display: grid;
    place-items: center;
    background: linear-gradient(160deg, var(--bg), var(--bg-deep));
  }
  .blob {
    position: absolute;
    border-radius: 50%;
    filter: blur(5rem);
    opacity: 0.55;
  }
  .b1 {
    width: 46rem;
    height: 46rem;
    background: #f2cfae;
    left: -10rem;
    top: -12rem;
    animation: drift 22s ease-in-out infinite alternate;
  }
  .b2 {
    width: 38rem;
    height: 38rem;
    background: #e8d9c0;
    right: -8rem;
    top: 18rem;
    animation: drift 26s ease-in-out infinite alternate-reverse;
  }
  .b3 {
    width: 30rem;
    height: 30rem;
    background: #d7e6c4;
    left: 40%;
    bottom: -16rem;
    opacity: 0.35;
    animation: drift 30s ease-in-out infinite alternate;
  }
  .center {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1.6rem;
    margin-top: -10rem;
  }
  h1 {
    font-size: 6.4rem;
    font-weight: 800;
    letter-spacing: -0.04em;
    margin-top: 1rem;
  }
  .cta {
    font-size: 2.6rem;
    font-weight: 600;
    color: var(--text-2);
    display: flex;
    align-items: center;
    gap: 0.9rem;
  }
  .handset {
    display: inline-block;
    animation: ring 3.2s ease-in-out infinite;
    transform-origin: 70% 70%;
  }
  .sub {
    font-size: 1.5rem;
    color: var(--muted);
  }
  .strip {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 3.5rem;
    overflow: hidden;
    mask-image: linear-gradient(90deg, transparent, black 12%, black 88%, transparent);
  }
  .track {
    display: flex;
    gap: 1.6rem;
    width: max-content;
    animation: slide 70s linear infinite;
  }
  .mini {
    width: 9rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.6rem;
    font-size: 1.15rem;
    color: var(--text-2);
    opacity: 0.85;
  }
  @keyframes drift {
    to {
      transform: translate(6rem, 4rem) scale(1.1);
    }
  }
  @keyframes slide {
    to {
      transform: translateX(-50%);
    }
  }
  @keyframes ring {
    0%,
    70%,
    100% {
      transform: rotate(0);
    }
    74%,
    82%,
    90% {
      transform: rotate(-12deg);
    }
    78%,
    86% {
      transform: rotate(12deg);
    }
  }
</style>
