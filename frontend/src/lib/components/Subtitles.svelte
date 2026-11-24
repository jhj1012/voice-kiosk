<script lang="ts">
  // What the customer said and what the assistant says (each can be turned off in the
  // developer panel), centered under the assistant.
  import { fade } from 'svelte/transition';
  import { ui } from '../store.svelte';

  const lines = $derived(
    ui.subtitles.filter((line) =>
      line.speaker === 'customer' ? ui.settings.subtitlesCustomer : ui.settings.subtitlesAssistant,
    ),
  );
</script>

<div class="subtitles" aria-live="polite">
  {#each lines as line, i (line.id)}
    <p class={line.speaker} class:latest={i === lines.length - 1} in:fade={{ duration: 300 }}>
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
    --text-role: subtitles-assistant;
    font-size: calc(2.5rem * var(--size-all) * var(--fs-subtitles-assistant, 1));
    font-weight: 600;
    letter-spacing: -0.02em;
  }
  .customer {
    --text-role: subtitles-customer;
    font-size: calc(1.9rem * var(--size-all) * var(--fs-subtitles-customer, 1));
    color: var(--accent);
  }
</style>
