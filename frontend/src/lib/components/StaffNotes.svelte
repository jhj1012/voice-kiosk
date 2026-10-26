<script lang="ts">
  // Requests passed on to the staff ("아메리카노 얼음 적게"), with the order.
  import { fade } from 'svelte/transition';
  import { ui } from '../store.svelte';

  const notes = $derived(ui.state.order.notes);
</script>

{#if notes.length}
  <div class="notes box" in:fade={{ duration: 300 }}>
    <span class="label">직원에게 전달할 내용</span>
    <ul>
      {#each notes as note (note)}
        <li>{note}</li>
      {/each}
    </ul>
  </div>
{/if}

<style>
  .notes {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    padding: 1.6rem 1.8rem;
  }
  .label {
    align-self: flex-start;
    padding: 0.4rem 1.4rem;
    border-radius: 999px;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 2rem;
    font-weight: 700;
  }
  ul {
    margin: 0;
    padding: 0;
    list-style: none;
    font-size: 2.8rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--text);
    line-height: 1.4;
    word-break: keep-all;
  }
</style>
