<script lang="ts">
  // The items the assistant chose, under its heading, grouped by category.
  import { flip } from 'svelte/animate';
  import { fly } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import { won } from '../format';
  import { byCategory } from '../menu';
  import { ui } from '../store.svelte';
  import { receive, send } from '../transitions';
  import ItemImage from './ItemImage.svelte';

  const view = $derived(ui.state.view);
  const sections = $derived(ui.menu ? byCategory(ui.menu, view.item_ids) : []);
  const count = $derived(sections.reduce((n, s) => n + s.items.length, 0));
  // Card order across sections, for the stagger delay.
  const order = $derived(new Map(sections.flatMap((s) => s.items).map((item, i) => [item.id, i])));
</script>

<div class="menu">
  <header>
    <h2>{view.title}</h2>
    <span class="count">{count}개</span>
  </header>

  {#if count === 0}
    <p class="empty">해당하는 메뉴가 없어요</p>
  {/if}

  <div class="sections">
    {#each sections as section (section.id)}
      <section animate:flip={{ duration: 450 }}>
        <h3>{section.name}</h3>
        <div class="grid" style:--columns={section.items.length}>
          {#each section.items as item (item.id)}
            {@const highlighted = view.highlight.includes(item.id)}
            <article
              class="card"
              class:highlighted
              animate:flip={{ duration: 450, easing: cubicOut }}
              in:fly|global={{
                y: 24,
                duration: 480,
                delay: 160 + (order.get(item.id) ?? 0) * 45,
                easing: cubicOut,
              }}
            >
              <div
                class="image"
                data-fly-source={item.id}
                in:receive|global={{ key: item.id }}
                out:send|global={{ key: item.id }}
              >
                <ItemImage {item} />
              </div>
              {#if highlighted}<span class="badge">추천</span>{/if}
              <div class="text">
                <span class="name">{item.name}</span>
                <span class="price">{won(item.price)}</span>
              </div>
            </article>
          {/each}
        </div>
      </section>
    {/each}
  </div>
</div>

<style>
  .menu {
    height: 100%;
    display: flex;
    flex-direction: column;
    padding: 3.2rem 5rem 0;
    gap: 1.8rem;
  }
  header {
    display: flex;
    align-items: baseline;
    gap: 1.2rem;
  }
  h2 {
    font-size: 3.4rem;
    font-weight: 800;
    letter-spacing: -0.03em;
  }
  .count {
    font-size: 1.5rem;
    color: var(--muted);
  }
  .empty {
    font-size: 2rem;
    color: var(--muted);
  }
  /* Categories flow side by side and wrap: the whole menu fits on one landscape screen. */
  .sections {
    display: flex;
    flex-wrap: wrap;
    align-content: flex-start;
    column-gap: 3.2rem;
    row-gap: 2rem;
    overflow: hidden;
    padding: 0.6rem; /* room for the highlight ring and shadows */
    margin: -0.6rem;
  }
  h3 {
    font-size: 1.35rem;
    font-weight: 700;
    color: var(--muted);
    letter-spacing: 0.04em;
    margin-bottom: 0.8rem;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(var(--columns), 11rem);
    gap: 1.4rem;
  }
  .card {
    position: relative;
    background: var(--surface);
    border-radius: var(--radius-m);
    padding: 0.8rem 0.8rem 1.1rem;
    box-shadow: var(--shadow-s);
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    transition:
      box-shadow 0.4s,
      transform 0.4s var(--ease-out);
  }
  .card.highlighted {
    box-shadow:
      0 0 0 0.18rem var(--accent-2),
      var(--shadow-m);
    transform: translateY(-0.3rem);
  }
  .badge {
    position: absolute;
    top: 1.3rem;
    left: 1.3rem;
    padding: 0.35rem 0.8rem;
    border-radius: 999px;
    background: var(--accent);
    color: white;
    font-size: 1rem;
    font-weight: 700;
    box-shadow: var(--shadow-s);
  }
  .text {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    padding: 0 0.3rem;
  }
  .name {
    font-size: 1.45rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    word-break: keep-all;
  }
  .price {
    font-size: 1.25rem;
    color: var(--text-2);
  }
</style>
