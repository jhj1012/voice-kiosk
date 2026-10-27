"""What differs between kinds of options (answers.OptionRule). The conversations are in
tests/test_conversation_rules.py."""

from kiosk.assistant.answers import OptionRule
from kiosk.domain.flow import Kiosk


def rule(menu, item_id: str, group_id: str) -> OptionRule:
    group = menu.item(item_id).group(group_id)
    assert group is not None
    return OptionRule(group)


def choice(menu, item_id: str, group_id: str, choice_id: str):
    return next(c for c in menu.item(item_id).group(group_id).choices if c.id == choice_id)


def test_no_means_the_other_of_two_choices(menu):
    size = rule(menu, "americano", "size")
    assert size.other((choice(menu, "americano", "size", "large"),)).id == "regular"
    temperature = rule(menu, "americano", "temperature")
    assert temperature.other((choice(menu, "americano", "temperature", "hot"),)).id == "ice"
    shot = rule(menu, "americano", "shot")  # an extra: "아니" means it does not get it
    assert shot.other((choice(menu, "americano", "shot", "extra_shot"),)) is None


def test_what_counts_as_an_answer(menu):
    shot = rule(menu, "americano", "shot")
    assert shot.counts((choice(menu, "americano", "shot", "extra_shot"),))
    assert not shot.counts((choice(menu, "americano", "shot", "none"),))  # "기본"
    size = rule(menu, "americano", "size")
    assert size.counts((choice(menu, "americano", "size", "regular"),))


def test_which_drinks_may_want_it_too(kiosk: Kiosk, menu):
    kiosk.order_item("americano", 1, {"temperature": "ice"})
    # A second americano is not asked about extras: complete, it goes into the order at once.
    kiosk.order_item("americano", 1, {"temperature": "hot", "size": "regular"})
    (iced,) = kiosk.drafts
    (line,) = kiosk.order.lines
    size = rule(menu, "americano", "size")
    assert size.still_open(iced, ("regular",))  # still missing a size
    assert not size.still_open(line, ("regular",))  # an order line has its size
    shot = rule(menu, "americano", "shot")
    assert shot.still_open(iced, ("extra_shot",))  # asked about extras, without the shot
    assert shot.still_open(line, ("extra_shot",))  # in the order, may want it too
