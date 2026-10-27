<script lang="ts">
  // The avatar, standing behind everything: data/avatar/<clip>.webm (transparent background).
  // Every clip is loaded at once and only the current one is visible. A new clip fades in over
  // the one before, which keeps playing until it is covered: AI-made clips never meet exactly.
  // Clips that do not exist yet show the still image (data/avatar/avatar.png).
  import { untrack } from 'svelte';
  import { LOOPS, nextClip } from '../avatar';
  import type { AvatarClip } from '../events';
  import { ui } from '../store.svelte';

  const CLIPS: AvatarClip[] = ['idle', 'pick_up', 'listening', 'talking', 'put_down'];
  const FADE_MS = 300;

  const files = $derived(ui.avatar);
  const onLine = $derived(ui.state.phase !== 'idle');
  const speaking = $derived(ui.state.assistant === 'speaking');
  const has = (clip: AvatarClip) => !!files?.[clip];

  let current = $state<AvatarClip>('idle');
  let leaving = $state<AvatarClip | null>(null);
  let fadeTimer: ReturnType<typeof setTimeout> | undefined;
  let ready = $state<Record<string, boolean>>({});
  const videos: Partial<Record<AvatarClip, HTMLVideoElement>> = {};

  $effect(() => {
    const [line, talk] = [onLine, speaking];
    untrack(() => (current = nextClip(current, line, talk, false, has)));
  });

  // Each time a clip becomes current it starts from its first frame and fades in over the one
  // before; that one stops once covered.
  let shown: AvatarClip | null = null;
  $effect(() => {
    const clip = current;
    untrack(() => {
      const before = shown;
      shown = clip;
      leaving = before !== null && before !== clip && ready[before] ? before : null;
      clearTimeout(fadeTimer);
      for (const [name, video] of Object.entries(videos)) {
        if (name === clip) {
          video.currentTime = 0;
          void video.play().catch(() => {});
        } else if (name !== leaving) {
          video.pause();
        }
      }
      if (leaving) {
        fadeTimer = setTimeout(() => {
          if (leaving) videos[leaving]?.pause();
          leaving = null;
        }, FADE_MS);
      }
    });
  });

  function ended(clip: AvatarClip) {
    if (clip === current) current = nextClip(current, onLine, speaking, true, has);
  }

  const showStill = $derived(!files?.[current] || !ready[current]);
</script>

<div class="avatar" class:phone={ui.phone} aria-hidden="true">
  {#if files?.still && showStill}
    <img src={files.still} alt="" />
  {/if}
  {#each CLIPS as clip (clip)}
    {#if files?.[clip]}
      <video
        bind:this={videos[clip]}
        class:visible={clip === current && ready[clip]}
        class:leaving={clip === leaving}
        style:--fade="{FADE_MS}ms"
        src={files[clip]}
        muted
        playsinline
        preload="auto"
        loop={LOOPS.includes(clip)}
        oncanplay={() => (ready[clip] = true)}
        onended={() => ended(clip)}
      ></video>
    {/if}
  {/each}
</div>

<style>
  .avatar {
    position: absolute;
    inset: 0;
    pointer-events: none;
    isolation: isolate; /* the clips' z-index stays behind the rest of the page */
  }
  img,
  video {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center bottom;
  }
  /* The phone's screen is wider than the 9:16 clips, so they are cut at the top or the bottom:
     the bottom, which its case covers anyway. He stands lower and his face clears the order,
     which is at the top there. */
  .phone img,
  .phone video {
    object-position: center top;
  }
  video {
    opacity: 0;
  }
  /* The clip before stays fully shown underneath while the new one fades in over it. */
  video.leaving {
    opacity: 1;
    z-index: 1;
  }
  video.visible {
    opacity: 1;
    z-index: 2;
    transition: opacity var(--fade) ease-out;
    /* Also with reduced motion (app.css): the fade makes a cut gentler, it adds no motion. */
    transition-duration: var(--fade) !important;
  }
</style>
