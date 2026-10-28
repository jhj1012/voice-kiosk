<script lang="ts">
  // Picks the event source: the backend's WebSocket, or a recorded demo timeline
  // (?demo=order, ?demo=allergy; &at=<ms> starts later, &pause stops there; &dev opens the
  // developer panel; &backdrop=blur|gradient|boxes picks the choices' background; &phone shows
  // the phone mode's screen). F2 opens the developer panel, F4 the text size editor.
  // On the phone of the phone mode a tap anywhere starts the conversation (and turns on the
  // phone's microphone and speaker the first time). From that tap on, the handset's button
  // starts and ends it (on the laptop, Space).
  import { onMount } from 'svelte';
  import type { ClientEvent, ServerEvent } from './lib/events';
  import { connect, type Connection } from './lib/connection';
  import { startMediaButton } from './lib/mediaButton';
  import { startPhoneAudio, type PhoneAudio } from './lib/phone';
  import { play, type Timeline } from './lib/player';
  import { dispatch, openTextEdit, previewSettings, ui } from './lib/store.svelte';
  import DevPanel from './lib/components/DevPanel.svelte';
  import Stage from './lib/components/Stage.svelte';
  import TextSizeEditor from './lib/components/TextSizeEditor.svelte';

  const params = new URLSearchParams(location.search);
  const demoName = params.get('demo');
  const mode = demoName !== null ? 'demo' : 'live';

  let devOpen = $state(params.has('dev'));
  let connected = $state(false);
  let log = $state.raw<{ at: number; event: ServerEvent }[]>([]);
  let connection: Connection | null = null;
  let phoneAudio = $state.raw<PhoneAudio | null>(null);
  let phoneStarting = false;
  let buttonOn = false; // the handset's button (lib/mediaButton.ts)
  let wakeLock: WakeLockSentinel | null = null;

  // The phone sends its microphone only while a conversation is on.
  $effect(() => phoneAudio?.setActive(ui.state.phase !== 'idle'));
  $effect(() => {
    document.body.classList.toggle('phone-mode', ui.phone);
  });
  $effect(() => {
    document.body.classList.toggle('text-edit', ui.textEdit);
  });

  function receive(event: ServerEvent) {
    dispatch(event);
    const partial = event.type === 'subtitle' && !event.final;
    if (devOpen && event.type !== 'level' && !partial) {
      log = [...log.slice(-40), { at: performance.now() + Math.random(), event }];
    }
  }

  function send(event: ClientEvent) {
    if (connection) connection.send(event);
    else console.info('demo mode, not sent:', event);
  }

  function onKey(event: KeyboardEvent) {
    if (event.key === 'F2') {
      event.preventDefault();
      devOpen = !devOpen;
    } else if (event.key === 'F4') {
      event.preventDefault();
      openTextEdit(!ui.textEdit);
    } else if (event.code === 'Space' && !(event.target instanceof HTMLInputElement)) {
      event.preventDefault();
      send({ type: 'hook', off_hook: ui.state.phase === 'idle' });
    }
  }

  /** The phone: a tap anywhere while idle starts the conversation; from then on the handset's
   * button starts and ends it. Any tap brings back full screen (also during a conversation). */
  async function onTap() {
    if (!ui.phone) return;
    // Full screen, the wake lock and the button's silent loop need the tap itself, before
    // anything is awaited.
    if (!document.fullscreenElement)
      void document.documentElement.requestFullscreen?.().catch(() => {});
    if (ui.keyForm || ui.state.phase !== 'idle' || phoneStarting) return;
    void keepAwake();
    if (!buttonOn) {
      buttonOn = true;
      startMediaButton(onHandsetButton);
    }
    if (!phoneAudio) {
      phoneStarting = true;
      try {
        phoneAudio = await startPhoneAudio();
      } catch (error) {
        console.warn('no microphone', error);
        receive({
          type: 'notice',
          level: 'error',
          text: '마이크를 쓸 수 없어요. Chrome에서 마이크를 허용한 뒤 다시 눌러 주세요.',
        });
        return;
      } finally {
        phoneStarting = false;
      }
      receive({ type: 'notice', level: 'info', text: '' });
    }
    send({ type: 'hook', off_hook: true });
  }

  /** The handset's button (one press): starts the conversation, or ends it. */
  function onHandsetButton() {
    if (ui.keyForm || phoneStarting || !phoneAudio) return;
    if (ui.state.phase === 'idle') void keepAwake();
    send({ type: 'hook', off_hook: ui.state.phase === 'idle' });
  }

  /** Keeps the phone's screen on (Chrome lets it go when the page is hidden). */
  async function keepAwake() {
    if (wakeLock && !wakeLock.released) return;
    try {
      wakeLock = (await navigator.wakeLock?.request('screen')) ?? null;
    } catch {
      wakeLock = null; // e.g. battery saver: the screen may turn off, nothing else changes
    }
  }

  async function startDemo(): Promise<() => void> {
    // Loaded only in demo mode, so the kiosk's own bundle stays small.
    const demo = (await import('./dev/demo.json')).default;
    const scenarios = demo.scenarios as unknown as Record<string, Timeline>;
    dispatch({ ...(demo.init as ServerEvent & { type: 'init' }), phone: params.has('phone') });
    if (params.get('backdrop')) previewSettings({ backdrop: params.get('backdrop') });
    connected = true;
    return play(scenarios[demoName!] ?? Object.values(scenarios)[0], receive, {
      startAt: Number(params.get('at') ?? 0),
      pause: params.has('pause'),
    });
  }

  onMount(() => {
    if (!params.has('cursor')) document.body.classList.add('kiosk-mode');
    if (mode === 'demo') {
      const stop = startDemo();
      return () => void stop.then((s) => s());
    }
    connection = connect(receive, (ok) => {
      connected = ok;
      if (!ok) receive({ type: 'notice', level: 'warn', text: '키오스크 서버에 연결하고 있어요' });
      else receive({ type: 'notice', level: 'info', text: '' });
    });
    return () => connection?.close();
  });
</script>

<svelte:window onkeydown={onKey} onpointerup={onTap} />

<Stage />
{#if devOpen}
  <DevPanel {send} {mode} {connected} {log} />
{/if}
{#if ui.textEdit}
  <TextSizeEditor {send} />
{/if}
