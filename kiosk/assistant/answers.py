"""Whose answer is it, and for which drink: the rules for the calls that put the customer's
choices in (order, set_options, change, no_more_extras). See docs/conversation-rules.md,
section 4.

The model passes options; these rules decide what of it the customer really said and for which
drink:

- An option nobody mentioned is a guess: left out, the kiosk asks (`guessed_groups`). An answer
  to the question on screen is always taken, once the customer spoke after it was asked.
- One answer is for one drink. When the same item is being chosen more than once (or is already
  in the order) and the customer did not say "둘 다", it goes to the drink asked about and the
  kiosk asks "따뜻한 아메리카노도 레귤러로 해 드릴까요?"; the same answer put on the other drink
  in the same turn is held until then. "네" sets it; "아니" sets the only other choice of a
  two-choice option (temperature, size), or leaves an extra out.
- An answer for some cups ("하나만 라지로") splits them off (the domain does that); with "만" the
  rest get the only other choice ("2개만 아이스로": the rest are hot).
- The extras question waits for the customer's answer.

What differs between kinds of options is in `OptionRule`; the words in `safety`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from kiosk.assistant.actions import Actions, Drink, Result
from kiosk.assistant.safety import (
    Transcript,
    guessed_groups,
    is_no,
    is_yes,
    meant_for_all,
    only_some,
    wants_nothing_more,
)
from kiosk.assistant.tools import selection_from_args
from kiosk.domain.flow import Ask, Draft, Kiosk
from kiosk.domain.menu import Chosen, KioskError, OptionChoice, OptionGroup
from kiosk.domain.order import CartLine

log = logging.getLogger(__name__)

NOT_SAID = (
    "The customer did not mention {groups}, so it was not set: never fill in an option. Ask the "
    "result's question."
)
EXTRAS_NOT_ANSWERED = (
    "Not done: the customer has not answered '추가하실 거 있으세요?' yet. Wait for their answer; "
    "call no_more_extras only after they say they want nothing (more)."
)

Ids = tuple[str, ...]


@dataclass(frozen=True)
class OptionRule:
    """How an answer about one option group is treated."""

    group: OptionGroup

    def counts(self, choices: tuple[OptionChoice, ...]) -> bool:
        """An answer worth checking: a temperature or size, or an extra actually wanted."""
        return self.group.required or any(not c.is_none for c in choices)

    def other(self, choices: tuple[OptionChoice, ...]) -> OptionChoice | None:
        """What "아니" (or "the rest") means: the only other choice of a required group with
        two ("라지가 아니면 레귤러"); None for extras or more choices."""
        if not self.group.required:
            return None
        left = [c for c in self.group.choices if c not in choices]
        return left[0] if len(left) == 1 else None

    def still_open(self, drink: Drink, ids: Ids) -> bool:
        """`drink` may want this answer too: a drink being chosen still missing a temperature or
        size, or one asked about extras (or already in the order) without this extra."""
        has = tuple(c.id for c in _chosen(drink).get(self.group.id, ()))
        if self.group.required:
            return isinstance(drink, Draft) and any(m.id == self.group.id for m in drink.missing)
        return has != ids and (isinstance(drink, CartLine) or drink.ask_extras)


@dataclass(frozen=True)
class Given:
    """An option set since the customer last spoke."""

    draft: int
    item_id: str
    group: str
    ids: Ids


@dataclass(frozen=True)
class Checking:
    """The kiosk asked "따뜻한 아메리카노도 레귤러로 해 드릴까요?" about a drink being chosen."""

    draft: int
    group: str
    ids: Ids


class Answers:
    """The rules, and what they remember of the conversation."""

    def __init__(self, kiosk: Kiosk, actions: Actions, transcript: Transcript) -> None:
        self.kiosk = kiosk
        self.actions = actions
        self.transcript = transcript
        # Where the transcript was when the kiosk's question last changed: only customer words
        # after it answer that question (not an answer the model made up right after asking).
        self._question_mark = 0
        self._given: list[Given] = []
        self._given_mark = -1  # the customer utterance `_given` belongs to
        self._checking: Checking | None = None

    # --- for the session -----------------------------------------------------------------------

    def call(self, name: str, args: dict[str, Any]) -> Result:
        """Run one of the calls these rules cover."""
        if name == "set_options":
            return self._set_options(args)
        if name == "order":
            return self._without_guesses(name, args)
        if name == "change":
            return self._held_for_line(args) or self.actions.call(name, args)
        if name == "no_more_extras" and not self._extras_answered():
            log.info("no_more_extras before the customer answered: not done")
            return {"not_done": EXTRAS_NOT_ANSWERED}
        return self.actions.call(name, args)

    def question_changed(self) -> None:
        """The kiosk asks something new: answers to it come from here on."""
        self._question_mark = len(self.transcript.entries)

    # --- set_options -----------------------------------------------------------------------------

    def _set_options(self, args: dict[str, Any]) -> Result:
        menu = self.kiosk.menu
        try:
            draft = self._draft(args)
            chosen = menu.resolve(draft.item, selection_from_args(menu, args))
        except (KioskError, TypeError, ValueError):
            return self._without_guesses("set_options", args)
        quantity = args.get("quantity")
        if chosen and quantity and int(float(quantity)) < draft.quantity:
            # "하나만 라지로": the customer said which cups (split off), nothing to check
            return self._split_rest(draft, chosen, self._without_guesses("set_options", args))
        self._fresh_given()  # the customer spoke since: a new answer
        latest = self._latest()
        for_all = meant_for_all(latest)
        answer = {
            g: tuple(c.id for c in cs)
            for g, cs in chosen.items()
            if self._rule(draft, g).counts(cs)
        }

        # The same answer already went to another drink of this item in this turn: hold it.
        held = [
            g for g, ids in answer.items() if not for_all and self._given_elsewhere(draft, g, ids)
        ]
        confirm: Result = {}
        for g in held:
            args.pop(g, None)
            del answer[g]
        if held:
            group = self._rule(draft, held[0]).group
            log.info("held: the same %s for another %s", group.id, draft.item.id)
            confirm = self._ask_about(draft, group, chosen[group.id])
            if not set(args) - {"item_id", "draft"}:  # nothing else to set
                return {"not_set": self.actions.held(draft), **confirm}

        if self._agreed(draft, answer, latest):
            # "네" to the kiosk's own question (or "아니" with only one other choice).
            self._checking = None
            result = self.actions.call("set_options", args)
        else:
            result = self._without_guesses("set_options", args)
        if "error" in result:
            return result
        if held:
            return {**result, "not_set": self.actions.held(draft), **confirm}

        # Only what was really set (a guessed option was left out) counts as answered.
        answer = {g: ids for g, ids in answer.items() if _ids(draft, g) == ids}
        self._given += [Given(draft.id, draft.item.id, g, ids) for g, ids in answer.items()]
        if for_all:
            return result
        for g, ids in answer.items():
            other = self._maybe_also_for(draft, g, ids)
            if other is not None:
                then = str(result.get("ask", ""))
                return {
                    **result,
                    **self._ask_about(other, self._rule(draft, g).group, chosen[g], then),
                }
        return result

    def _split_rest(self, rest: Draft, chosen: Chosen, result: Result) -> Result:
        """After "두 잔만 아이스로" split some cups off: the rest get the only other choice
        ("only two iced": the others are not). Without "만" ("두 잔은 아이스로") the rest are
        asked, as "나머지는…" may follow."""
        if "error" in result or rest not in self.kiosk.drafts or not only_some(self._latest()):
            return result
        others = {
            g: other.id
            for g, choices in chosen.items()
            if not rest.chosen.get(g) and (other := self._rule(rest, g).other(choices))
        }
        if not others:
            return result
        log.info("the rest of %s: %s", rest.item.id, others)
        return self.actions.call("set_options", {"draft": rest.id, **others})

    def _maybe_also_for(self, draft: Draft, group_id: str, ids: Ids) -> Drink | None:
        """Another drink of this item the answer may be for too (asked about first), if any:
        one being chosen, else (an extra) the latest one already in the order."""
        rule = self._rule(draft, group_id)
        given = {(g.draft, g.group) for g in self._given}
        for other in self.kiosk.drafts:
            if (
                other.id != draft.id
                and other.item.id == draft.item.id
                and (other.id, group_id) not in given
                and rule.still_open(other, ids)
            ):
                return other
        lines = [ln for ln in self.kiosk.order.lines if ln.item.id == draft.item.id]
        lines = [ln for ln in lines if not rule.group.required and rule.still_open(ln, ids)]
        return lines[-1] if lines else None

    def _ask_about(
        self, other: Drink, group: OptionGroup, choices: tuple[OptionChoice, ...], then: str = ""
    ) -> Result:
        """The question "…도 레귤러로 해 드릴까요?", remembered so that a "네" to it counts."""
        if isinstance(other, Draft):
            self._checking = Checking(other.id, group.id, tuple(c.id for c in choices))
        other_choice = OptionRule(group).other(choices)
        return self.actions.confirm(other, group, choices, other_choice, then)

    def _agreed(self, draft: Draft, answer: dict[str, Ids], words: str) -> bool:
        """The answer is what the customer agreed to when the kiosk asked about this drink: "네"
        and that choice, or "아니" and the only other one."""
        checking = self._checking
        if checking is None or checking.draft != draft.id or checking.group not in answer:
            return False
        group = draft.item.group(checking.group)
        if group is None:
            return False
        ids = answer[checking.group]
        if is_yes(words):
            return ids == checking.ids
        other = OptionRule(group).other(tuple(c for c in group.choices if c.id in checking.ids))
        return is_no(words) and other is not None and ids == (other.id,)

    # --- change, no_more_extras, order ---------------------------------------------------------

    def _held_for_line(self, args: dict[str, Any]) -> Result | None:
        """change on an order line with the extra just given for a drink being chosen, which the
        customer did not say was for both: not done; the kiosk asks first."""
        if not self._fresh_given() or meant_for_all(self._latest()):
            return None
        try:
            number = int(float(args.get("line", 0)))
            line = self.kiosk.order.line(number)
            chosen = self.kiosk.menu.resolve(line.item, selection_from_args(self.kiosk.menu, args))
        except (KioskError, TypeError, ValueError):
            return None
        for g, choices in chosen.items():
            group = line.item.group(g)
            ids = tuple(c.id for c in choices)
            same = any((x.item_id, x.group, x.ids) == (line.item.id, g, ids) for x in self._given)
            if group is not None and not group.required and same:
                log.info("held: the same %s for line %d", g, number)
                return {"not_set": self.actions.held(line), **self._ask_about(line, group, choices)}
        return None

    def _extras_answered(self) -> bool:
        """The customer answered the extras question: they spoke after it was asked, or said
        before that they want nothing added ("레귤러로, 추가는 없어요")."""
        if self.kiosk.question.kind is not Ask.EXTRAS:
            return True  # the domain explains any mistake
        if self.transcript.customer_since(self._question_mark):
            return True
        return wants_nothing_more(self._latest())

    def _without_guesses(self, name: str, args: dict[str, Any]) -> Result:
        """Run order / set_options without required options the customer never mentioned
        (unless the screen asks for that option and the customer spoke since: then any answer
        is taken)."""
        try:
            if name == "order":
                item = self.kiosk.menu.item(str(args.get("item_id", "")))
            else:
                item = self._draft(args).item
        except (KioskError, TypeError, ValueError):
            return self.actions.call(name, args)  # the domain explains the mistake
        question = self.kiosk.question
        answered = bool(self.transcript.customer_since(self._question_mark))
        asked = question.group if question.item_id == item.id and answered else ""
        selection = selection_from_args(self.kiosk.menu, args)
        guessed = guessed_groups(item, selection, self._latest(), asked)
        for group in guessed:
            args.pop(group.id, None)
        result = self.actions.call(name, args)
        if guessed and "error" not in result:
            names = ", ".join(g.name for g in guessed)
            log.info("guessed %s left out for %s", names, item.id)
            result["not_said"] = NOT_SAID.format(groups=names)
        return result

    # --- helpers ---------------------------------------------------------------------------------

    def _draft(self, args: dict[str, Any]) -> Draft:
        draft = args.get("draft")
        return self.kiosk.find_draft(
            args.get("item_id") or None,
            selection_from_args(self.kiosk.menu, args),
            int(float(draft)) if draft else None,
        )

    def _rule(self, draft: Draft, group_id: str) -> OptionRule:
        group = draft.item.group(group_id)
        if group is None:
            raise KioskError(f"{draft.item.id} has no {group_id}")
        return OptionRule(group)

    def _latest(self) -> str:
        latest = self.transcript.last_customer()
        return latest.text if latest else ""

    def _fresh_given(self) -> bool:
        """`_given` is about the customer's latest words (it starts over when they speak)."""
        if self._given_mark != self.transcript.mark:
            self._given, self._given_mark = [], self.transcript.mark
        return bool(self._given)

    def _given_elsewhere(self, draft: Draft, group_id: str, ids: Ids) -> bool:
        self._fresh_given()
        return any(
            (g.item_id, g.group, g.ids) == (draft.item.id, group_id, ids) and g.draft != draft.id
            for g in self._given
        )


def _chosen(drink: Drink) -> Chosen:
    return drink.chosen() if isinstance(drink, CartLine) else drink.chosen


def _ids(drink: Drink, group_id: str) -> Ids:
    return tuple(c.id for c in _chosen(drink).get(group_id, ()))
