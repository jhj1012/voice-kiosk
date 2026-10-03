<script lang="ts">
  // One item, large: its card's image grows into this one. While the customer is choosing it,
  // only the required options are shown, as minimal choices.
  import { fade } from 'svelte/transition';
  import { won } from '../format';
  import { allergenNames, CAFFEINE, groupById, itemById, SERVED } from '../menu';
  import { ui } from '../store.svelte';
  import { receive, send } from '../transitions';
  import ItemImage from './ItemImage.svelte';

  const item = $derived(itemById(ui.menu, ui.state.view.item_id));
  const pending = $derived(
    ui.state.pending?.item_id === ui.state.view.item_id ? ui.state.pending : null,
  );
  const groups = $derived(
    pending && item
      ? item.options
          .map((id) => groupById(ui.menu, id))
          .filter((g) => g && (g.required || pending.chosen[g.id]))
      : [],
  );
  const allergens = $derived(item && ui.menu ? allergenNames(ui.menu, item.allergens) : []);
  const facts = $derived(
    item
      ? [
          CAFFEINE[item.caffeine],
          `단맛 ${'●'.repeat(item.sweetness)}${'○'.repeat(3 - item.sweetness)}`,
          ...(item.temperature ? [SERVED[item.temperature]] : []),
          allergens.length ? `${allergens.join('·')} 포함` : '알레르기 표시 없음',
        ]
      : [],
  );
</script>

{#if item}
  <div class="item">
    <div
      class="hero"
      data-fly-source={item.id}
      in:receive|global={{ key: item.id }}
      out:send|global={{ key: item.id }}
    >
      <ItemImage {item} size="l" />
    </div>

    <div class="text" in:fade|global={{ duration: 400, delay: 350 }}>
      <h2>{item.name}</h2>
      <p class="price">
        {won(item.price)}{#if pending && pending.quantity > 1}<span class="qty">
            × {pending.quantity}</span
          >{/if}
      </p>
      <p class="description">{item.description}</p>
      <p class="facts">{item.ingredients.join(', ')}</p>
      <p class="facts">{facts.join('  ·  ')}</p>
    </div>

    {#if groups.length && pending}
      <div class="choices" in:fade|global={{ duration: 400, delay: 500 }}>
        {#each groups as group (group!.id)}
          {@const chosen = pending.chosen[group!.id] ?? []}
          <div class="group" class:missing={pending.missing.includes(group!.id)}>
            {#each group!.choices as choice (choice.id)}
              <span class="choice" class:chosen={chosen.includes(choice.id)}>
                {choice.say || choice.name}
                {#if choice.price}<small>+{won(choice.price)}</small>{/if}
              </span>
            {/each}
          </div>
        {/each}
      </div>
    {/if}
  </div>
{/if}

<style>
  .item {
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2.6rem;
  }
  .hero {
    width: 32rem;
  }
  .text {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: 0.8rem;
  }
  h2 {
    font-size: 4.4rem;
    font-weight: 800;
    letter-spacing: -0.04em;
  }
  .price {
    font-size: 2.2rem;
    color: var(--text-2);
  }
  .qty {
    color: var(--accent);
    font-weight: 700;
  }
  .description {
    margin-top: 0.8rem;
    font-size: 2rem;
    line-height: 1.5;
    color: var(--text-2);
    word-break: keep-all;
    max-width: 50rem;
  }
  .facts {
    font-size: 1.6rem;
    color: var(--muted);
    white-space: pre;
  }
  .choices {
    display: flex;
    flex-direction: column;
    gap: 1.4rem;
    width: 100%;
    max-width: 48rem;
  }
  .group {
    display: grid;
    grid-auto-flow: column;
    grid-auto-columns: 1fr;
    gap: 1.2rem;
  }
  .choice {
    padding: 1.6rem 1rem;
    border-radius: var(--radius-m);
    background: var(--tint);
    font-size: 2.2rem;
    font-weight: 600;
    text-align: center;
    color: var(--text-2);
    transition:
      background 0.35s var(--ease-out),
      color 0.35s;
  }
  .choice small {
    display: block;
    font-size: 1.3rem;
    font-weight: 500;
    opacity: 0.8;
  }
  .choice.chosen {
    background: var(--accent);
    color: white;
  }
  .missing .choice {
    animation: invite 1.8s ease-in-out infinite;
  }
  @keyframes invite {
    50% {
      background: var(--tint-2);
    }
  }
</style>
