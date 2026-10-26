<script lang="ts">
  // The developer panel's settings: the conversation (ignore speech not meant for the kiosk),
  // subtitles, the choices' background, the colours, the phone's covered edges. A change shows at
  // once; the backend saves it and sends it to every display.
  import type { ClientEvent } from '../events';
  import { BACKDROPS, COLORS, INSET_SIDES, MAX_INSET, type PhoneInsets } from '../settings';
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

  function inset(side: keyof PhoneInsets, value: number) {
    if (Number.isFinite(value) && value >= 0 && value <= MAX_INSET) {
      save({ phoneInsets: { ...settings.phoneInsets, [side]: value } });
    }
  }

  function reset() {
    previewSettings(null);
    send({ type: 'settings', reset: true });
  }
</script>

<section>
  <h3>대화 설정</h3>
  <label class="line">
    <input
      type="checkbox"
      checked={settings.ignoreUnrelated}
      onchange={(e) => save({ ignoreUnrelated: e.currentTarget.checked })}
    />
    키오스크에 하는 말이 아니면 대답하지 않기
  </label>
  <p class="note">옆 사람과의 대화나 통화에는 대답하지 않아요. 다음 손님부터 적용돼요.</p>
</section>

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

<section>
  <h3>휴대폰 화면 가려지는 부분</h3>
  <p class="note flush">
    휴대폰 버전에서 선택지와 주문 현황이 피하는 가장자리. 위·아래는 화면 높이의, 왼쪽·오른쪽은 화면
    너비의 %예요. (높이 31.5cm에서 1cm ≈ 3.2%, 너비 19.5cm에서 1cm ≈ 5.1%)
  </p>
  <div class="insets">
    {#each INSET_SIDES as side (side.key)}
      <label>
        {side.label}
        <input
          type="number"
          min="0"
          max={MAX_INSET}
          step="0.1"
          value={settings.phoneInsets[side.key]}
          onchange={(e) => inset(side.key, e.currentTarget.valueAsNumber)}
        />
        %
      </label>
    {/each}
  </div>
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
  .note {
    margin: -0.3rem 0 0 2.2rem;
    color: #b9aca1;
    word-break: keep-all;
  }
  .note.flush {
    margin-left: 0;
  }
  .insets {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem 1rem;
  }
  .insets label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  input[type='number'] {
    width: 4.5rem;
    margin-left: auto;
    font: inherit;
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
