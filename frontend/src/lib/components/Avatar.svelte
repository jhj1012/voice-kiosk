<script lang="ts">
  // The avatar, standing behind everything: data/avatar/<clip>.webm (transparent background).
  // Every clip is loaded at once and only the current one is visible, so switching is instant.
  // Clips that do not exist yet show the still image (data/avatar/avatar.png).
  import { untrack } from 'svelte';
  import { LOOPS, nextClip } from '../avatar';
  import type { AvatarClip } from '../events';
  import { ui } from '../store.svelte';

  const CLIPS: AvatarClip[] = ['idle', 'pick_up', 'listening', 'talking', 'put_down'];

  const files = $derived(ui.avatar);
  const onLine = $derived(ui.state.phase !== 'idle');
  const speaking = $derived(ui.state.assistant === 'speaking');
  const has = (clip: AvatarClip) => !!files?.[clip];

  let current = $state<AvatarClip>('idle');
  let ready = $state<Record<string, boolean>>({});
  const videos: Partial<Record<AvatarClip, HTMLVideoElement>> = {};

  $effect(() => {
    const [line, talk] = [onLine, speaking];
    untrack(() => (current = nextClip(current, line, talk, false, has)));
  });

  // Each time a clip becomes current it starts from its first frame.
  $effect(() => {
    const clip = current;
    untrack(() => {
      for (const [name, video] of Object.entries(videos)) {
        if (name === clip) {
          video.currentTime = 0;
          void video.play().catch(() => {});
        } else {
          video.pause();
        }
      }
    });
  });

  function ended(clip: AvatarClip) {
    if (clip === current) current = nextClip(current, onLine, speaking, true, has);
  }

  const showStill = $derived(!files?.[current] || !ready[current]);
</script>

<div class="avatar" aria-hidden="true">
  {#if files?.still && showStill}
    <img src={files.still} alt="" />
  {/if}
  {#each CLIPS as clip (clip)}
    {#if files?.[clip]}
      <video
        bind:this={videos[clip]}
        class:visible={clip === current && ready[clip]}
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
  video {
    opacity: 0;
  }
  video.visible {
    opacity: 1;
  }
</style>
