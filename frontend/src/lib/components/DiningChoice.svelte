<script lang="ts">
  // The first question: here or to go? (Also when it is still unknown at payment.)
  import { cubicOut } from 'svelte/easing';
  import { fly } from 'svelte/transition';
  import { ui } from '../store.svelte';

  const CHOICES = [
    { id: 'here', emoji: '🍽️', label: '매장에서 먹어요' },
    { id: 'to_go', emoji: '🛍️', label: '포장해 가요' },
  ] as const;
</script>

<ul class="list">
  {#each CHOICES as choice, i (choice.id)}
    <li
      class="row"
      class:chosen={ui.state.order.dining === choice.id}
      in:fly|global={{ y: 16, opacity: 0, duration: 400, delay: 80 + i * 70, easing: cubicOut }}
    >
      <span class="emoji">{choice.emoji}</span>
      <span class="label">{choice.label}</span>
    </li>
  {/each}
</ul>

<style>
  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .row {
    min-height: 9rem;
  }
  .emoji {
    font-size: 4rem;
    width: 6rem;
    text-align: center;
  }
  .label {
    font-size: 3rem;
    font-weight: 700;
    letter-spacing: -0.02em;
  }
</style>
