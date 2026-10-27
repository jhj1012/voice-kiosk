<script lang="ts">
  // Cafe information (Wi-Fi, restroom, hours, ...).
  import { TOPIC_ICONS } from '../menu';
  import { ui } from '../store.svelte';

  const topic = $derived(ui.cafe?.topics.find((t) => t.id === ui.state.view.topic));
</script>

{#if topic}
  <div class="info box">
    <span class="icon">{TOPIC_ICONS[topic.id] ?? 'ℹ️'}</span>
    <h2>{topic.title}</h2>
    <p>{topic.text}</p>
  </div>
{/if}

<style>
  .info {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 1.4rem;
    padding: 3rem;
  }
  .icon {
    --text-role: info-icon;
    font-size: calc(6rem * var(--size-all) * var(--fs-info-icon, 1));
  }
  h2 {
    --text-role: info-h2;
    font-size: calc(3.6rem * var(--size-all) * var(--fs-info-h2, 1));
    font-weight: 800;
    letter-spacing: -0.03em;
  }
  p {
    --text-role: info-p;
    font-size: calc(2.4rem * var(--size-all) * var(--fs-info-p, 1));
    line-height: 1.6;
    color: var(--text-2);
    word-break: keep-all;
  }
</style>
