<script lang="ts">
  import { fly } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';

  let { level, text }: { level: string; text: string } = $props();
</script>

<div
  class="notice {level}"
  role="status"
  transition:fly={{ y: -40, duration: 400, easing: cubicOut }}
>
  {#if level !== 'info'}<span class="dot"></span>{/if}
  {text}
</div>

<style>
  .notice {
    position: absolute;
    top: 1.6rem;
    left: 50%;
    translate: -50% 0;
    z-index: 20;
    display: flex;
    align-items: center;
    gap: 0.8rem;
    padding: 0.9rem 1.6rem;
    border-radius: 999px;
    background: white;
    border: 1px solid var(--line);
    font-size: 1.4rem;
    font-weight: 600;
  }
  .dot {
    width: 0.8rem;
    height: 0.8rem;
    border-radius: 50%;
    background: var(--warn);
    animation: pulse 1.2s ease-in-out infinite;
  }
  .error .dot {
    background: var(--error);
  }
  @keyframes pulse {
    50% {
      opacity: 0.3;
    }
  }
</style>
