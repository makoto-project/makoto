from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONLESS_DEMO = ROOT / "scripts" / "demo.sh"
VERSIONED_DEMO = ROOT / "scripts" / "demo-v0.2.sh"


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


def test_demo_entrypoints_have_identical_acceptance_behavior() -> None:
    assert VERSIONLESS_DEMO.is_file()
    assert VERSIONED_DEMO.is_file()
    assert os.access(VERSIONLESS_DEMO, os.X_OK)
    assert os.access(VERSIONED_DEMO, os.X_OK)

    assert _run_acceptance(VERSIONLESS_DEMO) == _run_acceptance(VERSIONED_DEMO)
