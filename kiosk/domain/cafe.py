"""Information about the cafe (hours, Wi-Fi, restroom, ...), as loaded from `data/cafe.yaml`."""

from __future__ import annotations

from dataclasses import dataclass

from kiosk.domain.menu import KioskError


@dataclass(frozen=True)
class InfoTopic:
    id: str
    title: str
    text: str
    verified: bool = False


@dataclass(frozen=True)
class Cafe:
    name: str
    topics: tuple[InfoTopic, ...] = ()
    verified: bool = False

    def topic(self, topic_id: str) -> InfoTopic:
        for topic in self.topics:
            if topic.id == topic_id:
                return topic
        valid = ", ".join(t.id for t in self.topics)
        raise KioskError(f"there is no cafe info topic {topic_id!r} (valid: {valid})")
