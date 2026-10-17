"""Calendar-validated date mentions shared by routing and version guidance."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date


DATE_PATTERN = re.compile(
    r"(?<!\d)(?:"
    r"(?P<jy>\d{4})年(?P<jm>\d{1,2})月(?:(?P<jd>\d{1,2})日)?"
    r"|(?P<ny>\d{4})(?P<sep>[-/])(?P<nm>\d{1,2})(?P=sep)(?P<nd>\d{1,2})(?!\d)"
    r")"
)


@dataclass(frozen=True)
class QuestionDate:
    text: str
    start: int
    end: int
    value: date | None
    has_day: bool


def question_dates(question: str) -> tuple[QuestionDate, ...]:
    mentions = []
    for match in DATE_PATTERN.finditer(question):
        year = match.group("jy") or match.group("ny")
        month = match.group("jm") or match.group("nm")
        day = match.group("jd") or match.group("nd")
        try:
            value = date(int(year), int(month), int(day or 1))
        except ValueError:
            value = None
        mentions.append(
            QuestionDate(match.group(), match.start(), match.end(), value, day is not None)
        )
    return tuple(mentions)


def has_other_date_mentions(question: str, mentions: tuple[QuestionDate, ...]) -> bool:
    """Do not mistake an omitted year or era date for one unique reference date."""
    remainder = list(question)
    for mention in mentions:
        remainder[mention.start:mention.end] = " " * (mention.end - mention.start)
    return bool(re.search(
        r"\d{1,2}月\d{1,2}日|(?<!\d)\d{1,2}[/-]\d{1,2}(?!\d)|"
        r"(?:令和|平成|昭和)(?:元|\d+)年",
        "".join(remainder),
    ))
