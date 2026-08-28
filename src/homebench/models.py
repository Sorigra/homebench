"""Data models shared across homebench.

Everything the runner produces is a plain dataclass so results serialize
cleanly to JSON and are trivial to test.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Optional


def _pick(cls, d: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only keys that are constructor fields of ``cls`` (ignore extras)."""
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in (d or {}).items() if k in names}


@dataclass
class ModelInfo:
    """A model discovered from a provider."""

    name: str
    provider: str
    size_bytes: int = 0
    parameter_size: str = ""
    quantization: str = ""
    family: str = ""
    digest: str = ""            # provider content hash; identifies a model version

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ModelInfo":
        return cls(**_pick(cls, d))

    @property
    def cache_id(self) -> str:
        """Stable identity for caching (digest if available, else name+size)."""
        return self.digest or f"{self.name}:{self.size_bytes}"


@dataclass
class SpeedMetrics:
    """Timing for a single generation.

    Durations are seconds. ``tokens_per_sec`` is the pure generation rate
    (output tokens / eval time), which is the number people quote for local
    models and excludes prompt processing and model-load time.
    """

    ttft_s: float = 0.0            # time to first token (wall clock)
    tokens_per_sec: float = 0.0    # output eval rate
    prompt_tokens: int = 0
    output_tokens: int = 0
    prompt_eval_s: float = 0.0
    eval_s: float = 0.0
    load_s: float = 0.0            # model load time (excluded from other metrics)
    total_s: float = 0.0           # wall-clock request duration
    content_tokens: int = 0        # tokens streamed in delta.content
    reasoning_tokens: int = 0      # tokens streamed in delta.reasoning_content
    #: prompt-processing rate. ``None`` means "unknown" -- never 0.0, which is
    #: a valid measurement and would read as a real (very slow) prefill.
    prefill_tps: Optional[float] = None
    #: "server" when the rates came from the backend's own ``timings`` object,
    #: "client" when they were timed here from the stream.
    timings_source: str = "client"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SpeedMetrics":
        return cls(**_pick(cls, d))


@dataclass
class DepthMetrics:
    """One speed measurement at one prompt-context depth.

    ``depth_requested`` is what the sweep asked for; ``depth_actual`` is what
    the server actually processed (its ``prompt_n``), which is the number that
    gets reported -- the synthetic prompt never lands exactly on the target.
    """

    depth_requested: int
    depth_actual: int = 0
    #: prompt-processing rate. ``None`` = unknown, never 0.0.
    prefill_tps: Optional[float] = None
    decode_tps: float = 0.0
    ttft_s: float = 0.0
    prompt_eval_s: float = 0.0
    output_tokens: int = 0
    #: ``timings.cache_n``; anything above 0 means the prefill read reused KV
    cache_hit_tokens: int = 0
    #: why this depth could not be measured; ``None`` when it was
    skipped: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DepthMetrics":
        return cls(**_pick(cls, d))


@dataclass
class MemoryMetrics:
    """Memory footprint of a loaded model.

    ``size_bytes`` / ``vram_bytes`` come from the provider's view of the
    resident model. ``rss_peak_bytes`` is the peak resident-set delta we
    sampled across the provider's processes during generation (best-effort).
    """

    size_bytes: int = 0
    vram_bytes: int = 0
    rss_peak_bytes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemoryMetrics":
        return cls(**_pick(cls, d))


@dataclass
class TaskResult:
    """Outcome of one quality task for one model."""

    task_id: str
    category: str
    score: float                 # 0.0 .. 1.0
    passed: bool
    latency_s: float = 0.0
    output_tokens: int = 0
    response: str = ""
    detail: str = ""             # grader explanation / judge rationale

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TaskResult":
        return cls(**_pick(cls, d))


@dataclass
class ModelReport:
    """Everything measured for a single model in one benchmark run."""

    model: ModelInfo
    speed: SpeedMetrics = field(default_factory=SpeedMetrics)
    memory: MemoryMetrics = field(default_factory=MemoryMetrics)
    task_results: List[TaskResult] = field(default_factory=list)
    #: one point per measured context depth, in the order they were
    #: measured. Empty for runs saved before the depth sweep existed.
    depth_results: List[DepthMetrics] = field(default_factory=list)
    error: Optional[str] = None
    #: Non-fatal notes for this model (e.g. a best-effort unload that failed).
    #: The run continues; the warning is kept so it reaches the report (MLC-14).
    warnings: List[str] = field(default_factory=list)

    # ---- derived views -------------------------------------------------
    @property
    def quality_score(self) -> Optional[float]:
        """Mean task score in 0..100, or None if no tasks were graded."""
        if not self.task_results:
            return None
        return 100.0 * sum(t.score for t in self.task_results) / len(self.task_results)

    @property
    def tasks_passed(self) -> int:
        return sum(1 for t in self.task_results if t.passed)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model.to_dict(),
            "speed": self.speed.to_dict(),
            "memory": self.memory.to_dict(),
            "quality_score": self.quality_score,
            "tasks_passed": self.tasks_passed,
            "tasks_total": len(self.task_results),
            "task_results": [t.to_dict() for t in self.task_results],
            "depth_results": [d.to_dict() for d in self.depth_results],
            "error": self.error,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ModelReport":
        return cls(
            model=ModelInfo.from_dict(d.get("model", {})),
            speed=SpeedMetrics.from_dict(d.get("speed", {})),
            memory=MemoryMetrics.from_dict(d.get("memory", {})),
            task_results=[TaskResult.from_dict(t) for t in d.get("task_results", [])],
            depth_results=[DepthMetrics.from_dict(x)
                           for x in (d.get("depth_results") or [])],
            error=d.get("error"),
            warnings=list(d.get("warnings", []) or []),
        )


@dataclass
class BenchmarkResult:
    """A complete benchmark run across one or more models."""

    reports: List[ModelReport] = field(default_factory=list)
    provider: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0
    config: Dict[str, Any] = field(default_factory=dict)
    environment: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "config": self.config,
            "environment": self.environment,
            "reports": [r.to_dict() for r in self.reports],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BenchmarkResult":
        return cls(
            reports=[ModelReport.from_dict(r) for r in d.get("reports", [])],
            provider=d.get("provider", ""),
            started_at=float(d.get("started_at", 0) or 0),
            finished_at=float(d.get("finished_at", 0) or 0),
            config=d.get("config", {}) or {},
            environment=d.get("environment", {}) or {},
        )
