import { describe, expect, it } from 'vitest';
import pageCss from '../app.css?raw';
import { TEXT_ROLES } from './textRoles';

const components = import.meta.glob('./components/*.svelte', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

describe('text roles', () => {
  const css = [pageCss, ...Object.values(components)].join('\n');
  const named = [...css.matchAll(/--text-role: ([a-z0-9-]+);/g)].map((m) => m[1]);

  it('every font size on the screens has a role with a name, and every role is used', () => {
    expect(new Set(named).size).toBe(named.length);
    expect(named.filter((role) => !(role in TEXT_ROLES))).toEqual([]);
    expect(Object.keys(TEXT_ROLES).filter((role) => !named.includes(role))).toEqual([]);
  });

  it("each role's size is its own", () => {
    for (const role of named) {
      expect(css).toContain(`var(--size-all) * var(--fs-${role}, 1)`);
    }
  });
});
