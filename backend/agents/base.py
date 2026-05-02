from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar


OutputT = TypeVar("OutputT")


class Agent(ABC, Generic[OutputT]):
    name: str
    prompt: str

    @abstractmethod
    def run(self, *args, **kwargs) -> OutputT:
        raise NotImplementedError


def confidence_label(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def numbered_lines(text: str) -> list[tuple[int, str]]:
    return [(index, line) for index, line in enumerate(text.splitlines(), start=1)]


def window(lines: list[tuple[int, str]], line_number: int, radius: int = 1) -> str:
    start = max(1, line_number - radius)
    end = line_number + radius
    return "\n".join(line for number, line in lines if start <= number <= end)
