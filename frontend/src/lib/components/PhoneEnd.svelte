<script lang="ts">
  // Phone mode: ends the conversation, like putting down the handset. A button rather than a
  // tap anywhere, so a customer pointing at the screen does not end the order by mistake.
  import { fade } from 'svelte/transition';

  let { onend }: { onend: () => void } = $props();

  function end(event: PointerEvent) {
    event.stopPropagation(); // not a tap on the page
    onend();
  }
</script>

<button class="end" onpointerup={end} transition:fade={{ duration: 250 }}>대화 끝내기</button>

<style>
  .end {
    position: absolute; /* in the page, inside its covered edges */
    top: calc(var(--safe-top, 0px) + 2.4rem);
    right: calc(var(--safe-right, 0px) + 3rem);
    z-index: 30;
    padding: 1.4rem 2.6rem;
    border: 0.25rem solid var(--line);
    border-radius: 999px;
    background: var(--panel);
    color: var(--text-2);
    font: inherit;
    font-size: 3rem;
    font-weight: 700;
    cursor: pointer;
  }
  .end:active {
    background: var(--accent-soft);
    color: var(--accent);
  }
</style>
