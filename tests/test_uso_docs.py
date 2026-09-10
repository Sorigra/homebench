from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
USO_PATH = REPO_ROOT / "docs" / "USO.md"


def test_uso_leads_with_setup_and_panel():
    lines = USO_PATH.read_text(encoding="utf-8").splitlines()
    first_40 = "\n".join(lines[:40]).lower()
    assert "setup.sh" in first_40
    assert "painel" in first_40


def test_uso_throughput_appears_after_happy_path():
    lines = USO_PATH.read_text(encoding="utf-8").splitlines()
    throughput_idx = next(
        i for i, line in enumerate(lines) if "throughput" in line.lower()
    )
    assert throughput_idx >= 40
