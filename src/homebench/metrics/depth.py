"""Context-depth measurement.

Single-stream tok/s is normally measured on a near-empty prompt, which is the
one context nobody actually works in: the same model loses roughly a quarter
of its decode rate and a third of its prefill rate by 32k tokens. This module
sweeps a model across several prompt depths in one run so the degradation is
visible instead of implied.

Nothing here talks to a backend directly -- the provider and the tokenizer are
injected -- so the sweep stays testable without a network.
"""

from __future__ import annotations

from typing import List


def parse_depths(spec: str) -> List[int]:
    """Parse a depth spec like '0,8192,32768' into a list of prompt depths.

    Unlike :func:`~homebench.metrics.throughput.parse_levels` this keeps the
    order the user gave and does not deduplicate: the sweep measures exactly
    what was asked for, in that order. An empty spec means depth 0, the
    behaviour homebench had before the sweep existed.

    Raises ``ValueError`` naming the offending value for anything that is not
    a non-negative integer.
    """
    depths: List[int] = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            value = int(part)
        except ValueError:
            raise ValueError(f"invalid context depth {part!r}")
        if value < 0:
            raise ValueError(f"invalid context depth {part!r}: must not be negative")
        depths.append(value)
    return depths or [0]
