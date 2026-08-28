"""ModelLifecycleManager - planning and executing router state transitions.

Offline: the router client is faked, so no HTTP happens at all.
Requirements exercised: MLC-01 (state integrity), MLC-02 (unknown model),
MLC-03 (unload every other resident), MLC-04 (already-loaded no-op).
"""

import pytest

from homebench.lifecycle.manager import ModelLifecycleManager
from homebench.lifecycle.models import LoadParams, ModelState
from homebench.providers.base import ProviderError

HOST = "http://router.test"


def _state(model_id, status, extra=()):
    args = ["/app/llama-server", "-m", "/models/%s.gguf" % model_id] + list(extra)
    return ModelState(id=model_id, status=status, args=args, source="models_dir")


class FakeRouter:
    """Stand-in for LlamaRouterClient.

    Mutations raise unless ``allow_mutations`` is set, which is how the
    "``plan()`` has no side effects" requirement is proved.
    """

    host = HOST

    def __init__(self, states, allow_mutations=False,
                 load_error=None, wait_error=None):
        self._states = list(states)
        self.allow_mutations = allow_mutations
        self.load_error = load_error
        self.wait_error = wait_error
        self.calls = []

    def _find(self, model):
        return next((m for m in self._states if m.id == model), None)

    def list_models(self):
        self.calls.append(("list_models",))
        return list(self._states)

    def loaded_models(self):
        return [m for m in self._states if m.status == "loaded"]

    def load(self, model, extra_args=None):
        if not self.allow_mutations:
            raise AssertionError("plan() must not call load()")
        self.calls.append(("load", model, list(extra_args or [])))
        if self.load_error is not None:
            raise self.load_error
        state = self._find(model)
        state.status = "loaded"
        state.args = state.args + list(extra_args or [])

    def unload(self, model):
        if not self.allow_mutations:
            raise AssertionError("plan() must not call unload()")
        self.calls.append(("unload", model))
        state = self._find(model)
        if state is not None:
            state.status = "unloaded"

    def wait_until_loaded(self, model, timeout=300.0):
        self.calls.append(("wait", model))
        if self.wait_error is not None:
            raise self.wait_error
        state = self._find(model)
        if state is None or state.status != "loaded":
            raise ProviderError("timed out waiting for %r to load" % model)


def _mutable(states, **kw):
    return FakeRouter(states, allow_mutations=True, **kw)


def _kinds(router):
    return [c[0] for c in router.calls]


# =====================================================================
# T9: plan() decides without acting
# =====================================================================
def test_plan_makes_no_mutation_calls():
    router = FakeRouter([_state("target", "unloaded"), _state("other", "loaded")])
    ModelLifecycleManager(router).plan("target", LoadParams())
    assert [c[0] for c in router.calls] == ["list_models"]


def test_plan_unloads_every_other_resident_model():
    router = FakeRouter([
        _state("target", "unloaded"),
        _state("resident-a", "loaded"),
        _state("resident-b", "loaded"),
        _state("idle", "unloaded"),
    ])
    plan = ModelLifecycleManager(router).plan("target", LoadParams())
    assert sorted(plan.to_unload) == ["resident-a", "resident-b"]
    assert plan.needs_load is True


def test_plan_is_noop_when_target_already_loaded_with_same_params():
    router = FakeRouter([_state("target", "loaded", ["-ngl", "99"])])
    plan = ModelLifecycleManager(router).plan(
        "target", LoadParams(extra_args=["-ngl", "99"], origin="explicit")
    )
    assert plan.needs_load is False
    assert plan.to_unload == []
    assert plan.target == "target"


def test_plan_keeps_loaded_target_but_still_unloads_others():
    router = FakeRouter([
        _state("target", "loaded", ["-ngl", "99"]),
        _state("resident", "loaded"),
    ])
    plan = ModelLifecycleManager(router).plan(
        "target", LoadParams(extra_args=["-ngl", "99"])
    )
    assert plan.needs_load is False
    assert plan.to_unload == ["resident"]  # MLC-03: the target is not in it


def test_plan_reloads_target_when_params_differ():
    router = FakeRouter([_state("target", "loaded", ["-ngl", "99"])])
    plan = ModelLifecycleManager(router).plan(
        "target", LoadParams(extra_args=["-ngl", "20"], origin="explicit")
    )
    assert plan.needs_load is True
    assert plan.to_unload == ["target"]


def test_plan_loads_unloaded_target():
    router = FakeRouter([_state("target", "unloaded")])
    plan = ModelLifecycleManager(router).plan("target", LoadParams())
    assert plan.needs_load is True
    assert plan.to_unload == []


def test_plan_waits_instead_of_reloading_a_loading_target():
    router = FakeRouter([_state("target", "loading")])
    plan = ModelLifecycleManager(router).plan("target", LoadParams())
    assert plan.needs_load is False
    assert "loading" in plan.reason


def test_plan_unknown_model_raises_providererror_citing_the_id():
    router = FakeRouter([_state("real", "unloaded")])
    with pytest.raises(ProviderError) as exc:
        ModelLifecycleManager(router).plan("ghost", LoadParams())
    assert "ghost" in str(exc.value)


def test_plan_unknown_model_does_not_mutate_anything():
    router = FakeRouter([_state("real", "loaded")])
    with pytest.raises(ProviderError):
        ModelLifecycleManager(router).plan("ghost", LoadParams())
    assert [c[0] for c in router.calls] == ["list_models"]


def test_plan_reason_names_the_target_and_every_model_it_unloads():
    router = FakeRouter([
        _state("target", "unloaded"),
        _state("resident-a", "loaded"),
        _state("resident-b", "loaded"),
    ])
    plan = ModelLifecycleManager(router).plan("target", LoadParams())
    assert "target" in plan.reason
    assert "resident-a" in plan.reason and "resident-b" in plan.reason
    assert len(plan.reason.split()) >= 5  # a sentence, not a code


# =====================================================================
# T10: ensure_only() executes the plan behind an injected confirmation
# =====================================================================
def test_ensure_only_asks_confirmation_with_the_plan_before_unloading():
    router = _mutable([_state("target", "unloaded"), _state("resident", "loaded")])
    seen = []

    def confirm(plan):
        # asked before anything was unloaded
        assert "unload" not in _kinds(router)
        seen.append(plan)
        return True

    ModelLifecycleManager(router).ensure_only("target", LoadParams(), confirm)
    assert len(seen) == 1
    assert seen[0].to_unload == ["resident"]


def test_ensure_only_refusal_unloads_nothing_and_loads_nothing():
    router = _mutable([_state("target", "unloaded"), _state("resident", "loaded")])
    outcome = ModelLifecycleManager(router).ensure_only(
        "target", LoadParams(), lambda plan: False
    )
    assert outcome.aborted is True
    assert "unload" not in _kinds(router)
    assert "load" not in _kinds(router)
    assert outcome.unloaded == []


def test_ensure_only_does_not_confirm_when_nothing_will_be_unloaded():
    router = _mutable([_state("target", "unloaded")])
    asked = []
    ModelLifecycleManager(router).ensure_only(
        "target", LoadParams(), lambda plan: asked.append(plan) or True
    )
    assert asked == []
    assert ("load", "target", []) in router.calls


def test_ensure_only_unloads_every_resident_then_loads_the_target():
    router = _mutable([
        _state("target", "unloaded"),
        _state("resident-a", "loaded"),
        _state("resident-b", "loaded"),
    ])
    outcome = ModelLifecycleManager(router).ensure_only(
        "target", LoadParams(extra_args=["-ngl", "20"]), lambda plan: True
    )
    unloaded = [c[1] for c in router.calls if c[0] == "unload"]
    assert unloaded == ["resident-a", "resident-b"]
    assert ("load", "target", ["-ngl", "20"]) in router.calls
    # the load happened after both unloads
    assert _kinds(router).index("load") > max(
        i for i, k in enumerate(_kinds(router)) if k == "unload"
    )
    assert outcome.unloaded == ["resident-a", "resident-b"]
    assert outcome.aborted is False


def test_ensure_only_never_calls_input(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("lifecycle must stay headless: no input()")

    monkeypatch.setattr("builtins.input", boom)
    router = _mutable([_state("target", "unloaded"), _state("resident", "loaded")])
    outcome = ModelLifecycleManager(router).ensure_only(
        "target", LoadParams(), lambda plan: True
    )
    assert outcome.aborted is False


def test_ensure_only_reports_the_effective_args_after_loading():
    router = _mutable([_state("target", "unloaded")])
    outcome = ModelLifecycleManager(router).ensure_only(
        "target", LoadParams(extra_args=["-ngl", "20"], origin="explicit"),
        lambda plan: True,
    )
    assert outcome.effective_args == [
        "/app/llama-server", "-m", "/models/target.gguf", "-ngl", "20",
    ]


def test_ensure_only_skips_the_load_when_already_loaded_with_same_params():
    router = _mutable([_state("target", "loaded", ["-ngl", "99"])])
    outcome = ModelLifecycleManager(router).ensure_only(
        "target", LoadParams(extra_args=["-ngl", "99"]), lambda plan: True
    )
    assert "load" not in _kinds(router)
    assert outcome.aborted is False
    assert outcome.effective_args[-2:] == ["-ngl", "99"]


def test_ensure_only_propagates_a_failed_load():
    router = _mutable([_state("target", "unloaded")],
                      load_error=ProviderError("router refused: bad flag -zzz"))
    with pytest.raises(ProviderError) as exc:
        ModelLifecycleManager(router).ensure_only(
            "target", LoadParams(extra_args=["-zzz"]), lambda plan: True
        )
    assert "bad flag -zzz" in str(exc.value)


def test_ensure_only_unloads_the_target_when_the_load_times_out():
    router = _mutable([_state("target", "unloaded")],
                      wait_error=ProviderError("Timed out after 300s"))
    with pytest.raises(ProviderError) as exc:
        ModelLifecycleManager(router).ensure_only(
            "target", LoadParams(), lambda plan: True
        )
    assert "Timed out" in str(exc.value)
    # no half-loaded model is left behind by the module (MLC-06)
    assert [c[1] for c in router.calls if c[0] == "unload"] == ["target"]


def test_ensure_only_waits_for_a_target_that_is_already_loading():
    router = _mutable([_state("target", "loading")])
    with pytest.raises(ProviderError):
        # the fake's wait fails while the model is still "loading"
        ModelLifecycleManager(router).ensure_only(
            "target", LoadParams(), lambda plan: True
        )
    assert "wait" in _kinds(router)
    assert "load" not in _kinds(router)  # no redundant load POST
