<script lang="ts">
  // The developer panel's display settings: subtitles, the choices' background, the colours.
  // A change shows at once; the backend saves it and sends it to every display.
  import type { ClientEvent } from '../events';
  import { BACKDROPS, COLORS } from '../settings';
  import { previewSettings, ui } from '../store.svelte';

  let { send }: { send: (event: ClientEvent) => void } = $props();

  const settings = $derived(ui.settings);

  function save(values: Record<string, unknown>) {
    previewSettings(values);
    send({ type: 'settings', values });
  }

  function color(key: string, value: string, done: boolean) {
    const values = { colors: { ...settings.colors, [key]: value } };
    if (done) save(values);
    else previewSettings(values); // while dragging in the colour picker
  }

  function reset() {
    previewSettings(null);
    send({ type: 'settings', reset: true });
  }
</script>

<section>
  <h3>화면 설정</h3>
  <label class="line">
    <input
      type="checkbox"
      checked={settings.subtitles}
      onchange={(e) => save({ subtitles: e.currentTarget.checked })}
    />
    자막 보기 (손님과 AI가 하는 말)
  </label>
  <label class="line">
    선택지 배경
    <select value={settings.backdrop} onchange={(e) => save({ backdrop: e.currentTarget.value })}>
      {#each BACKDROPS as backdrop (backdrop.id)}
        <option value={backdrop.id}>{backdrop.label}</option>
      {/each}
    </select>
  </label>
  <label class="line">
    배경 진하기
    <input
      type="range"
      min="0"
      max="100"
      value={Math.round(settings.panelOpacity * 100)}
      oninput={(e) => previewSettings({ panelOpacity: Number(e.currentTarget.value) / 100 })}
      onchange={(e) => save({ panelOpacity: Number(e.currentTarget.value) / 100 })}
    />
    <span class="value">{Math.round(settings.panelOpacity * 100)}%</span>
  </label>
  <div class="colors">
    {#each COLORS as c (c.key)}
      <label>
        <input
          type="color"
          value={settings.colors[c.key]}
          oninput={(e) => color(c.key, e.currentTarget.value, false)}
          onchange={(e) => color(c.key, e.currentTarget.value, true)}
        />
        {c.label}
      </label>
    {/each}
  </div>
  <button type="button" onclick={reset}>기본값으로 되돌리기</button>
</section>

<style>
  section {
    display: flex;
    flex-direction: column;
    gap: 0.7rem;
    padding-top: 0.8rem;
    border-top: 1px solid #5a4a40;
  }
  h3 {
    margin: 0;
    font-size: 1.15rem;
  }
  .line {
    display: flex;
    align-items: center;
    gap: 0.6rem;
  }
  select {
    margin-left: auto;
    font: inherit;
  }
  input[type='range'] {
    margin-left: auto;
    width: 12rem;
  }
  .value {
    width: 3.4rem;
    text-align: right;
  }
  .colors {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem 1rem;
  }
  .colors label {
    display: flex;
    align-items: center;
    gap: 0.6rem;
  }
  input[type='color'] {
    width: 2.6rem;
    height: 1.8rem;
    padding: 0;
    border: none;
    background: none;
    cursor: pointer;
  }
  button {
    align-self: flex-start;
    padding: 0.2rem 0.8rem;
    border: 1px solid #5a4a40;
    border-radius: 999px;
    background: transparent;
    color: inherit;
    font: inherit;
    font-size: 1rem;
    cursor: pointer;
  }
</style>
