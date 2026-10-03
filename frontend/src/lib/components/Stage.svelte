<script lang="ts">
  // One continuous page. The assistant and the conversation stay at the top, the order at the
  // bottom; in between, what the assistant chose appears and disappears in place.
  import { tick } from 'svelte';
  import { fade } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import { ui } from '../store.svelte';
  import { appear, disappear } from '../transitions';
  import AssistantPresence from './AssistantPresence.svelte';
  import Categories from './Categories.svelte';
  import Done from './Done.svelte';
  import Hint from './Hint.svelte';
  import Info from './Info.svelte';
  import ItemDetail from './ItemDetail.svelte';
  import MenuGrid from './MenuGrid.svelte';
  import Notice from './Notice.svelte';
  import OrderBar from './OrderBar.svelte';
  import Payment from './Payment.svelte';
  import Review from './Review.svelte';
  import Subtitles from './Subtitles.svelte';

  const STATUS: Record<string, string> = {
    connecting: '연결 중',
    listening: '듣고 있어요',
    thinking: '생각 중',
    speaking: '',
    idle: '',
  };

  const view = $derived(ui.state.view);
  const idle = $derived(view.screen === 'attract');
  // Menus with other titles or items stay one block: the cards themselves come and go.
  const block = $derived(
    view.screen === 'item'
      ? `item|${view.item_id}`
      : view.screen === 'info'
        ? `info|${view.topic}`
        : view.screen,
  );
  const showOrder = $derived(
    ui.state.order.count > 0 && !['review', 'payment', 'done'].includes(view.screen),
  );
  const level = $derived(
    ui.state.assistant === 'speaking'
      ? ui.level.out
      : ui.state.assistant === 'listening'
        ? ui.level.mic
        : 0,
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

<div class="page" class:idle>
  <div class="glow"></div>

  <section class="talk">
    <div class="presence">
      <AssistantPresence state={idle ? 'idle' : ui.state.assistant} {level} size={idle ? 17 : 8} />
      {#if !idle}
        <span class="status" transition:fade={{ duration: 200 }}>{STATUS[ui.state.assistant]}</span>
      {/if}
    </div>
    {#if idle}
      <p class="prompt" in:fade={{ duration: 600, delay: 400 }} out:fade={{ duration: 200 }}>
        수화기를 들고 말씀해 주세요
      </p>
    {:else}
      <div class="subtitles" in:fade={{ duration: 400, delay: 500, easing: cubicOut }}>
        <Subtitles />
      </div>
    {/if}
  </section>

  <main class="content">
    {#key block}
      <div class="block" in:appear out:disappear>
        {#if view.screen === 'welcome'}
          <Hint />
        {:else if view.screen === 'menu'}
          <MenuGrid />
        {:else if view.screen === 'categories'}
          <Categories />
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
    {/key}
  </main>

  {#if showOrder}
    <div class="order" transition:fade={{ duration: 350 }}>
      <OrderBar />
    </div>
  {/if}

  {#if ui.notice}
    <Notice level={ui.notice.level} text={ui.notice.text} />
  {/if}
</div>

<style>
  .page {
    position: absolute;
    inset: 0;
    overflow: hidden;
    background: var(--bg);
  }
  /* Soft blue light at the top and bottom of a white page */
  .glow {
    position: absolute;
    inset: 0;
    background:
      radial-gradient(60rem 34rem at 50% -6rem, #dcebff, transparent 70%),
      radial-gradient(70rem 30rem at 50% 128rem, #e3efff, transparent 70%);
    transition: opacity 1.2s;
  }
  .idle .glow {
    background:
      radial-gradient(56rem 56rem at 50% 44rem, #e2eeff, transparent 70%),
      radial-gradient(70rem 30rem at 50% 130rem, #edf4ff, transparent 70%);
  }

  .talk {
    position: absolute;
    left: 0;
    right: 0;
    top: 5rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2rem;
    padding: 0 5rem;
    transition: top 0.9s var(--ease-out);
  }
  .idle .talk {
    top: 40rem;
    gap: 4rem;
  }
  .presence {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.6rem;
  }
  .status {
    height: 1.6rem;
    font-size: 1.3rem;
    color: var(--muted);
  }
  .prompt {
    font-size: 3.2rem;
    font-weight: 600;
    letter-spacing: -0.03em;
    color: var(--text);
  }
  /* The latest words stay visible; older lines fade out at the top. */
  .subtitles {
    width: 100%;
    height: 13rem;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    overflow: hidden;
    mask-image: linear-gradient(transparent, black 3rem);
  }

  .content {
    position: absolute;
    top: 30rem;
    bottom: 15rem;
    left: 4.5rem;
    right: 4.5rem;
    display: grid;
  }
  .block {
    grid-area: 1 / 1;
    min-height: 0;
  }

  .order {
    position: absolute;
    left: 4.5rem;
    right: 4.5rem;
    bottom: 4rem;
  }
</style>
