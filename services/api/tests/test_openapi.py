import json
from pathlib import Path

from vic.main import create_app

OPENAPI = Path(__file__).resolve().parents[3] / "contracts" / "openapi.json"

EXPECTED_PATHS = {"/health", "/cases", "/cases/{case_id}/runs", "/runs/{run_id}",
                  "/runs/{run_id}/outputs",
                  "/cases/{case_id}/reports/{version}", "/cases/{case_id}/evidence",
                  "/cases/{case_id}/documents"}


def test_paths_match_contract():
    assert set(create_app().openapi()["paths"]) == EXPECTED_PATHS


def test_422_uses_error_envelope():
    schema = create_app().openapi()
    components = schema["components"]["schemas"]
    assert "ErrorEnvelope" in components
    assert "HTTPValidationError" not in components
    assert "ValidationError" not in components


def test_enums_present():
    components = create_app().openapi()["components"]["schemas"]
    assert components["Recommendation"]["enum"] == ["Invest", "Conditional", "Do Not Invest"]
    assert len(components["SectionKey"]["enum"]) == 11


def test_committed_openapi_is_in_sync():
    """Fails until you run: python scripts/export_openapi.py (and commit the result)."""
    assert OPENAPI.exists(), "contracts/openapi.json is missing; run scripts/export_openapi.py"
    committed = json.loads(OPENAPI.read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(create_app().openapi()))
