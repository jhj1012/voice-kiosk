<script lang="ts">
  // Developer mode (F2): type what the customer says, mute the audio, see the events.
  // Space lifts / puts down the simulated handset. Customers never see this panel.
  import type { ClientEvent, ServerEvent } from '../events';
  import { ui } from '../store.svelte';

  let {
    send,
    mode,
    connected,
    log,
  }: {
    send: (event: ClientEvent) => void;
    mode: string;
    connected: boolean;
    log: { at: number; event: ServerEvent }[];
  } = $props();

  let text = $state('');
  let audio = $state(true);
  const offHook = $derived(ui.state.phase !== 'idle');

  function submit(event: SubmitEvent) {
    event.preventDefault();
    if (text.trim()) send({ type: 'dev_text', text: text.trim() });
    text = '';
  }

  function summary(event: ServerEvent): string {
    switch (event.type) {
      case 'state':
        return `#${event.seq} ${event.phase} · ${event.view.screen} ${event.view.title || event.view.item_id || event.view.topic} · ${event.assistant} · ${event.order.count}개`;
      case 'subtitle':
        return `${event.speaker}${event.final ? '' : '…'}: ${event.text}`;
      case 'notice':
        return `${event.level}: ${event.text || '(clear)'}`;
      default:
        return event.type;
    }
  }
</script>

<div class="dev">
  <div class="row">
    <strong>개발자 모드</strong>
    <span class="pill" class:ok={connected}
      >{mode === 'demo' ? 'demo' : connected ? 'connected' : 'offline'}</span
    >
    <span class="pill" class:ok={offHook}>{offHook ? '수화기 듦' : '수화기 내려놓음'}</span>
  </div>
  {#if mode === 'live' && !connected}
    <p class="offline">
      백엔드 서버에 연결되지 않았어요. 화면만 보려면 주소 끝에 <code>?demo=order</code> 또는
      <code>?demo=allergy</code>를 붙여 주세요.
    </p>
  {/if}
  <form onsubmit={submit}>
    <!-- svelte-ignore a11y_autofocus -->
    <input bind:value={text} placeholder="손님 말 입력 후 Enter" autofocus />
  </form>
  <div class="row">
    <label>
      <input
        type="checkbox"
        bind:checked={audio}
        onchange={() => send({ type: 'dev_mute', audio })}
      />
      오디오
    </label>
    <span class="hint">Space: 수화기 · F2: 닫기</span>
  </div>
  <ol>
    {#each log.slice(-14) as entry (entry.at)}
      <li>{summary(entry.event)}</li>
    {/each}
  </ol>
</div>

<style>
  .dev {
    position: absolute;
    right: 1.2rem;
    top: 1.2rem;
    z-index: 40;
    width: 34rem;
    padding: 1.2rem;
    border-radius: var(--radius-m);
    background: rgb(30 24 20 / 0.92);
    color: #f3ece5;
    font-size: 1.15rem;
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    cursor: auto;
    user-select: text;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 0.8rem;
  }
  .pill {
    padding: 0.1rem 0.6rem;
    border-radius: 999px;
    background: #5a4a40;
    font-size: 1rem;
  }
  .pill.ok {
    background: var(--ok);
  }
  input:not([type]) {
    width: 100%;
    padding: 0.7rem 0.9rem;
    border-radius: 0.6rem;
    border: none;
    font: inherit;
    font-size: 1.3rem;
  }
  .offline {
    margin: 0;
    padding: 0.6rem 0.8rem;
    border-radius: 0.6rem;
    background: rgb(201 138 28 / 0.25);
    line-height: 1.5;
  }
  code {
    white-space: nowrap;
    font-family: ui-monospace, monospace;
    color: #ffd9a8;
  }
  .hint {
    margin-left: auto;
    color: #b9aca1;
  }
  ol {
    margin: 0;
    padding: 0;
    list-style: none;
    font-family: ui-monospace, monospace;
    font-size: 0.95rem;
    color: #d5c9be;
    max-height: 18rem;
    overflow: hidden;
  }
</style>
