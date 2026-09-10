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

    def to_dict(self) -> dict:
        return {
            "model_ids": list(self.model_ids),
            "depths": list(self.depths),
            "run_speed": self.run_speed,
            "run_quality": self.run_quality,
        }

    @classmethod
    def from_dict(cls, data: dict) -> RunPlan:
        return cls(
            model_ids=list(data.get("model_ids") or []),
            depths=list(data.get("depths") or []),
            run_speed=bool(data.get("run_speed", True)),
            run_quality=bool(data.get("run_quality", False)),
        )

    @classmethod
    def restore(cls, saved: dict, available_ids: List[str]) -> RunPlan:
        allowed = set(available_ids)
        model_ids = [mid for mid in saved.get("model_ids") or [] if mid in allowed]
        return cls.from_dict({**saved, "model_ids": model_ids})
