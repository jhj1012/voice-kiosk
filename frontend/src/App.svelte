<script lang="ts">
  // Picks the event source: the backend's WebSocket, or a recorded demo timeline
  // (?demo=order, ?demo=allergy; &at=<ms> starts later, &pause stops there; &dev opens the
  // developer panel; &backdrop=blur|gradient|boxes picks the choices' background).
  import { onMount } from 'svelte';
  import type { ClientEvent, ServerEvent } from './lib/events';
  import { connect, type Connection } from './lib/connection';
  import { play, type Timeline } from './lib/player';
  import { dispatch, previewSettings, ui } from './lib/store.svelte';
  import DevPanel from './lib/components/DevPanel.svelte';
  import Stage from './lib/components/Stage.svelte';

  const params = new URLSearchParams(location.search);
  const demoName = params.get('demo');
  const mode = demoName !== null ? 'demo' : 'live';

  let devOpen = $state(params.has('dev'));
  let connected = $state(false);
  let log = $state.raw<{ at: number; event: ServerEvent }[]>([]);
  let connection: Connection | null = null;

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
    } else if (event.code === 'Space' && !(event.target instanceof HTMLInputElement)) {
      event.preventDefault();
      send({ type: 'hook', off_hook: ui.state.phase === 'idle' });
    }
  }

  async function startDemo(): Promise<() => void> {
    // Loaded only in demo mode, so the kiosk's own bundle stays small.
    const demo = (await import('./dev/demo.json')).default;
    const scenarios = demo.scenarios as unknown as Record<string, Timeline>;
    dispatch(demo.init as ServerEvent);
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

<svelte:window onkeydown={onKey} />

<Stage />
{#if devOpen}
  <DevPanel {send} {mode} {connected} {log} />
{/if}
