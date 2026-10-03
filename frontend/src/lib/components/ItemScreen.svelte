<script lang="ts">
  // One item, large: the card's image grows into the hero image. While the customer is
  // choosing this item, its required options are shown as minimal choices.
  import { fly } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import { won } from '../format';
  import { allergenNames, CAFFEINE, groupById, itemById, SERVED } from '../menu';
  import { ui } from '../store.svelte';
  import { receive, send } from '../transitions';
  import ItemImage from './ItemImage.svelte';

  const item = $derived(itemById(ui.menu, ui.state.view.item_id));
  const pending = $derived(
    ui.state.pending?.item_id === ui.state.view.item_id ? ui.state.pending : null,
  );
  // Required groups of this item: shown while choosing (chosen or still missing).
  const groups = $derived(
    pending && item
      ? item.options
          .map((id) => groupById(ui.menu, id))
          .filter((g) => g && (g.required || pending.chosen[g.id]))
      : [],
  );
  const allergens = $derived(item && ui.menu ? allergenNames(ui.menu, item.allergens) : []);
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

    <div class="info">
      <div class="title" in:fly|global={{ x: 30, duration: 500, delay: 250, easing: cubicOut }}>
        <h2>{item.name}</h2>
        <span class="price">{won(item.price)}</span>
        {#if pending && pending.quantity > 1}<span class="qty">× {pending.quantity}</span>{/if}
      </div>

      <p class="description" in:fly|global={{ x: 30, duration: 500, delay: 330, easing: cubicOut }}>
        {item.description}
      </p>

      <div class="facts" in:fly|global={{ x: 30, duration: 500, delay: 410, easing: cubicOut }}>
        <div class="row">
          <span class="label">재료</span>
          <span>{item.ingredients.join(', ')}</span>
        </div>
        <div class="row">
          <span class="label">알레르기</span>
          {#if allergens.length}
            {#each allergens as name (name)}<span class="tag warn">{name}</span>{/each}
          {:else}
            <span class="tag">표시 대상 없음</span>
          {/if}
        </div>
        <div class="row">
          <span class="label">특징</span>
          <span class="tag">{CAFFEINE[item.caffeine]}</span>
          <span class="tag">
            단맛
            <span class="dots">
              {#each [1, 2, 3] as n (n)}<i class:on={n <= item.sweetness}></i>{/each}
            </span>
          </span>
          {#if item.temperature}<span class="tag">{SERVED[item.temperature]}</span>{/if}
        </div>
      </div>

      {#if groups.length && pending}
        <div class="choices">
          {#each groups as group, i (group!.id)}
            {@const chosen = pending.chosen[group!.id] ?? []}
            {@const missing = pending.missing.includes(group!.id)}
            <div
              class="group"
              class:missing
              in:fly|global={{ y: 20, duration: 450, delay: 500 + i * 120, easing: cubicOut }}
            >
              <span class="group-name">{group!.name}</span>
              <div class="segments">
                {#each group!.choices as choice (choice.id)}
                  <span class="segment" class:chosen={chosen.includes(choice.id)}>
                    {choice.say || choice.name}
                    {#if choice.price}<small>+{won(choice.price)}</small>{/if}
                  </span>
                {/each}
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .item {
    height: 100%;
    display: grid;
    grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
    gap: 4.5rem;
    align-items: center;
    padding: 2rem 6rem 0;
  }
  .hero {
    width: min(100%, 38rem);
    justify-self: end;
    filter: drop-shadow(var(--shadow-l));
  }
  .info {
    display: flex;
    flex-direction: column;
    gap: 1.6rem;
    max-width: 52rem;
  }
  .title {
    display: flex;
    align-items: baseline;
    gap: 1.4rem;
    flex-wrap: wrap;
  }
  h2 {
    font-size: 4.6rem;
    font-weight: 800;
    letter-spacing: -0.035em;
  }
  .price {
    font-size: 2.2rem;
    color: var(--text-2);
  }
  .qty {
    font-size: 2.2rem;
    font-weight: 700;
    color: var(--accent);
  }
  .description {
    word-break: keep-all;
    font-size: 1.8rem;
    line-height: 1.5;
    color: var(--text-2);
  }
  .facts {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    flex-wrap: wrap;
    font-size: 1.4rem;
  }
  .label {
    width: 6.5rem;
    color: var(--muted);
    font-weight: 600;
  }
  .tag {
    padding: 0.35rem 0.9rem;
    border-radius: 999px;
    background: var(--surface);
    box-shadow: var(--shadow-s);
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
  }
  .tag.warn {
    background: #fdf1e2;
    color: #8a5a12;
  }
  .dots {
    display: inline-flex;
    gap: 0.25rem;
  }
  .dots i {
    width: 0.6rem;
    height: 0.6rem;
    border-radius: 50%;
    background: var(--line);
  }
  .dots i.on {
    background: var(--accent-2);
  }
  .choices {
    margin-top: 1rem;
    display: flex;
    flex-direction: column;
    gap: 1.2rem;
  }
  .group {
    display: flex;
    align-items: center;
    gap: 1.4rem;
  }
  .group-name {
    width: 6.5rem;
    font-size: 1.5rem;
    font-weight: 700;
  }
  .segments {
    display: flex;
    gap: 0.8rem;
  }
  .segment {
    min-width: 9rem;
    padding: 1rem 1.6rem;
    border-radius: var(--radius-m);
    background: var(--surface);
    box-shadow: var(--shadow-s);
    font-size: 1.7rem;
    font-weight: 600;
    text-align: center;
    color: var(--text-2);
    transition:
      background 0.35s var(--ease-out),
      color 0.35s,
      transform 0.35s var(--ease-out),
      box-shadow 0.35s;
  }
  .segment small {
    display: block;
    font-size: 1.05rem;
    font-weight: 500;
    opacity: 0.8;
  }
  .segment.chosen {
    background: var(--accent);
    color: white;
    transform: scale(1.04);
    box-shadow: 0 0.6rem 1.4rem rgb(184 105 47 / 0.35);
  }
  .group.missing .segment {
    animation: invite 1.8s ease-in-out infinite;
  }
  @keyframes invite {
    0%,
    100% {
      box-shadow: var(--shadow-s);
    }
    50% {
      box-shadow:
        0 0 0 0.16rem var(--accent-2),
        var(--shadow-s);
    }
  }
</style>
