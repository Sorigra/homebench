"""Orchestrate "make sure only this model is loaded, with these parameters".

Headless (AD-005): the only import outside this package is the repo's shared
``ProviderError``. User interaction enters through an injected ``Confirmer``
callable, never through ``input()``.

``plan()`` is deliberately separate from ``ensure_only()`` (TD-03): the decision
becomes inspectable data, testable without I/O, and showable to the user before
anything is unloaded.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional

from ..providers.base import ProviderError
from .models import LifecycleOutcome, LifecyclePlan, LoadParams

#: Asked to approve a plan before anything is unloaded. The CLI passes a Rich
#: prompt, the future web API passes its own, tests pass a lambda (TD-04).
Confirmer = Callable[[LifecyclePlan], bool]


def _is_sublist(needle: List[str], haystack: List[str]) -> bool:
    """True when ``needle`` appears as a contiguous run inside ``haystack``."""
    n = len(needle)
    if n == 0:
        return True
    return any(haystack[i:i + n] == needle for i in range(len(haystack) - n + 1))


#: Long form for every short llama.cpp flag we may send, so a router that
#: reports the resolved argv in long form is not mistaken for one that dropped
#: the request.
_LONG_FORM = {
    "-ngl": "--n-gpu-layers", "-c": "--ctx-size", "-np": "--parallel",
    "-fa": "--flash-attn", "-ctk": "--cache-type-k", "-ctv": "--cache-type-v",
    "-b": "--batch-size", "-ub": "--ubatch-size", "-m": "--model",
}


def _missing_args(requested: List[str], resolved: List[str]) -> List[str]:
    """Requested flags whose value did not survive into the resolved argv.

    Some router builds accept ``extra_args`` on ``POST /models/load``, answer
    ``{"success": true}``, and then load the model from the preset alone --
    silently. The caller would otherwise record a measurement under parameters
    that were never applied, which is worse than an error.

    Only flag/value pairs are checked; a bare flag has no value to verify.
    """
    resolved = list(resolved or [])
    missing: List[str] = []
    req = list(requested or [])
    for i, token in enumerate(req):
        if not token.startswith("-") or i + 1 >= len(req):
            continue
        value = req[i + 1]
        if value.startswith("-"):
            continue
        names = {token, _LONG_FORM.get(token, token)}
        names |= {k for k, v in _LONG_FORM.items() if v == token}
        applied = any(
            resolved[j] in names and j + 1 < len(resolved) and resolved[j + 1] == value
            for j in range(len(resolved))
        )
        if not applied:
            missing.append(f"{token} {value}")
    return missing


def _args_satisfied(requested: List[str], resolved: List[str]) -> bool:
    """True when the loaded argv already carries every requested extra arg.

    The router appends ``extra_args`` verbatim to the argv it reports back in
    ``status.args``, so a contiguous match means "loaded with these parameters".
    Requesting nothing matches any argv.
    """
    return _is_sublist(list(requested or []), list(resolved or []))


class ModelLifecycleManager:
    """Decides and applies router model-state transitions for one host."""

    def __init__(self, client: Any):
        self.client = client

    # ------------------------------------------------------------------
    def plan(self, model: str, params: Optional[LoadParams] = None) -> LifecyclePlan:
        """Decide what to unload and whether to load -- without acting.

        Makes exactly one read (``GET /v1/models``) and no mutation call.
        Raises :class:`ProviderError` citing the id when the router does not
        know ``model``, so nothing is loaded for a typo (MLC-02).
        """
        params = params or LoadParams()
        states = self.client.list_models()
        target = next((m for m in states if m.id == model), None)
        if target is None:
            known = ", ".join(sorted(m.id for m in states)) or "none"
            raise ProviderError(
                f"Model {model!r} is not known to the router at "
                f"{getattr(self.client, 'host', '?')} (available: {known})"
            )

        # MLC-03: every other resident model contends for VRAM, so all of them go.
        to_unload = [m.id for m in states if m.id != model and m.status == "loaded"]
        satisfied = _args_satisfied(params.extra_args, target.args)

        if target.status == "loaded" and satisfied:
            # MLC-04: no unload-and-reload of the target itself.
            needs_load = False
            reason = f"{model} is already loaded with the requested parameters"
        elif target.status == "loaded":
            needs_load = True
            to_unload = to_unload + [model]
            reason = f"{model} is loaded with different parameters and will be reloaded"
        elif target.status == "loading":
            needs_load = False
            reason = f"{model} is already loading; waiting for it to become loaded"
        else:
            needs_load = True
            reason = f"{model} is not loaded and will be loaded"

        if to_unload:
            reason += "; unloading " + ", ".join(to_unload) + " first"
        return LifecyclePlan(
            target=model,
            to_unload=to_unload,
            needs_load=needs_load,
            reason=reason,
        )

    # ------------------------------------------------------------------
    def ensure_only(
        self,
        model: str,
        params: LoadParams,
        confirm: Confirmer,
    ) -> LifecycleOutcome:
        """Apply :meth:`plan` so that ``model`` is the only resident model.

        ``confirm`` is asked once, with the plan, before anything is unloaded,
        and only when there is something to unload. Returning False aborts:
        nothing is unloaded, nothing is loaded, and the outcome is flagged
        ``aborted`` so the caller does not benchmark (MLC-08).

        A load that fails or times out raises :class:`ProviderError`; the
        target is unloaded first so the module never leaves a half-loaded
        model behind (MLC-06).
        """
        plan = self.plan(model, params)

        if plan.to_unload and not confirm(plan):
            return LifecycleOutcome(plan=plan, aborted=True)

        for victim in plan.to_unload:
            self.client.unload(victim)

        if plan.needs_load:
            if plan.to_unload:
                # The unloads above have been accepted but the router stops the
                # instances asynchronously (MLC-15). Two distinct refusals come
                # from loading too early: reloading the same model gets "model
                # is already running", and loading a different one gets "model
                # limit reached". The first needs those instances to be really
                # gone; the second only needs a free slot.
                self._wait_unloaded(plan.to_unload)
                self._wait_for_capacity()
            self.client.load(model, list(params.extra_args) or None)
        try:
            self.client.wait_until_loaded(model)
        except ProviderError:
            if plan.needs_load:
                self._best_effort_unload(model)
            raise

        effective = self._effective_args(model)
        return LifecycleOutcome(
            plan=plan,
            effective_args=effective,
            unloaded=list(plan.to_unload),
            ignored_args=_missing_args(params.extra_args, effective),
        )

    # ------------------------------------------------------------------
    def _effective_args(self, model: str) -> List[str]:
        """The argv the router resolved for ``model`` after loading (MLC-09)."""
        state = next((m for m in self.client.list_models() if m.id == model), None)
        return list(state.args) if state is not None else []

    def _wait_unloaded(self, models: List[str]) -> None:
        """Let the router actually stop the instances we just unloaded."""
        waiter = getattr(self.client, "wait_until_unloaded", None)
        if waiter is not None:
            waiter(list(models))

    def _wait_for_capacity(self) -> None:
        """Let the router free the slots we just unloaded, when it can say so.

        Guarded by ``getattr`` because the manager is written against any
        client that speaks the protocol, and older ones have no such method.
        """
        waiter = getattr(self.client, "wait_for_capacity", None)
        if waiter is not None:
            waiter()

    def _best_effort_unload(self, model: str) -> None:
        try:
            self.client.unload(model)
        except ProviderError:
            pass
