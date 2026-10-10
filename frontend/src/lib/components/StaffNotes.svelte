<script lang="ts">
  // Requests passed on to the staff ("아메리카노 얼음 적게"), with the order.
  import { fade } from 'svelte/transition';
  import { ui } from '../store.svelte';

  const notes = $derived(ui.state.order.notes);
</script>

{#if notes.length}
  <div class="notes box" in:fade={{ duration: 300 }}>
    <span class="label">직원 전달</span>
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
    gap: 1.4rem;
    align-items: baseline;
    padding: 1.2rem 1.6rem;
  }
  .label {
    flex: none;
    padding: 0.3rem 1rem;
    border-radius: 999px;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 1.5rem;
    font-weight: 700;
  }
  ul {
    margin: 0;
    padding: 0;
    list-style: none;
    font-size: 1.8rem;
    color: var(--text-2);
    line-height: 1.5;
  }
</style>
