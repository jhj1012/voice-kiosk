<script lang="ts">
  // The handset was lifted: a greeting and a few things the customer could say.
  import { fly } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';

  const examples = [
    '“메뉴 뭐 있어요?”',
    '“아이스 아메리카노 한 잔 주세요”',
    '“우유 안 들어간 거 있어요?”',
  ];
</script>

<div class="welcome">
  <p class="hello">안녕하세요</p>
  <h1>무엇을 드릴까요?</h1>
  <p class="hint">편하게 말씀해 주세요. 예를 들면</p>
  <ul>
    {#each examples as example, i (example)}
      <li in:fly|global={{ y: 16, delay: 500 + i * 180, duration: 500, easing: cubicOut }}>
        {example}
      </li>
    {/each}
  </ul>
</div>

<style>
  .welcome {
    height: 100%;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 0 9rem;
    gap: 1.4rem;
  }
  .hello {
    font-size: 1.8rem;
    font-weight: 600;
    color: var(--accent);
  }
  h1 {
    font-size: 5.6rem;
    font-weight: 800;
    letter-spacing: -0.035em;
  }
  .hint {
    margin-top: 2.4rem;
    font-size: 1.5rem;
    color: var(--muted);
  }
  ul {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
  }
  li {
    font-size: 1.7rem;
    padding: 1rem 1.6rem;
    border-radius: 999px;
    background: var(--surface);
    box-shadow: var(--shadow-s);
    color: var(--text-2);
  }
</style>
