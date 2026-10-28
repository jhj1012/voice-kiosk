// Every place on the screen with its own text size (the `--text-role` its CSS rule names), for
// the text size editor (F4). A new font-size in the CSS gets a role here too, or it cannot be
// adjusted (textRoles.test.ts checks this).

export const TEXT_ROLES: Record<string, string> = {
  'page-caption': '제목 문구',
  'stage-prompt': '안내 문구',
  'stage-prompt-small': '메뉴판 안내 문구',
  'subtitles-assistant': '자막 · AI',
  'subtitles-customer': '자막 · 손님',
  'notice-notice': '알림',
  'diningchoice-emoji': '매장/포장 · 이모지',
  'diningchoice-label': '매장/포장 · 이름',
  'categorylist-emoji': '카테고리 · 이모지',
  'categorylist-name': '카테고리 · 이름',
  'categorylist-count': '카테고리 · 메뉴 개수',
  'menulist-name': '메뉴 목록 · 메뉴 이름',
  'menulist-price': '메뉴 목록 · 가격',
  'itemimage-emoji': '메뉴 이모지',
  'itemimage-l-emoji': '메뉴 이모지 (크게)',
  'itemimage-s-emoji': '메뉴 이모지 (작게)',
  'itemdetail-h2': '메뉴 · 이름',
  'itemdetail-price': '메뉴 · 가격',
  'itemdetail-chip': '메뉴 · 고른 옵션 표시',
  'itemdetail-choice': '옵션 선택 · 옵션 이름',
  'itemdetail-row-chosen-choice': '옵션 선택 · 선택된 옵션 (파란 바탕)',
  'itemdetail-extra': '옵션 선택 · 추가 금액',
  'itemdetail-group': '옵션 · 종류 이름',
  'itemdetail-pill': '추가 옵션 · 이름',
  'itemdetail-pill-small': '추가 옵션 · 금액',
  'itemdetail-pill-on': '추가 옵션 · 선택된 것 (파란 바탕)',
  'itemdetail-value': '옵션 한눈에 · 고른 값',
  'itemdetail-facts': '메뉴 · 재료와 정보',
  'info-icon': '매장 안내 · 아이콘',
  'info-h2': '매장 안내 · 제목',
  'info-p': '매장 안내 · 내용',
  'orderbar-count': '주문 현황 · 개수',
  'orderbar-total': '주문 현황 · 합계',
  'review-name': '주문 확인 · 메뉴 이름',
  'review-options': '주문 확인 · 옵션',
  'review-qty': '주문 확인 · 수량',
  'review-amount': '주문 확인 · 금액',
  'review-dining': '주문 확인 · 매장/포장',
  'review-label': '주문 확인 · 합계 라벨',
  'review-value': '주문 확인 · 합계 금액',
  'staffnotes-label': '직원 메모 · 라벨',
  'staffnotes-ul': '직원 메모 · 내용',
  'payment-screen': '결제 · 단말기 화면',
  'payment-h2': '결제 · 안내',
  'done-label': '완료 · 라벨',
  'done-number': '완료 · 주문 번호',
  'done-note': '완료 · 안내',
};

/** The role of the text at an element: the nearest rule that named one (custom properties
 * inherit), or null outside the kiosk's screens. */
export function textRoleAt(element: Element): string | null {
  const role = getComputedStyle(element).getPropertyValue('--text-role').trim();
  return role in TEXT_ROLES ? role : null;
}
