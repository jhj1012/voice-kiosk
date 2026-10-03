<script lang="ts">
  // The image slot of a menu item: data/images/<item_id>.png when it exists, otherwise the
  // item's emoji on a soft blue tile.
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
    width: 100%;
    aspect-ratio: 1;
    border-radius: var(--radius-m);
    overflow: hidden;
    display: grid;
    place-items: center;
    background: linear-gradient(160deg, #f6f9ff, var(--tint-2));
  }
  .tile.l {
    border-radius: var(--radius-l);
  }
  .tile.s {
    border-radius: var(--radius-s);
  }
  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .emoji {
    font-size: 5.5rem;
  }
  .l .emoji {
    font-size: 13rem;
  }
  .s .emoji {
    font-size: 2.2rem;
  }
</style>
