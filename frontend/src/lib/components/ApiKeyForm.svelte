<script lang="ts">
  // Asks for the Gemini API key, for teammates who never use a terminal: when no key is set,
  // when Google refused the saved one, or from the developer panel ("API 키 바꾸기").
  import { fade } from 'svelte/transition';
  import { KEY_MESSAGES, saveApiKey, type KeyResult } from '../apiKey';
  import { openKeyForm, ui } from '../store.svelte';

  const AI_STUDIO = 'https://aistudio.google.com/apikey';

  let key = $state('');
  let visible = $state(false);
  let busy = $state(false);
  let result = $state<KeyResult | null>(null);
  const closable = $derived(ui.apiKey === 'ok' && result !== 'ok');

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (busy || !key.trim()) return;
    busy = true;
    openKeyForm(true); // stays open to show the result after the key starts working
    result = await saveApiKey(key.trim());
    busy = false;
    if (result === 'ok') {
      key = '';
      setTimeout(() => openKeyForm(false), 1800);
    }
  }
</script>

<div class="overlay" transition:fade={{ duration: 250 }}>
  <form class="card" onsubmit={submit}>
    <h1>Gemini API 키를 넣어 주세요</h1>
    {#if ui.apiKey === 'rejected'}
      <p class="lead warn">저장된 키를 Google이 받아 주지 않았어요. 새 키를 넣어 주세요.</p>
    {:else}
      <p class="lead">처음 한 번만 하면 돼요. 키는 이 컴퓨터에만 저장돼요.</p>
    {/if}

    <ol>
      <li>
        <a href={AI_STUDIO} target="_blank" rel="noreferrer">Google AI Studio 열기</a>
        를 눌러 Google 계정으로 로그인해요.
      </li>
      <li><b>Create API key</b>(API 키 만들기)를 누르고, 만들어진 키를 <b>복사</b>해요.</li>
      <li>아래 칸에 붙여 넣고(<kbd>Ctrl</kbd>+<kbd>V</kbd>) <b>저장</b>을 눌러요.</li>
    </ol>

    <div class="field">
      <!-- svelte-ignore a11y_autofocus -->
      <input
        type={visible ? 'text' : 'password'}
        bind:value={key}
        placeholder="복사한 키를 여기에 붙여 넣기"
        autocomplete="off"
        spellcheck="false"
        aria-label="Gemini API 키"
        autofocus
      />
      <button type="button" class="ghost" onclick={() => (visible = !visible)}>
        {visible ? '숨기기' : '보기'}
      </button>
    </div>

    <div class="actions">
      {#if closable}
        <button type="button" class="ghost" onclick={() => openKeyForm(false)}>닫기</button>
      {/if}
      <button type="submit" class="primary" disabled={busy || !key.trim()}>
        {busy ? '확인하는 중…' : '저장'}
      </button>
    </div>

    {#if result && !busy}
      <p class="result" class:ok={result === 'ok'} role="status" in:fade={{ duration: 200 }}>
        {KEY_MESSAGES[result]}
      </p>
    {/if}

    <p class="note">
      무료 키로 쓰면 대화 내용이 Google의 서비스 개선에 쓰일 수 있어요. 키는 다른 사람과 공유하지
      마세요.
    </p>
  </form>
</div>

<style>
  .overlay {
    position: absolute;
    inset: 0;
    z-index: 50;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 5rem;
    background: rgb(240 246 255 / 0.96);
    cursor: auto;
    user-select: text;
  }
  .card {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 2.2rem;
    padding: 4.5rem 4rem;
    border-radius: var(--radius-l);
    background: white;
    border: 1px solid var(--line);
  }
  h1 {
    font-size: 3rem;
    font-weight: 700;
    letter-spacing: -0.03em;
  }
  .lead {
    font-size: 1.7rem;
    color: var(--text-2);
  }
  .warn {
    color: var(--error);
  }
  ol {
    margin: 0;
    padding-left: 2.4rem;
    display: flex;
    flex-direction: column;
    gap: 1.2rem;
    font-size: 1.7rem;
    line-height: 1.5;
  }
  a {
    color: var(--accent);
    font-weight: 700;
  }
  kbd {
    padding: 0 0.5rem;
    border: 1px solid var(--line);
    border-radius: 0.4rem;
    font: inherit;
    font-size: 0.9em;
  }
  .field {
    display: flex;
    gap: 1rem;
  }
  input {
    flex: 1;
    min-width: 0;
    padding: 1.4rem 1.6rem;
    border: 2px solid var(--line);
    border-radius: var(--radius-m);
    font: inherit;
    font-size: 1.8rem;
    outline: none;
  }
  input:not(:placeholder-shown) {
    font-family: ui-monospace, monospace;
  }
  input:focus {
    border-color: var(--accent);
  }
  button {
    padding: 1.3rem 2.4rem;
    border-radius: var(--radius-m);
    border: none;
    font: inherit;
    font-size: 1.7rem;
    font-weight: 700;
    cursor: pointer;
  }
  .primary {
    background: var(--accent);
    color: white;
  }
  .primary:disabled {
    background: var(--accent-2);
    cursor: default;
  }
  .ghost {
    background: var(--tint);
    color: var(--text-2);
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 1rem;
  }
  .result {
    padding: 1.2rem 1.6rem;
    border-radius: var(--radius-m);
    background: #fdecea;
    color: var(--error);
    font-size: 1.6rem;
    line-height: 1.5;
  }
  .result.ok {
    background: var(--accent-soft);
    color: var(--accent);
  }
  .note {
    font-size: 1.3rem;
    line-height: 1.5;
    color: var(--muted);
  }
</style>
