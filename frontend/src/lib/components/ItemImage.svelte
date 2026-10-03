<script lang="ts">
  // The image slot of a menu item: data/images/<item_id>.png when it exists, otherwise the
  // item's emoji on a soft tile in its category's colors.
  import type { MenuItem } from '../events';

  let { item, size = 'm' }: { item: MenuItem; size?: 's' | 'm' | 'l' } = $props();
  let failed = $state(false);
</script>

<div class="tile {size}" style:background="var(--tile-{item.category}, var(--tile-coffee))">
  {#if item.image_url && !failed}
    <img src={item.image_url} alt={item.name} onerror={() => (failed = true)} />
  {:else}
    <span class="emoji" aria-hidden="true">{item.emoji || '☕'}</span>
  {/if}
</div>

<style>
  .tile {
    position: relative;
    width: 100%;
    aspect-ratio: 1;
    border-radius: var(--radius-m);
    overflow: hidden;
    display: grid;
    place-items: center;
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
    font-size: 4.6rem;
    filter: drop-shadow(0 0.6rem 0.8rem rgb(70 45 25 / 0.18));
  }
  .l .emoji {
    font-size: 12rem;
  }
  .s .emoji {
    font-size: 1.7rem;
    filter: none;
  }
</style>
