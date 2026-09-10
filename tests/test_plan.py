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
