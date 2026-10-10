<script lang="ts">
  // One item. While the customer is choosing it, only the option the assistant is asking about
  // is listed; what was already chosen stays as small chips. Asked about the item instead, it
  // shows the item's facts (no description: the assistant tells it when asked).
  import { fade, fly } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import { won } from '../format';
  import { allergenNames, CAFFEINE, groupById, itemById, SERVED } from '../menu';
  import { ui } from '../store.svelte';
  import ItemImage from './ItemImage.svelte';

  const item = $derived(itemById(ui.menu, ui.state.view.item_id));
  const pending = $derived(
    ui.state.pending?.item_id === ui.state.view.item_id ? ui.state.pending : null,
  );
  const chips = $derived(
    pending
      ? Object.entries(pending.chosen).flatMap(([groupId, ids]) => {
          const group = groupById(ui.menu, groupId);
          return ids.map((id) => group?.choices.find((c) => c.id === id)?.say ?? id);
        })
      : [],
  );
  // The option being asked: the first missing one, in the item's own order.
  const asking = $derived(
    pending && item
      ? groupById(ui.menu, item.options.find((id) => pending.missing.includes(id)) ?? '')
      : undefined,
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
    <div class="head box">
      <div class="thumb" data-fly-source={item.id}><ItemImage {item} size="s" /></div>
      <div class="what">
        <h2>{item.name}</h2>
        <p class="price">
          {won(item.price)}{#if pending && pending.quantity > 1}<span class="qty">
              × {pending.quantity}</span
            >{/if}
        </p>
        {#if chips.length}
          <div class="chips" in:fade>
            {#each chips as chip (chip)}
              <span class="chip" in:fade={{ duration: 300 }}>{chip}</span>
            {/each}
          </div>
        {/if}
      </div>
    </div>

    {#if asking}
      {#key asking.id}
        <div class="asking" in:fly={{ y: 16, opacity: 0, duration: 400, easing: cubicOut }}>
          <p class="caption">{asking.name}</p>
          <ul class="list">
            {#each asking.choices as choice (choice.id)}
              <li class="row">
                <span class="choice">{choice.say || choice.name}</span>
                {#if choice.price}<span class="extra">+{won(choice.price)}</span>{/if}
              </li>
            {/each}
          </ul>
        </div>
      {/key}
    {:else if !pending}
      <div class="facts box" in:fade={{ duration: 400, delay: 200 }}>
        <p>{item.ingredients.join(', ')}</p>
        <p>{facts.join('  ·  ')}</p>
      </div>
    {/if}
  </div>
{/if}

<style>
  .item {
    display: flex;
    flex-direction: column;
    gap: 2.2rem;
  }
  .head {
    display: flex;
    align-items: center;
    gap: 2.2rem;
    padding: 1.4rem 1.6rem;
  }
  .thumb {
    width: 11rem;
    flex: none;
  }
  .what {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  h2 {
    font-size: 3.4rem;
    font-weight: 800;
    letter-spacing: -0.03em;
  }
  .price {
    font-size: 2rem;
    color: var(--text-2);
  }
  .qty {
    color: var(--accent);
    font-weight: 700;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.6rem;
    margin-top: 0.4rem;
  }
  .chip {
    padding: 0.3rem 1.1rem;
    border-radius: 999px;
    background: var(--accent);
    color: var(--on-accent);
    font-size: 1.5rem;
    font-weight: 700;
  }
  .asking {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .row {
    min-height: 7.5rem;
  }
  .choice {
    flex: 1;
    font-size: 2.6rem;
    font-weight: 700;
  }
  .extra {
    font-size: 1.8rem;
    color: var(--text-2);
  }
  .facts {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    padding: 1.4rem 1.6rem;
    font-size: 1.7rem;
    color: var(--text-2);
    line-height: 1.5;
  }
</style>
