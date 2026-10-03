// Events between the backend and the display (see kiosk/server/events.py and
// docs/architecture.md). The display only renders what these events say.

export type Speaker = 'customer' | 'assistant';
export type Phase = 'idle' | 'ordering' | 'paying' | 'done';
export type AssistantState = 'idle' | 'connecting' | 'listening' | 'thinking' | 'speaking';
export type Screen =
  'attract' | 'welcome' | 'menu' | 'item' | 'info' | 'review' | 'payment' | 'done';
export type PaymentStep = 'insert_card' | 'processing' | 'approved';

export interface Choice {
  id: string;
  name: string;
  say: string;
  price: number;
}

export interface OptionGroup {
  id: string;
  name: string;
  required: boolean;
  multi: boolean;
  choices: Choice[];
}

export interface MenuItem {
  id: string;
  name: string;
  category: string;
  price: number;
  emoji: string;
  image_url: string | null;
  description: string;
  ingredients: string[];
  allergens: string[];
  caffeine: 'none' | 'low' | 'medium' | 'high';
  sweetness: number;
  recommended: boolean;
  temperature: 'hot' | 'ice' | null;
  options: string[];
}

export interface Menu {
  categories: { id: string; name: string; unit: string }[];
  allergens: { id: string; name: string }[];
  option_groups: OptionGroup[];
  items: MenuItem[];
}

export interface Cafe {
  name: string;
  topics: { id: string; title: string; text: string }[];
}

export interface View {
  screen: Screen;
  title: string;
  item_ids: string[];
  highlight: string[];
  item_id: string;
  topic: string;
}

export interface Pending {
  item_id: string;
  quantity: number;
  chosen: Record<string, string[]>;
  missing: string[];
}

export interface OrderLine {
  line: number;
  item_id: string;
  name: string;
  options: string;
  quantity: number;
  unit_price: number;
  total: number;
}

export interface Order {
  lines: OrderLine[];
  dining: 'here' | 'to_go' | null;
  count: number;
  total: number;
}

export interface InitEvent {
  type: 'init';
  menu: Menu;
  cafe: Cafe;
}

export interface StateEvent {
  type: 'state';
  seq: number;
  phase: Phase;
  assistant: AssistantState;
  view: View;
  pending: Pending | null;
  order: Order;
  payment: { step: PaymentStep; order_number: number | null } | null;
}

export interface SubtitleEvent {
  type: 'subtitle';
  id: number;
  speaker: Speaker;
  text: string;
  final: boolean;
}

export interface LevelEvent {
  type: 'level';
  mic: number;
  out: number;
}

export interface NoticeEvent {
  type: 'notice';
  level: 'info' | 'warn' | 'error';
  text: string;
}

export type ServerEvent = InitEvent | StateEvent | SubtitleEvent | LevelEvent | NoticeEvent;

// Display -> backend (developer mode only).
export type ClientEvent =
  | { type: 'hook'; off_hook: boolean }
  | { type: 'dev_text'; text: string }
  | { type: 'dev_mute'; audio: boolean };
