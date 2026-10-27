<script lang="ts">
  // The image slot of a menu item: data/images/<item_id>.png when it exists (a transparent
  // background shows the "menu image background" colour), otherwise the item's emoji.
  import type { MenuItem } from '../events';

  let { item, size = 'm' }: { item: MenuItem; size?: 's' | 'm' | 'l' } = $props();
  let failed = $state(false);
</script>

<div class="tile {size}">
  {#if item.image_url && !failed}
    <img src={item.image_url} alt={item.name} onerror={() => (failed = true)} />
  {:else}
    <span class="emoji" aria-hidden="true">{item.emoji || '☕'}</span>
  {/if}
</div>

<style>
  .tile {
    position: relative; /* the image fills it and never sizes it (photos are 1024 px wide) */
    width: 100%;
    aspect-ratio: 1;
    border-radius: var(--radius-m);
    overflow: hidden;
    display: grid;
    place-items: center;
    background: var(--image-bg);
  }
  .tile.l {
    border-radius: var(--radius-l);
  }
  .tile.s {
    border-radius: var(--radius-s);
  }
  img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: contain;
  }
  .emoji {
    --text-role: itemimage-emoji;
    font-size: calc(5.5rem * var(--size-all) * var(--fs-itemimage-emoji, 1));
  }
  .l .emoji {
    --text-role: itemimage-l-emoji;
    font-size: calc(13rem * var(--size-all) * var(--fs-itemimage-l-emoji, 1));
  }
  .s .emoji {
    --text-role: itemimage-s-emoji;
    font-size: calc(2.2rem * var(--size-all) * var(--fs-itemimage-s-emoji, 1));
  }
</style>
