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

    def __init__(self, states, allow_mutations=False):
        self._states = list(states)
        self.allow_mutations = allow_mutations
        self.calls = []

    def list_models(self):
        self.calls.append(("list_models",))
        return list(self._states)

    def loaded_models(self):
        return [m for m in self._states if m.status == "loaded"]

    def load(self, model, extra_args=None):
        if not self.allow_mutations:
            raise AssertionError("plan() must not call load()")
        self.calls.append(("load", model, list(extra_args or [])))

    def unload(self, model):
        if not self.allow_mutations:
            raise AssertionError("plan() must not call unload()")
        self.calls.append(("unload", model))


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
