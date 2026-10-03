<script lang="ts">
  // The assistant's presence: a calm orb that shows what the assistant is doing.
  // Replace the orb with a real avatar later by passing `children`: it gets the same
  // `state` and `level` (0..1, the microphone while listening, the voice while speaking).
  import type { Snippet } from 'svelte';
  import { Spring } from 'svelte/motion';
  import type { AssistantState } from '../events';

  let {
    state,
    level = 0,
    size = 5,
    children,
  }: { state: AssistantState; level?: number; size?: number; children?: Snippet } = $props();

  const smooth = new Spring(0, { stiffness: 0.18, damping: 0.55 });
  $effect(() => {
    smooth.target = state === 'listening' || state === 'speaking' ? level : 0;
  });
</script>

<div
  class="presence {state}"
  style:--size="{size}rem"
  style:--level={smooth.current}
  role="img"
  aria-label={state}
>
  {#if children}
    {@render children()}
  {:else}
    <span class="ring r1"></span>
    <span class="ring r2"></span>
    <span class="orb">
      {#if state === 'thinking'}
        <span class="dots"><i></i><i></i><i></i></span>
      {:else if state === 'speaking'}
        <span class="bars"><i></i><i></i><i></i><i></i><i></i></span>
      {:else if state === 'listening'}
        <span class="mic"></span>
      {/if}
    </span>
    {#if state === 'connecting'}<span class="arc"></span>{/if}
  {/if}
</div>

<style>
  .presence {
    position: relative;
    width: var(--size);
    height: var(--size);
    flex: none;
    display: grid;
    place-items: center;
  }
  .orb {
    position: absolute;
    inset: 12%;
    border-radius: 50%;
    background: radial-gradient(circle at 35% 30%, #f6d3b2, var(--accent-2) 45%, var(--accent));
    box-shadow:
      0 0.6rem 1.6rem rgb(184 105 47 / 0.35),
      inset 0 -0.4rem 0.8rem rgb(120 60 20 / 0.25);
    display: grid;
    place-items: center;
    transform: scale(calc(1 + var(--level) * 0.12));
    transition: transform 80ms linear;
  }
  .ring {
    position: absolute;
    inset: 12%;
    border-radius: 50%;
    border: 0.12rem solid var(--accent-2);
    opacity: 0;
  }

  /* idle: slow breathing */
  .idle .orb {
    animation: breathe 4.5s ease-in-out infinite;
  }
  .idle .r1 {
    animation: halo 4.5s ease-in-out infinite;
  }

  /* connecting: a spinning arc */
  .arc {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    border: 0.18rem solid transparent;
    border-top-color: var(--accent);
    animation: spin 0.9s linear infinite;
  }
  .connecting .orb {
    opacity: 0.75;
  }

  /* listening: rings follow the customer's voice */
  .listening .r1,
  .listening .r2 {
    opacity: calc(0.25 + var(--level) * 0.6);
    transform: scale(calc(1.08 + var(--level) * 0.35));
    transition: transform 90ms linear;
  }
  .listening .r2 {
    transform: scale(calc(1.18 + var(--level) * 0.6));
    opacity: calc(var(--level) * 0.45);
  }
  .mic {
    width: 18%;
    height: 30%;
    border-radius: 999px;
    background: rgb(255 255 255 / 0.9);
    box-shadow: 0 0 0 0.12rem rgb(255 255 255 / 0.35);
  }

  /* thinking: orbiting dots */
  .dots {
    position: relative;
    width: 55%;
    height: 55%;
    animation: spin 1.4s linear infinite;
  }
  .dots i {
    position: absolute;
    width: 22%;
    height: 22%;
    border-radius: 50%;
    background: white;
    left: 39%;
    top: 0;
    transform-origin: 50% 227%;
  }
  .dots i:nth-child(2) {
    transform: rotate(120deg);
    opacity: 0.75;
  }
  .dots i:nth-child(3) {
    transform: rotate(240deg);
    opacity: 0.5;
  }

  /* speaking: bars follow the assistant's voice */
  .bars {
    display: flex;
    align-items: center;
    gap: 6%;
    height: 50%;
    width: 52%;
  }
  .bars i {
    flex: 1;
    border-radius: 999px;
    background: white;
    height: calc(18% + var(--level) * 82% * var(--k));
    animation: wobble 0.5s ease-in-out infinite alternate;
  }
  .bars i:nth-child(1) {
    --k: 0.45;
    animation-delay: -0.1s;
  }
  .bars i:nth-child(2) {
    --k: 0.8;
    animation-delay: -0.3s;
  }
  .bars i:nth-child(3) {
    --k: 1;
  }
  .bars i:nth-child(4) {
    --k: 0.75;
    animation-delay: -0.2s;
  }
  .bars i:nth-child(5) {
    --k: 0.5;
    animation-delay: -0.4s;
  }
  .speaking .r1 {
    opacity: calc(var(--level) * 0.5);
    transform: scale(calc(1.1 + var(--level) * 0.3));
  }

  @keyframes breathe {
    0%,
    100% {
      transform: scale(0.96);
    }
    50% {
      transform: scale(1.03);
    }
  }
  @keyframes halo {
    0%,
    100% {
      opacity: 0;
      transform: scale(1);
    }
    50% {
      opacity: 0.35;
      transform: scale(1.18);
    }
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @keyframes wobble {
    from {
      transform: scaleY(0.75);
    }
    to {
      transform: scaleY(1.1);
    }
  }
</style>
