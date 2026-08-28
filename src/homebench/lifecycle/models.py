"""Dataclasses for the llama.cpp router lifecycle module.

Plain, JSON-serialisable dataclasses mirroring the router's HTTP contract.
``from_dict`` tolerates unknown keys so a newer router build does not break
parsing (same spirit as ``homebench.models._pick``).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List


def _pick(cls, d: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only keys that are constructor fields of ``cls`` (ignore extras)."""
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in (d or {}).items() if k in names}


#: The only model states the router reports; anything else is treated as unloaded.
VALID_STATUS = ("loaded", "loading", "unloaded")


@dataclass
class RouterInfo:
    """Result of ``GET /props`` on a llama.cpp router."""

    role: str = ""                   # "router" when talking to a router
    max_instances: int = 0           # mirrors --models-max
    models_autoload: bool = False
    build_info: str = ""             # differs per host; recorded with the result

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RouterInfo":
        return cls(**_pick(cls, d))


@dataclass
class ModelState:
    """One entry of ``GET /v1/models`` on a router."""

    id: str = ""
    status: str = "unloaded"         # loaded | loading | unloaded
    args: List[str] = field(default_factory=list)   # argv resolved by the server
    preset: str = ""
    source: str = ""                 # e.g. "models_dir" | "preset"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ModelState":
        d = d or {}
        status_obj = d.get("status")
        if isinstance(status_obj, dict):
            raw_status = status_obj.get("value", "")
            args = status_obj.get("args", [])
            preset = status_obj.get("preset", "")
        else:
            raw_status = status_obj if isinstance(status_obj, str) else ""
            args = d.get("args", [])
            preset = d.get("preset", "")
        status = raw_status if raw_status in VALID_STATUS else "unloaded"
        return cls(
            id=d.get("id", "") or "",
            status=status,
            args=list(args or []),
            preset=preset or "",
            source=d.get("source", "") or "",
        )


@dataclass
class LoadParams:
    """Resolved load parameters for a model, plus which source won."""

    extra_args: List[str] = field(default_factory=list)
    origin: str = "default"          # explicit | json | preset | heuristic | default

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LoadParams":
        return cls(**_pick(cls, d))


@dataclass
class LifecyclePlan:
    """What ``ensure_only`` would do, decided without acting."""

    target: str = ""
    to_unload: List[str] = field(default_factory=list)
    needs_load: bool = True
    reason: str = ""                 # human-readable: why this plan

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LifecyclePlan":
        return cls(**_pick(cls, d))


@dataclass
class LifecycleOutcome:
    """The executed plan plus the effective post-load argv (feeds MLC-09)."""

    plan: LifecyclePlan = field(default_factory=LifecyclePlan)
    effective_args: List[str] = field(default_factory=list)
    unloaded: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "effective_args": list(self.effective_args),
            "unloaded": list(self.unloaded),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LifecycleOutcome":
        d = d or {}
        return cls(
            plan=LifecyclePlan.from_dict(d.get("plan", {})),
            effective_args=list(d.get("effective_args", []) or []),
            unloaded=list(d.get("unloaded", []) or []),
        )
