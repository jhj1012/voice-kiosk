/** Format a price the Korean way, e.g. 4500 -> "4,500원". */
export function won(amount: number): string {
  return `${amount.toLocaleString('ko-KR')}원`;
}
