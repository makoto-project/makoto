from __future__ import annotations

from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from makoto.schema import strict_json_loads

ROOT = Path(__file__).resolve().parents[1]
INTERNAL = ROOT / "src" / "makoto" / "internal-schemas"


def _validator(name: str) -> Draft202012Validator:
    value = strict_json_loads((INTERNAL / name).read_bytes())
    assert isinstance(value, dict)
    Draft202012Validator.check_schema(value)
    return Draft202012Validator(value)


def test_profile_worker_result_contract() -> None:
    validator = _validator("profile-worker-result.schema.json")
    validator.validate(
        {
            "diagnostic": None,
            "evaluationsConsumed": 1,
            "phase": "complete",
            "status": "pass",
            "tokenCount": 0,
        }
    )
    with pytest.raises(ValidationError):
        validator.validate(
            {
                "diagnostic": None,
                "evaluationsConsumed": 1,
                "phase": "complete",
                "status": "invalid",
                "tokenCount": 0,
            }
        )


def test_dataset_worker_result_contract() -> None:
    validator = _validator("dataset-worker-result.schema.json")
    validator.validate(
        {
            "diagnostic": None,
            "entries": [{"digest": {"sha256": "0" * 64}, "name": "part-000.json", "size": "12"}],
            "phase": "complete",
            "status": "pass",
            "tokenCount": 9,
        }
    )
    with pytest.raises(ValidationError):
        validator.validate(
            {
                "diagnostic": {"code": "E_RESOURCE_LIMIT", "context": {}},
                "entries": [{"digest": {"sha256": "0" * 64}, "name": "part.json", "size": None}],
                "phase": "semantic",
                "status": "resource_limit",
                "tokenCount": 9,
            }
        )
