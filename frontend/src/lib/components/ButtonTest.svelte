<script lang="ts">
  // A test page (?buttons): which signals the handset's button sends to this page. On Android a
  // headset button acts as play / pause for the app playing sound; Chrome passes it to the page
  // through the Media Session API, but only while the page plays sound with an <audio> element.
  // So a tap starts a silent loop (lib/mediaButton.ts), and every media action and key that
  // arrives is listed.
  import { playLoop } from '../mediaButton';

  const ACTIONS = [
    'play',
    'pause',
    'stop',
    'nexttrack',
    'previoustrack',
    'seekbackward',
    'seekforward',
    'hangup',
    'togglemicrophone',
  ] as const;

  let started = $state(false);
  let quietNoise = $state(false); // a barely audible hiss instead of digital silence
  let micOn = $state(false);
  let log = $state<{ id: number; time: string; text: string }[]>([]);
  let nextId = 0;
  let audio: HTMLAudioElement | null = null;
  let mic: MediaStream | null = null;

  function add(text: string) {
    const time = new Date().toLocaleTimeString('ko-KR', { hour12: false });
    log = [{ id: nextId++, time, text }, ...log].slice(0, 40);
  }

  function start() {
    audio?.pause();
    audio = playLoop(quietNoise);
    add(`소리 재생 시작 (${quietNoise ? '아주 작은 잡음' : '무음'})`);
    const session = navigator.mediaSession;
    if (!session) {
      add('이 브라우저는 Media Session을 지원하지 않아요');
      return;
    }
    session.metadata = new MediaMetadata({ title: '키오스크 버튼 테스트', artist: 'voice-kiosk' });
    session.playbackState = 'playing';
    for (const action of ACTIONS) {
      try {
        type Action = Parameters<typeof session.setActionHandler>[0];
        session.setActionHandler(action as Action, () => {
          add(`버튼 신호: ${action}`);
          // keep sounding, so the session stays ours; only the state the button toggles
          if (action === 'pause') session.playbackState = 'paused';
          if (action === 'play') session.playbackState = 'playing';
        });
      } catch {
        add(`(이 Chrome은 ${action} 신호를 받을 수 없어요)`);
      }
    }
    started = true;
  }

  async function toggleMic() {
    if (mic) {
      mic.getTracks().forEach((t) => t.stop());
      mic = null;
      micOn = false;
      add('마이크 끔');
      return;
    }
    try {
      mic = await navigator.mediaDevices.getUserMedia({ audio: true });
      micOn = true;
      add('마이크 켬 (대화 중과 같은 상태)');
    } catch (error) {
      add(`마이크를 켤 수 없어요: ${error}`);
    }
  }

  function onKey(event: KeyboardEvent) {
    add(`키 ${event.type === 'keydown' ? '누름' : '뗌'}: key=${event.key} code=${event.code}`);
  }

  function onVisibility() {
    add(`화면 ${document.visibilityState === 'visible' ? '보임' : '숨김'}`);
  }
</script>

<svelte:window onkeydown={onKey} onkeyup={onKey} />
<svelte:document onvisibilitychange={onVisibility} />

<div class="test">
  <h1>수화기 버튼 테스트</h1>
  <p class="note">
    1. <b>시작</b>을 누르세요 (들리지 않는 소리가 계속 재생돼요). 2. 수화기 버튼을 한 번, 두 번,
    길게 눌러 보세요. 3. 마이크를 켜고도 다시 눌러 보세요. 아래에 들어온 신호가 나와요.
  </p>
  <div class="controls">
    <button type="button" class="primary" onclick={start}>{started ? '다시 시작' : '시작'}</button>
    <button type="button" onclick={toggleMic}>{micOn ? '마이크 끄기' : '마이크 켜기'}</button>
    <label><input type="checkbox" bind:checked={quietNoise} /> 무음 대신 아주 작은 잡음</label>
  </div>
  <ol>
    {#each log as entry (entry.id)}
      <li><span class="time">{entry.time}</span> {entry.text}</li>
    {:else}
      <li class="empty">아직 들어온 신호가 없어요</li>
    {/each}
  </ol>
</div>

<style>
  .test {
    position: absolute;
    inset: 0;
    overflow-y: auto;
    padding: 4rem 4rem 6rem;
    background: #ffffff;
    color: #0e1a2b;
    font-size: 2.6rem;
    cursor: auto;
    user-select: text;
  }
  h1 {
    font-size: 4rem;
    margin-bottom: 1.6rem;
  }
  .note {
    color: #4b5b71;
    line-height: 1.5;
    word-break: keep-all;
  }
  .controls {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 1.6rem;
    margin: 2.4rem 0;
  }
  button {
    padding: 1.4rem 3rem;
    border: 0.25rem solid #2f6fed;
    border-radius: 999px;
    background: #ffffff;
    color: #2f6fed;
    font: inherit;
    font-weight: 700;
  }
  .primary {
    background: #2f6fed;
    color: #ffffff;
  }
  input {
    width: 2.6rem;
    height: 2.6rem;
  }
  ol {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
  }
  li {
    padding: 1rem 1.4rem;
    border-radius: 1.2rem;
    background: #eef4ff;
  }
  .time {
    color: #94a3b8;
    font-variant-numeric: tabular-nums;
  }
  .empty {
    color: #94a3b8;
  }
</style>
