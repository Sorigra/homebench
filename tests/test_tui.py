import asyncio

from textual.widgets import DataTable

from homebench.runner import RunConfig, Runner
from homebench.tui.app import HomebenchApp
from tests.fakes import FakeProvider


async def _run_to_completion(app):
    async with app.run_test() as pilot:
        for _ in range(200):
            if app.result is not None:
                break
            await pilot.pause(0.05)
        assert app.result is not None, "benchmark did not finish"
        return app.query_one("#board", DataTable)


def test_tui_runs_and_fills_leaderboard():
    provider = FakeProvider()
    # Default depths=[0, 8192, 32768]: each model measures 3 points, so the
    # finished leaderboard has one row per (model, depth) -- 6, not 2 (T15).
    runner = Runner(provider, RunConfig(sample_rss=False))
    models = provider.list_models()

    async def scenario():
        app = HomebenchApp(runner, models)
        table = await _run_to_completion(app)
        assert table.row_count == 6
        assert len(app.result.reports) == 2

    asyncio.run(scenario())


def test_tui_leaderboard_has_depth_prefill_decode_columns():
    provider = FakeProvider()
    runner = Runner(provider, RunConfig(sample_rss=False, depths=[0]))
    models = provider.list_models()

    async def scenario():
        app = HomebenchApp(runner, models)
        table = await _run_to_completion(app)
        headers = [str(col.label) for col in table.columns.values()]
        assert "Depth" in headers
        assert "Prefill tok/s" in headers
        assert "Decode tok/s" in headers
        assert "tok/s" not in headers
        assert table.row_count == 2   # depths=[0]: one row per model

    asyncio.run(scenario())


def test_tui_leaderboard_cells_are_filled_with_measured_values():
    from textual.coordinate import Coordinate

    provider = FakeProvider()
    runner = Runner(provider, RunConfig(sample_rss=False, depths=[0]))
    models = provider.list_models()

    async def scenario():
        app = HomebenchApp(runner, models)
        table = await _run_to_completion(app)
        # Column order from on_mount: Model, Status, Quality, Pass, Depth,
        # Prefill tok/s, Decode tok/s, TTFT, Memory, Peak.
        decode_col, depth_col = 6, 4
        decode_cells = [str(table.get_cell_at(Coordinate(r, decode_col)))
                        for r in range(table.row_count)]
        depth_cells = [str(table.get_cell_at(Coordinate(r, depth_col)))
                       for r in range(table.row_count)]
        # FakeProvider's canned decode rates (120.0 tok/s, 40.0 tok/s) --
        # actually filled in, not left as the placeholder "-".
        assert any("120.0" in c for c in decode_cells)
        assert any("40.0" in c for c in decode_cells)
        assert all(c != "–" for c in depth_cells)   # depth column is filled too

    asyncio.run(scenario())
