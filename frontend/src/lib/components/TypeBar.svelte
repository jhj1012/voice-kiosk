<script lang="ts">
  // The laptop's screen only (not the phone's): type what the customer says without opening
  // the developer panel. Enter sends it (and starts a conversation if none is going on); F8 and
  // F9 answer "아니요" / "네" (the backend's key hook, Windows).
  import type { ClientEvent } from '../events';

  let { send }: { send: (event: ClientEvent) => void } = $props();

  let text = $state('');

  function submit(event: SubmitEvent) {
    event.preventDefault();
    if (text.trim()) send({ type: 'dev_text', text: text.trim() });
    text = '';
  }
</script>

<div class="typebar">
  <p class="keys"><kbd>F8</kbd> 아니요 · <kbd>F9</kbd> 네</p>
  <form onsubmit={submit}>
    <input bind:value={text} placeholder="손님 말을 입력하고 Enter" aria-label="손님 말 입력" />
  </form>
</div>

<style>
  .typebar {
    position: absolute;
    left: 4.5rem;
    right: 4.5rem;
    bottom: 1.6rem;
    z-index: 30;
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
    cursor: auto;
  }
  .keys {
    align-self: center;
    margin: 0;
    padding: 0.4rem 1.4rem;
    border-radius: 999px;
    background: var(--panel-soft);
    font-size: 1.6rem;
    color: var(--text-2);
  }
  kbd {
    display: inline-block;
    padding: 0.1rem 0.6rem;
    border: 1px solid var(--text-2);
    border-radius: 0.5rem;
    background: var(--image-bg);
    font: inherit;
    font-weight: 700;
  }
  input {
    width: 100%;
    box-sizing: border-box;
    padding: 1rem 1.4rem;
    border: 1px solid var(--line);
    border-radius: var(--radius-m);
    background: var(--image-bg);
    color: var(--text);
    font: inherit;
    font-size: 1.8rem;
  }
  input:focus {
    outline: 2px solid var(--accent);
    outline-offset: 1px;
  }
</style>
