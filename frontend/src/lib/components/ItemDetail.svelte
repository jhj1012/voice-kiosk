<script lang="ts">
  // One item. The backend says what to list (view.group): one option group's choices (the one
  // being asked, or being changed), 'extras' (the item's extras, all at once), or nothing: then
  // an order line's options at a glance, or the item's facts. Earlier choices stay as chips.
  import { fade, fly } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import { won } from '../format';
  import type { Choice, OptionGroup } from '../events';
  import { allergenNames, CAFFEINE, groupById, itemById, SERVED } from '../menu';
  import { ui } from '../store.svelte';
  import ItemImage from './ItemImage.svelte';

  const view = $derived(ui.state.view);
  const item = $derived(itemById(ui.menu, view.item_id));
  const line = $derived(view.line ? ui.state.order.lines[view.line - 1] : undefined);
  const pending = $derived(
    !line && ui.state.pending?.item_id === view.item_id ? ui.state.pending : null,
  );
  const chosen = $derived<Record<string, string[]>>(line?.chosen ?? pending?.chosen ?? {});
  const groups = $derived(
    (item?.options ?? []).map((id) => groupById(ui.menu, id)).filter((g): g is OptionGroup => !!g),
  );
  const isNone = (choice: Choice) => choice.id === 'none';
  const picked = (group: OptionGroup) =>
    group.choices.filter((c) => (chosen[group.id] ?? []).includes(c.id) && !isNone(c));
  const chips = $derived(groups.flatMap((g) => picked(g).map((c) => c.say || c.name)));
  const asking = $derived(groupById(ui.menu, view.group));
  const extras = $derived(groups.filter((g) => !g.required));
  const quantity = $derived(line?.quantity ?? pending?.quantity ?? 1);
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
  const slide = { y: 16, opacity: 0, duration: 400, easing: cubicOut };
</script>

{#if item}
  <div class="item">
    <div class="head box">
      <div class="thumb" data-fly-source={item.id}><ItemImage {item} size="s" /></div>
      <div class="what">
        <h2>{item.name}</h2>
        <p class="price">
          {won(line?.unit_price ?? item.price)}{#if quantity > 1}<span class="qty">
              × {quantity}</span
            >{/if}
        </p>
        {#if chips.length}
          <div class="chips">
            {#each chips as chip (chip)}
              <span class="chip" in:fade={{ duration: 300 }}>{chip}</span>
            {/each}
          </div>
        {/if}
      </div>
    </div>

    {#if asking}
      {#key asking.id}
        <div class="block" in:fly={slide}>
          <p class="caption">{asking.name}</p>
          <ul class="list">
            {#each asking.choices as choice (choice.id)}
              <li class="row" class:chosen={(chosen[asking.id] ?? []).includes(choice.id)}>
                <span class="choice">{choice.say || choice.name}</span>
                {#if choice.price}<span class="extra">+{won(choice.price)}</span>{/if}
              </li>
            {/each}
          </ul>
        </div>
      {/key}
    {:else if view.group === 'extras'}
      <div class="block" in:fly={slide}>
        <p class="caption">추가할 수 있어요</p>
        <ul class="list">
          {#each extras as group (group.id)}
            <li class="row extras">
              <span class="group">{group.name}</span>
              <span class="pills">
                {#each group.choices.filter((c) => !isNone(c)) as choice (choice.id)}
                  <span class="pill" class:on={(chosen[group.id] ?? []).includes(choice.id)}>
                    {choice.say || choice.name}{#if choice.price}<small>+{won(choice.price)}</small
                      >{/if}
                  </span>
                {/each}
              </span>
            </li>
          {/each}
        </ul>
      </div>
    {:else if line}
      <ul class="list" in:fly={slide}>
        {#each groups as group (group.id)}
          {@const values = picked(group)}
          <li class="row overview">
            <span class="group">{group.name}</span>
            <span class="value" class:none={!values.length}>
              {values.map((c) => c.say || c.name).join(', ') || '없음'}
            </span>
          </li>
        {/each}
      </ul>
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
  .block {
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
    color: inherit;
    opacity: 0.75;
  }
  .row.extras,
  .row.overview {
    min-height: 6.4rem;
  }
  .group {
    width: 9rem;
    flex: none;
    font-size: 1.8rem;
    font-weight: 700;
    color: var(--text-2);
  }
  .pills {
    display: flex;
    flex-wrap: wrap;
    gap: 0.6rem;
  }
  .pill {
    padding: 0.5rem 1.2rem;
    border-radius: 999px;
    background: var(--tint);
    font-size: 1.7rem;
    font-weight: 600;
    transition:
      background 0.35s var(--ease-out),
      color 0.35s;
  }
  .pill small {
    margin-left: 0.4rem;
    font-size: 1.3rem;
    opacity: 0.75;
  }
  .pill.on {
    background: var(--accent);
    color: var(--on-accent);
  }
  .value {
    font-size: 2.2rem;
    font-weight: 700;
  }
  .value.none {
    color: var(--muted);
    font-weight: 500;
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
