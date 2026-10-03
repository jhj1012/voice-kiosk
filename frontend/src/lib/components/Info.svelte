<script lang="ts">
  // Cafe information (Wi-Fi, restroom, hours, ...).
  import { TOPIC_ICONS } from '../menu';
  import { ui } from '../store.svelte';

  const topic = $derived(ui.cafe?.topics.find((t) => t.id === ui.state.view.topic));
</script>

{#if topic}
  <div class="info">
    <span class="icon">{TOPIC_ICONS[topic.id] ?? 'ℹ️'}</span>
    <h2>{topic.title}</h2>
    <p>{topic.text}</p>
  </div>
{/if}

<style>
  .info {
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    gap: 1.6rem;
    padding: 0 3rem;
  }
  .icon {
    font-size: 6rem;
  }
  h2 {
    font-size: 3.6rem;
    font-weight: 800;
    letter-spacing: -0.03em;
  }
  p {
    font-size: 2.4rem;
    line-height: 1.6;
    color: var(--text-2);
    word-break: keep-all;
  }
</style>
