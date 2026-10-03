<script lang="ts">
  // What the customer said and what the assistant says, as it is spoken.
  import { fly } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import { ui } from '../store.svelte';
</script>

<div class="subtitles" aria-live="polite">
  {#each ui.subtitles as line, i (line.id)}
    <p
      class={line.speaker}
      class:latest={i === ui.subtitles.length - 1}
      in:fly={{ y: 14, duration: 350, easing: cubicOut }}
    >
      {#if line.speaker === 'customer'}<span class="who">손님</span>{/if}
      <span class="text">{line.text}</span>
    </p>
  {/each}
</div>

<style>
  .subtitles {
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    gap: 0.6rem;
    min-width: 0;
    flex: 1;
  }
  p {
    display: flex;
    align-items: baseline;
    gap: 0.8rem;
    opacity: 0.5;
    transition: opacity 0.4s;
    line-height: 1.35;
    word-break: keep-all;
  }
  p.latest {
    opacity: 1;
  }
  .assistant {
    font-size: 2rem;
    font-weight: 600;
    letter-spacing: -0.015em;
  }
  .customer {
    font-size: 1.6rem;
    color: var(--text-2);
  }
  .who {
    flex: none;
    font-size: 1.05rem;
    font-weight: 700;
    color: var(--accent);
    background: var(--accent-soft);
    padding: 0.2rem 0.6rem;
    border-radius: 999px;
  }
</style>
