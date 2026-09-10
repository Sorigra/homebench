from homebench.plan import DEPTH_CHOICES, RunPlan


def test_run_plan_keeps_two_model_ids():
    plan = RunPlan(model_ids=["alpha", "beta"], depths=[0])
    assert plan.model_ids == ["alpha", "beta"]


def test_run_plan_default_is_speed_only():
    plan = RunPlan(model_ids=["alpha"], depths=[0])
    assert plan.run_speed is True
    assert plan.run_quality is False


def test_run_plan_supports_three_test_type_modes():
    speed_only = RunPlan(model_ids=["alpha"], depths=[0], run_speed=True, run_quality=False)
    quality_only = RunPlan(model_ids=["alpha"], depths=[0], run_speed=False, run_quality=True)
    both = RunPlan(model_ids=["alpha"], depths=[0], run_speed=True, run_quality=True)
    assert speed_only.problems() == []
    assert quality_only.problems() == []
    assert both.problems() == []


def test_run_plan_depths_are_sorted_unique():
    plan = RunPlan(model_ids=["alpha", "beta"], depths=[32768, 0, 8192, 0])
    assert plan.depths == [0, 8192, 32768]


def test_run_plan_problems_for_zero_models():
    plan = RunPlan(model_ids=[], depths=[0])
    assert plan.problems() != []
    assert any("model" in msg for msg in plan.problems())


def test_run_plan_problems_for_zero_depths():
    plan = RunPlan(model_ids=["alpha", "beta"], depths=[])
    assert plan.problems() != []
    assert any("depth" in msg for msg in plan.problems())


def test_run_plan_problems_for_no_test_type():
    plan = RunPlan(
        model_ids=["alpha", "beta"],
        depths=[0],
        run_speed=False,
        run_quality=False,
    )
    assert plan.problems() != []
    assert any("test type" in msg for msg in plan.problems())


def test_depth_choices_constant():
    assert DEPTH_CHOICES == (0, 8192, 32768)


def test_run_plan_to_dict_from_dict_round_trip():
    original = RunPlan(
        model_ids=["alpha", "beta"],
        depths=[8192, 0],
        run_speed=True,
        run_quality=False,
    )
    restored = RunPlan.from_dict(original.to_dict())
    assert restored.model_ids == ["alpha", "beta"]
    assert restored.depths == [0, 8192]
    assert restored.run_speed is True
    assert restored.run_quality is False


def test_run_plan_restore_keeps_two_available_ids():
    saved = RunPlan(model_ids=["alpha", "beta"], depths=[0, 8192]).to_dict()
    plan = RunPlan.restore(saved, ["alpha", "beta"])
    assert plan.model_ids == ["alpha", "beta"]


def test_run_plan_restore_drops_missing_ids():
    saved = RunPlan(model_ids=["alpha", "beta"], depths=[0]).to_dict()
    plan = RunPlan.restore(saved, ["alpha"])
    assert plan.model_ids == ["alpha"]


def test_run_plan_restore_drops_invalid_depths():
    saved = {
        "model_ids": ["alpha", "beta"],
        "depths": [0, 4096, 8192],
        "run_speed": True,
        "run_quality": False,
    }
    plan = RunPlan.restore(saved, ["alpha", "beta"])
    assert plan.depths == [0, 8192]


def test_last_plan_round_trip_via_config(monkeypatch, tmp_path):
    from homebench.config import HomebenchConfig, load, save

    home = str(tmp_path / "home")
    monkeypatch.setenv("HOMEBENCH_HOME", home)
    plan = RunPlan(
        model_ids=["alpha", "beta"],
        depths=[32768, 0],
        run_speed=True,
        run_quality=True,
    )
    save(HomebenchConfig(last_plan=plan.to_dict()))
    loaded = load()
    assert loaded.last_plan == plan.to_dict()
    restored = RunPlan.restore(loaded.last_plan, ["alpha", "beta"])
    assert restored.model_ids == ["alpha", "beta"]
    assert restored.depths == [0, 32768]

