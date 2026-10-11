<script lang="ts">
  // One continuous page. The avatar stands behind everything; what the assistant is asking
  // about appears over his chest, on a see-through background (blur, a gradient from the bottom,
  // or boxes: the developer panel's choice). The order stays at the bottom.
  import { tick } from 'svelte';
  import { fade } from 'svelte/transition';
  import { ui } from '../store.svelte';
  import { cssVariables } from '../settings';
  import { appear, disappear } from '../transitions';
  import ApiKeyForm from './ApiKeyForm.svelte';
  import Avatar from './Avatar.svelte';
  import CategoryList from './CategoryList.svelte';
  import DiningChoice from './DiningChoice.svelte';
  import Done from './Done.svelte';
  import Info from './Info.svelte';
  import ItemDetail from './ItemDetail.svelte';
  import MenuList from './MenuList.svelte';
  import Notice from './Notice.svelte';
  import OrderBar from './OrderBar.svelte';
  import Payment from './Payment.svelte';
  import Review from './Review.svelte';
  import Subtitles from './Subtitles.svelte';

  const CONTENT = ['dining', 'menu', 'categories', 'item', 'info', 'review', 'payment', 'done'];

  const settings = $derived(ui.settings);
  const style = $derived(
    Object.entries(cssVariables(settings))
      .map(([name, value]) => `${name}: ${value}`)
      .join('; '),
  );
  const view = $derived(ui.state.view);
  const idle = $derived(view.screen === 'attract');
  const hasContent = $derived(CONTENT.includes(view.screen));
  // Menus with other titles or items stay one block: the rows themselves come and go.
  const block = $derived(
    view.screen === 'item'
      ? `item|${view.item_id}|${view.line}`
      : view.screen === 'info'
        ? `info|${view.topic}`
        : view.screen,
  );
  const showOrder = $derived(
    ui.state.order.count > 0 && !['review', 'payment', 'done'].includes(view.screen),
  );

  // An item that went into the order flies from its picture into the order bar.
  $effect(() => {
    const added = ui.lastAdded;
    if (added) void flyToOrder(added.itemId);
  });

  async function flyToOrder(itemId: string) {
    const sources = document.querySelectorAll<HTMLElement>(`[data-fly-source="${itemId}"]`);
    const source = sources[sources.length - 1];
    const from = source?.getBoundingClientRect();
    await tick();
    const target = document.querySelector<HTMLElement>('[data-fly-target]');
    if (!source || !from || !target || from.width === 0) return;
    const to = target.getBoundingClientRect();
    const ghost = source.cloneNode(true) as HTMLElement;
    Object.assign(ghost.style, {
      position: 'fixed',
      left: `${from.left}px`,
      top: `${from.top}px`,
      width: `${from.width}px`,
      height: `${from.height}px`,
      margin: '0',
      zIndex: '30',
      pointerEvents: 'none',
    });
    document.body.appendChild(ghost);
    const dx = to.left + to.height * 0.2 - from.left;
    const dy = to.top + to.height * 0.2 - from.top;
    const scale = (to.height * 0.6) / from.width;
    const flight = ghost.animate(
      [
        { transform: 'translate(0, 0) scale(1)', opacity: 1 },
        { transform: `translate(${dx}px, ${dy}px) scale(${scale})`, opacity: 0.3 },
      ],
      { duration: 800, easing: 'cubic-bezier(0.5, 0, 0.25, 1)' },
    );
    flight.onfinish = () => ghost.remove();
    target.animate([{ scale: '1' }, { scale: '1.03' }, { scale: '1' }], {
      duration: 400,
      delay: 700,
    });
  }
</script>

<div class="page backdrop-{settings.backdrop}" {style}>
  <div class="glow"></div>
  <Avatar />

  {#if settings.backdrop === 'gradient' && (hasContent || showOrder || idle)}
    <div class="fade" transition:fade={{ duration: 400 }}></div>
  {/if}

  {#if settings.subtitles && !idle}
    <section class="subtitles" transition:fade={{ duration: 300 }}>
      <Subtitles />
    </section>
  {/if}

  <main class="content">
    {#key block}
      <div class="block" in:appear out:disappear>
        {#if hasContent}
          <div class="surface">
            {#if view.screen === 'dining'}
              <DiningChoice />
            {:else if view.screen === 'menu'}
              <MenuList />
            {:else if view.screen === 'categories'}
              <CategoryList />
            {:else if view.screen === 'item'}
              <ItemDetail />
            {:else if view.screen === 'info'}
              <Info />
            {:else if view.screen === 'review'}
              <Review />
            {:else if view.screen === 'payment'}
              <Payment />
            {:else if view.screen === 'done'}
              <Done />
            {/if}
          </div>
        {/if}
      </div>
    {/key}
  </main>

  {#if idle}
    <p class="prompt box" in:fade={{ duration: 600, delay: 400 }} out:fade={{ duration: 200 }}>
      수화기를 들고 말씀해 주세요
    </p>
  {/if}

  {#if showOrder}
    <div class="order" transition:fade={{ duration: 350 }}>
      <OrderBar />
    </div>
  {/if}

  {#if ui.notice}
    <Notice level={ui.notice.level} text={ui.notice.text} />
  {/if}

  {#if ui.keyForm}
    <ApiKeyForm />
  {/if}
</div>

<style>
  .page {
    position: absolute;
    inset: 0;
    overflow: hidden;
    background: var(--bg);
    color: var(--text);
  }
  .glow {
    position: absolute;
    inset: 0;
    background: radial-gradient(70rem 50rem at 50% 0, var(--glow), transparent 70%);
  }

  /* "Gradient": the panel colour rises from the bottom of the screen over the avatar. */
  .fade {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    top: 44rem;
    background: linear-gradient(to top, var(--panel-soft) 70%, transparent);
    pointer-events: none;
  }

  .subtitles {
    position: absolute;
    top: 3rem;
    left: 5rem;
    right: 5rem;
    z-index: 5;
    padding: 1.4rem 2rem;
    border-radius: var(--radius-l);
    background: var(--panel-soft);
  }

  /* Over the avatar's chest: his face stays visible above. */
  .content {
    position: absolute;
    top: 54rem;
    bottom: 15rem;
    left: 4.5rem;
    right: 4.5rem;
    display: grid;
  }
  .block {
    grid-area: 1 / 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
  }
  .surface {
    position: relative;
    isolation: isolate; /* keeps the blurred patch behind the choices, above the avatar */
    max-height: 100%;
  }
  /* "Blur": a soft, blurred patch behind the choices, fading out at its edges. */
  .backdrop-blur .surface::before {
    content: '';
    position: absolute;
    inset: -3.5rem;
    z-index: -1;
    background: var(--panel-soft);
    backdrop-filter: blur(2.4rem) saturate(1.2);
    mask:
      linear-gradient(to bottom, transparent, #000 3.5rem, #000 calc(100% - 3.5rem), transparent),
      linear-gradient(to right, transparent, #000 3.5rem, #000 calc(100% - 3.5rem), transparent);
    mask-composite: intersect;
  }

  .prompt {
    position: absolute;
    left: 50%;
    bottom: 12rem;
    translate: -50% 0;
    white-space: nowrap;
    font-size: 3.2rem;
    font-weight: 700;
    letter-spacing: -0.03em;
    padding: 1.8rem 3.6rem;
    border-radius: 999px;
    background: var(--panel-soft);
  }
  .backdrop-blur .prompt {
    backdrop-filter: blur(2rem);
  }

  .order {
    position: absolute;
    left: 4.5rem;
    right: 4.5rem;
    bottom: 4rem;
  }
</style>
