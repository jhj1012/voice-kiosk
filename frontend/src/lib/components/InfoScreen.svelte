<script lang="ts">
  // A card with cafe information (Wi-Fi, restroom, hours, ...).
  import { TOPIC_ICONS } from '../menu';
  import { ui } from '../store.svelte';

  const topic = $derived(ui.cafe?.topics.find((t) => t.id === ui.state.view.topic));
</script>

{#if topic}
  <div class="info">
    <div class="card">
      <span class="icon">{TOPIC_ICONS[topic.id] ?? 'ℹ️'}</span>
      <h2>{topic.title}</h2>
      <p>{topic.text}</p>
    </div>
  </div>
{/if}

<style>
  .info {
    height: 100%;
    display: grid;
    place-items: center;
  }
  .card {
    width: min(64rem, 80%);
    padding: 4rem 4.5rem;
    border-radius: var(--radius-l);
    background: var(--surface);
    box-shadow: var(--shadow-l);
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 1.4rem;
  }
  .icon {
    font-size: 5rem;
  }
  h2 {
    font-size: 3.4rem;
    font-weight: 800;
    letter-spacing: -0.03em;
  }
  p {
    font-size: 2.2rem;
    line-height: 1.55;
    color: var(--text-2);
    word-break: keep-all;
  }
</style>
