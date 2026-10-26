import type { Menu, MenuItem, OptionGroup } from './events';

export function itemById(menu: Menu | null, id: string): MenuItem | undefined {
  return menu?.items.find((i) => i.id === id);
}

export function groupById(menu: Menu | null, id: string): OptionGroup | undefined {
  return menu?.option_groups.find((g) => g.id === id);
}

/** The counting word for an item's quantity, e.g. "잔" for drinks, "개" for desserts. */
/** An order line's options in the screen's words (e.g. "차갑게, 라지"), without "기본"/"없음". */
export function optionLabels(menu: Menu | null, chosen: Record<string, string[]>): string {
  return Object.entries(chosen)
    .flatMap(([groupId, ids]) => {
      const group = groupById(menu, groupId);
      return ids
        .filter((id) => id !== 'none')
        .map((id) => {
          const c = group?.choices.find((x) => x.id === id);
          return c ? c.label || c.say || c.name : id;
        });
    })
    .join(', ');
}

export function unitOf(menu: Menu | null, itemId: string): string {
  const category = itemById(menu, itemId)?.category;
  return menu?.categories.find((c) => c.id === category)?.unit ?? '개';
}

export function allergenNames(menu: Menu, ids: string[]): string[] {
  return ids.map((id) => menu.allergens.find((a) => a.id === id)?.name ?? id);
}

export const CAFFEINE: Record<MenuItem['caffeine'], string> = {
  none: '카페인 없음',
  low: '카페인 적음',
  medium: '카페인 보통',
  high: '카페인 많음',
};

export const SERVED: Record<'hot' | 'ice', string> = {
  hot: '따뜻하게만',
  ice: '아이스로만',
};

export const TOPIC_ICONS: Record<string, string> = {
  hours: '🕘',
  wifi: '📶',
  restroom: '🚻',
  pickup: '🛎️',
  waiting_time: '⏱️',
  outlets: '🔌',
  parking: '🅿️',
  allergy: '⚠️',
  refill: '🔁',
};
