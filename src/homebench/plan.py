"""Validatable benchmark run plans without TUI dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

DEPTH_CHOICES = (0, 8192, 32768)


@dataclass
class RunPlan:
    model_ids: List[str]
    depths: List[int]
    run_speed: bool = True
    run_quality: bool = False

    def __post_init__(self) -> None:
        allowed = set(DEPTH_CHOICES)
        self.depths = sorted({d for d in self.depths if d in allowed})

    def problems(self) -> List[str]:
        problems: List[str] = []
        if not self.model_ids:
            problems.append("select at least one model")
        if not self.depths:
            problems.append("select at least one depth")
        if not self.run_speed and not self.run_quality:
            problems.append("select at least one test type")
        return problems
