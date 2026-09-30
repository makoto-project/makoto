from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "scripts" / "demo.sh"


def _run_acceptance(script: Path) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["bash", str(script), "--acceptance"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    stdout = re.sub(
        r"^ACCEPTANCE_ELAPSED_SECONDS .+$",
        "ACCEPTANCE_ELAPSED_SECONDS <elapsed>",
        completed.stdout,
        flags=re.MULTILINE,
    )
    return completed.returncode, stdout, completed.stderr


def test_demo_entrypoint_runs_acceptance() -> None:
    assert DEMO.is_file()
    assert os.access(DEMO, os.X_OK)

    returncode, stdout, stderr = _run_acceptance(DEMO)
    assert returncode == 0, stderr
    assert "positive: ALLOW (all checks pass)" in stdout
