import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

EXAMPLES = Path(__file__).resolve().parents[2] / "packages" / "shared" / "examples"
client = TestClient(app)


def test_valid_config() -> None:
    config = json.loads((EXAMPLES / "clinic_booking.json").read_text())
    response = client.post("/agent-configs/validate", json=config)
    assert response.status_code == 200
    assert response.json() == {"valid": True, "errors": []}


def test_invalid_config_returns_paths() -> None:
    config = json.loads((EXAMPLES / "clinic_booking.json").read_text())
    config["voice"]["tts"]["fallback"] = ["sarvam:meera"]
    response = client.post("/agent-configs/validate", json=config)
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["errors"] == [
        {
            "path": "$.voice.tts.fallback[0]",
            "message": "fallback 'sarvam:meera' uses the same vendor as the primary ('sarvam')",
        }
    ]


def test_non_object_body_is_invalid_not_500() -> None:
    response = client.post("/agent-configs/validate", json=[1, 2])
    assert response.status_code == 200
    assert response.json()["valid"] is False
