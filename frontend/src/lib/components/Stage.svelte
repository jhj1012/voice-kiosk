<script lang="ts">
  // One continuous page. The avatar stands behind everything; what the assistant is asking
  // about appears over his chest, on a see-through background (blur, a gradient from the bottom,
  // or boxes: the developer panel's choice). The order stays at the bottom.
  // On the phone of the phone mode its case covers the screen's edges (`--safe-*`, set in the
  // developer panel): the avatar stands a little lower, everything else keeps out of them, and the order
  // moves above the avatar's head (the bottom is covered). The handset's button ends the call.
  import { tick } from 'svelte';
  import { fade } from 'svelte/transition';
  import { ui } from '../store.svelte';
  import { cssVariables, insetVariables, textSizeVariables } from '../settings';
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
    Object.entries({
      ...cssVariables(settings),
      ...(ui.phone ? insetVariables(settings.phoneInsets) : {}),
      ...(ui.phone || ui.textEdit ? textSizeVariables(settings) : {}),
    })
      .map(([name, value]) => `${name}: ${value}`)
      .join('; '),
  );
  const view = $derived(ui.state.view);
  const idle = $derived(view.screen === 'attract');
  const hasContent = $derived(CONTENT.includes(view.screen));
  // Menus with other titles or items stay one block: the rows themselves come and go.
  const block = $derived(
    view.screen === 'item'
      ? `item|${view.item_id}|${view.line}|${view.draft}`
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

  /** Shrinks the choices when they are taller than their place (a long menu, larger text, the
   * phone's covered bottom), so nothing reaches under the order or off the screen. They are
   * laid out wider by as much as they shrink, so the box keeps the width of every other screen:
   * the largest scale whose layout at full width / scale still fits (a few layouts, searched). */
  function fit(surface: HTMLElement) {
    const place = surface.closest<HTMLElement>('.content');
    if (!place) return;
    const layout = (scale: number, full: number) => {
      surface.style.width = scale < 1 ? `${full / scale}px` : '';
      surface.style.marginLeft = scale < 1 ? `${(full - full / scale) / 2}px` : '';
      // the box's layout height (the scale does not change it; the blurred patch reaching out
      // of it does not count)
      return surface.offsetHeight * scale;
    };
    const update = () => {
      const space = place.clientHeight;
      const full = surface.parentElement?.clientWidth ?? 0;
      let best = 1;
      if (space > 0 && full > 0 && layout(1, full) > space) {
        let low = space / layout(1, full); // fits: wider only makes it shorter
        let high = 1;
        for (let i = 0; i < 6; i++) {
          const mid = (low + high) / 2;
          if (layout(mid, full) <= space) low = mid;
          else high = mid;
        }
        best = low;
      }
      // its own resizing calls this again: a slightly smaller scale (it still fits) stays
      const now = Number(surface.style.scale || 1);
      if (now <= best && best - now < 0.01) best = now;
      layout(best, full);
      surface.style.scale = best < 1 ? String(best) : '';
    };
    const observer = new ResizeObserver(update);
    observer.observe(surface);
    observer.observe(place);
    return { destroy: () => observer.disconnect() };
  }

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

<div class="page backdrop-{settings.backdrop}" class:phone={ui.phone} {style}>
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
          <div class="surface" use:fit>
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

  {#if view.screen === 'welcome'}
    <!-- After here / to go: customers pick from the printed menu board. -->
    <p
      class="prompt box small"
      in:fade={{ duration: 500, delay: 300 }}
      out:fade={{ duration: 200 }}
    >
      메뉴판에서 메뉴를 고른 뒤 말씀해 주세요
    </p>
  {/if}

  {#if idle}
    <p class="prompt box" in:fade={{ duration: 600, delay: 400 }} out:fade={{ duration: 200 }}>
      {ui.phone ? '수화기를 들고 화면을 눌러 주세요' : '수화기를 들고 말씀해 주세요'}
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

  {#if ui.keyForm && ui.phone}
    <!-- The key is entered on the laptop only (POST /api/key is refused from the phone). -->
    <p class="prompt box">
      API 키가 필요해요. 노트북에서 http://localhost:8765 를 열고 넣어 주세요.
    </p>
  {:else if ui.keyForm}
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
    grid-template-columns: minmax(0, 1fr); /* its width: `fit` lays the choices out wider */
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
    transform-origin: top center; /* `fit` shrinks it from the top */
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
    /* One line when it fits; larger text (as on the team's phone) wraps inside the box. */
    width: max-content;
    max-width: calc(100% - 4rem);
    text-align: center;
    word-break: keep-all;
    --text-role: stage-prompt;
    font-size: calc(3.2rem * var(--size-all) * var(--fs-stage-prompt, 1));
    font-weight: 700;
    letter-spacing: -0.03em;
    padding: 1.8rem 3.6rem;
    border-radius: 999px;
    background: var(--panel-soft);
  }
  .prompt.small {
    --text-role: stage-prompt-small;
    font-size: calc(2.6rem * var(--size-all) * var(--fs-stage-prompt-small, 1));
    bottom: 40%;
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

  /* The phone mode: out of the covered edges; the order above the avatar's head. */
  .phone .subtitles {
    top: calc(var(--safe-top) + 13rem);
    left: calc(5rem + var(--safe-left));
    right: calc(5rem + var(--safe-right));
  }
  .phone .content {
    top: 48rem; /* a little higher: the covered bottom leaves less room (the face stays clear) */
    bottom: calc(var(--safe-bottom) + 3rem);
    left: calc(4.5rem + var(--safe-left));
    right: calc(4.5rem + var(--safe-right));
  }
  .phone .prompt {
    bottom: calc(var(--safe-bottom) + 6rem);
    max-width: calc(100% - 4rem - var(--safe-left) - var(--safe-right));
  }
  .phone .prompt.small {
    bottom: max(40%, calc(var(--safe-bottom) + 6rem));
  }
  .phone .order {
    top: calc(var(--safe-top) + 2.4rem);
    bottom: auto;
    left: calc(3rem + var(--safe-left));
    right: calc(3rem + var(--safe-right));
  }
</style>
