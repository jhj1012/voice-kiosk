<script lang="ts">
  // The text size editor (F4): click any text on the screen, then make that place's text smaller
  // or larger. Every place has its own size (the menu list's names and the order review's names
  // are two places), on top of the developer panel's size for all of it. This screen shows the
  // phone's sizes while the editor is open; the backend saves them and sends them to the phone.
  import type { ClientEvent } from '../events';
  import { MAX_TEXT_SIZE, MIN_TEXT_SIZE } from '../settings';
  import { previewSettings, ui } from '../store.svelte';
  import { TEXT_ROLES, textRoleAt } from '../textRoles';

  let { send }: { send: (event: ClientEvent) => void } = $props();

  const STEP = 5;

  let bar = $state<HTMLElement | null>(null);
  let role = $state<string | null>(null);
  let picked: HTMLElement | null = null; // outlined while chosen

  const roles = $derived(ui.settings.phoneTextRoles);
  const size = $derived(role ? (roles[role] ?? 100) : 100);
  const changed = $derived(Object.keys(roles).length);

  function save(next: Record<string, number>) {
    const values = { phoneTextRoles: next };
    previewSettings(values);
    send({ type: 'settings', values });
  }

  function setSize(value: number) {
    if (!role) return;
    const next = { ...roles };
    const clamped = Math.min(MAX_TEXT_SIZE, Math.max(MIN_TEXT_SIZE, value));
    if (clamped === 100) delete next[role];
    else next[role] = clamped;
    save(next);
  }

  function pick(element: HTMLElement | null) {
    picked?.style.removeProperty('outline');
    picked = element;
    picked?.style.setProperty('outline', '0.3rem dashed var(--accent)');
  }

  // Clicks anywhere but the bar choose text; they do nothing else while the editor is open.
  $effect(() => {
    const onClick = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof HTMLElement) || bar?.contains(target)) return;
      if (target.closest('.dev')) return; // the developer panel still works
      event.preventDefault();
      event.stopPropagation();
      role = textRoleAt(target);
      pick(role ? target : null);
    };
    window.addEventListener('click', onClick, true);
    window.addEventListener('pointerup', stop, true);
    return () => {
      window.removeEventListener('click', onClick, true);
      window.removeEventListener('pointerup', stop, true);
      pick(null);
    };
  });

  function stop(event: Event) {
    // the phone mode's "tap to start" listens for pointerup
    if (event.target instanceof Node && !bar?.contains(event.target)) event.stopPropagation();
  }
</script>

<div class="editor" bind:this={bar}>
  <div class="row">
    <b>글자 크기 편집</b>
    <span class="hint">바꿀 글자를 누르세요 · F4: 닫기</span>
  </div>
  {#if role}
    <div class="row">
      <span class="role">{TEXT_ROLES[role]}</span>
      <button type="button" onclick={() => setSize(size - STEP)} aria-label="작게">−</button>
      <b class="value">{size}%</b>
      <button type="button" onclick={() => setSize(size + STEP)} aria-label="크게">+</button>
      <button type="button" onclick={() => setSize(100)} disabled={size === 100}>원래대로</button>
    </div>
  {:else}
    <div class="row hint">글자가 아닌 곳이에요. 글자를 눌러 주세요.</div>
  {/if}
  {#if changed}
    <div class="row hint">
      바꾼 곳 {changed}개
      <button type="button" onclick={() => save({})}>모두 되돌리기</button>
    </div>
  {/if}
</div>

<style>
  .editor {
    position: absolute;
    left: 50%;
    top: 1.2rem;
    translate: -50% 0;
    z-index: 45;
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    padding: 1rem 1.4rem;
    border-radius: var(--radius-m);
    background: rgb(30 24 20 / 0.92);
    color: #f3ece5;
    font-size: 1.3rem;
    cursor: auto;
    white-space: nowrap;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 0.8rem;
  }
  .hint {
    color: #b9aca1;
  }
  .role {
    min-width: 18rem;
  }
  .value {
    min-width: 4.5em;
    text-align: center;
    font-variant-numeric: tabular-nums;
  }
  button {
    min-width: 3rem;
    padding: 0.3rem 0.9rem;
    border: 1px solid #5a4a40;
    border-radius: 999px;
    background: transparent;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }
  button:disabled {
    opacity: 0.4;
    cursor: default;
  }
</style>
