<script lang="ts">
  // What the customer said and what the assistant says, centered under the assistant.
  import { fade } from 'svelte/transition';
  import { ui } from '../store.svelte';
</script>

<div class="subtitles" aria-live="polite">
  {#each ui.subtitles as line, i (line.id)}
    <p
      class={line.speaker}
      class:latest={i === ui.subtitles.length - 1}
      in:fade={{ duration: 300 }}
    >
      {line.speaker === 'customer' ? `“${line.text}”` : line.text}
    </p>
  {/each}
</div>

<style>
  .subtitles {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.9rem;
    text-align: center;
  }
  p {
    line-height: 1.4;
    word-break: keep-all;
    opacity: 0.45;
    transition: opacity 0.4s;
  }
  p.latest {
    opacity: 1;
  }
  .assistant {
    font-size: 2.5rem;
    font-weight: 600;
    letter-spacing: -0.02em;
  }
  .customer {
    font-size: 1.9rem;
    color: var(--accent);
  }
</style>
