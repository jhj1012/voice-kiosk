<script lang="ts">
  // The whole display: the screen the assistant chose, and the dock with the assistant,
  // the subtitles and the order summary.
  import { tick } from 'svelte';
  import { fly } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import { ui } from '../store.svelte';
  import { screenIn, screenOut } from '../transitions';
  import AssistantPresence from './AssistantPresence.svelte';
  import Attract from './Attract.svelte';
  import DoneScreen from './DoneScreen.svelte';
  import InfoScreen from './InfoScreen.svelte';
  import ItemScreen from './ItemScreen.svelte';
  import MenuScreen from './MenuScreen.svelte';
  import Notice from './Notice.svelte';
  import OrderSummary from './OrderSummary.svelte';
  import PaymentScreen from './PaymentScreen.svelte';
  import ReviewScreen from './ReviewScreen.svelte';
  import Subtitles from './Subtitles.svelte';
  import Welcome from './Welcome.svelte';

  const STATUS: Record<string, string> = {
    connecting: '연결 중',
    listening: '듣고 있어요',
    thinking: '생각 중',
    speaking: '말하는 중',
    idle: '',
  };

  const view = $derived(ui.state.view);
  // A new key replays the screen transition (e.g. another menu title, another item).
  const screenKey = $derived(
    `${view.screen}|${view.screen === 'menu' ? view.title : ''}|` +
      `${view.screen === 'item' ? view.item_id : ''}|${view.screen === 'info' ? view.topic : ''}`,
  );
  const attract = $derived(view.screen === 'attract');
  const showSummary = $derived(
    ui.state.order.count > 0 && !['review', 'payment', 'done'].includes(view.screen),
  );
  const level = $derived(
    ui.state.assistant === 'speaking'
      ? ui.level.out
      : ui.state.assistant === 'listening'
        ? ui.level.mic
        : 0,
  );

  // An item that went into the order flies from its picture into the summary.
  $effect(() => {
    const added = ui.lastAdded;
    if (added) void flyToSummary(added.itemId);
  });

  async function flyToSummary(itemId: string) {
    const sources = document.querySelectorAll<HTMLElement>(`[data-fly-source="${itemId}"]`);
    const source = sources[sources.length - 1];
    const sourceRect = source?.getBoundingClientRect();
    await tick();
    const target = document.querySelector<HTMLElement>('[data-fly-target]');
    if (!source || !sourceRect || !target || sourceRect.width === 0) return;
    const targetRect = target.getBoundingClientRect();
    const ghost = source.cloneNode(true) as HTMLElement;
    Object.assign(ghost.style, {
      position: 'fixed',
      left: `${sourceRect.left}px`,
      top: `${sourceRect.top}px`,
      width: `${sourceRect.width}px`,
      height: `${sourceRect.height}px`,
      margin: '0',
      zIndex: '30',
      pointerEvents: 'none',
    });
    document.body.appendChild(ghost);
    const dx = targetRect.left + 24 - sourceRect.left;
    const dy = targetRect.top + 16 - sourceRect.top;
    const scale = 56 / sourceRect.width;
    const animation = ghost.animate(
      [
        { transform: 'translate(0, 0) scale(1)', opacity: 1 },
        {
          transform: `translate(${dx * 0.5}px, ${dy * 0.35 - 80}px) scale(${0.6 + scale / 2})`,
          opacity: 1,
          offset: 0.5,
        },
        { transform: `translate(${dx}px, ${dy}px) scale(${scale})`, opacity: 0.2 },
      ],
      { duration: 850, easing: 'cubic-bezier(0.5, 0, 0.3, 1)' },
    );
    animation.onfinish = () => ghost.remove();
    target.animate(
      [{ transform: 'scale(1)' }, { transform: 'scale(1.04)' }, { transform: 'scale(1)' }],
      { duration: 400, delay: 750 },
    );
  }
</script>

<div class="kiosk" class:attract>
  {#if !attract}
    <header class="brand" transition:fly={{ y: -20, duration: 400 }}>{ui.cafe?.name ?? ''}</header>
  {/if}

  <main class="stage">
    {#key screenKey}
      <section class="screen" in:screenIn out:screenOut>
        {#if view.screen === 'attract'}
          <Attract />
        {:else if view.screen === 'welcome'}
          <Welcome />
        {:else if view.screen === 'menu'}
          <MenuScreen />
        {:else if view.screen === 'item'}
          <ItemScreen />
        {:else if view.screen === 'info'}
          <InfoScreen />
        {:else if view.screen === 'review'}
          <ReviewScreen />
        {:else if view.screen === 'payment'}
          <PaymentScreen />
        {:else if view.screen === 'done'}
          <DoneScreen />
        {/if}
      </section>
    {/key}
  </main>

  {#if !attract}
    <footer class="dock" transition:fly={{ y: 60, duration: 500, easing: cubicOut }}>
      <div class="talk">
        <div class="who">
          <AssistantPresence state={ui.state.assistant} {level} size={6} />
          <span class="status">{STATUS[ui.state.assistant]}</span>
        </div>
        <Subtitles />
      </div>
      {#if showSummary}
        <div transition:fly={{ x: 60, duration: 500, easing: cubicOut }}>
          <OrderSummary />
        </div>
      {/if}
    </footer>
  {/if}

  {#if ui.notice}
    <Notice level={ui.notice.level} text={ui.notice.text} />
  {/if}
</div>

<style>
  .kiosk {
    position: relative;
    height: 100%;
    display: grid;
    grid-template-rows: auto 1fr auto;
    background:
      radial-gradient(80rem 40rem at 85% -10%, rgb(242 207 174 / 0.35), transparent), var(--bg);
  }
  .brand {
    padding: 1.8rem 5rem 0;
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--accent);
    letter-spacing: -0.01em;
  }
  .stage {
    position: relative;
    display: grid;
    min-height: 0;
  }
  .attract .stage {
    grid-row: 1 / -1;
  }
  .screen {
    grid-area: 1 / 1;
    position: relative;
    min-height: 0;
  }
  .dock {
    display: flex;
    align-items: flex-end;
    gap: 2.4rem;
    padding: 1.6rem 5rem 2.4rem;
    min-height: 12rem;
  }
  .talk {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: flex-end;
    gap: 1.8rem;
    padding: 1.4rem 2rem;
    border-radius: var(--radius-l);
    background: rgb(255 255 255 / 0.6);
    backdrop-filter: blur(1rem);
    box-shadow: var(--shadow-s);
  }
  .who {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.3rem;
    width: 7rem;
    flex: none;
  }
  .status {
    font-size: 1rem;
    color: var(--muted);
    font-weight: 600;
    height: 1.2rem;
  }
</style>
