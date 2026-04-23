from __future__ import annotations

import importlib
import os
from pathlib import Path

from fastapi.testclient import TestClient


def test_smoke_flow_with_ingestion_and_chat(tmp_path: Path, monkeypatch):
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv("GENIE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GENIE_DB_PATH", str(tmp_path / "data" / "genie.db"))
    monkeypatch.setenv("GENIE_PROFILE_CONFIG_DIR", str(root / "config" / "profiles"))
    monkeypatch.setenv("GENIE_DEMO_GATEWAY_URL", "http://127.0.0.1:8788")

    import app.main as main_module

    importlib.reload(main_module)
    client = TestClient(main_module.app)

    resolve_response = client.post("/profiles/resolve-startup", json={"profile_id": "demo"})
    assert resolve_response.status_code == 200

    upload_response = client.post(
        "/sources",
        files=[("files", ("benefits.txt", b"Benefits start on the first day of next month.", "text/plain"))],
    )
    assert upload_response.status_code == 200
    source_id = upload_response.json()[0]["id"]

    capture_response = client.post("/screen/capture")
    assert capture_response.status_code == 200
    capture_id = capture_response.json()["capture"]["id"]
    asset_response = client.get(f"/captures/{capture_id}")
    assert asset_response.status_code == 200
    assert asset_response.headers["content-type"].startswith("image/png")

    chat_response = client.post(
        "/chat",
        json={
          "prompt": "When do benefits start?",
          "use_current_screen": False,
          "source_ids": [source_id],
        },
    )
    assert chat_response.status_code == 200
    payload = chat_response.json()
    assert payload["trace_id"]
    assert payload["evidence"]
    assert payload["provider_used"]

    convo_id = payload["conversation_id"]
    attachment_response = client.post(
        f"/sessions/{convo_id}/attachments",
        files=[("files", ("one-off.txt", b"The secret phrase is BLUE CANARY.", "text/plain"))],
    )
    assert attachment_response.status_code == 200
    assert attachment_response.json()[0]["status"] in {"indexed", "failed"}

    attachment_list = client.get(f"/sessions/{convo_id}/attachments")
    assert attachment_list.status_code == 200
    assert attachment_list.json()

    chat_with_attachment = client.post(
        "/chat",
        json={
            "prompt": "What is the secret phrase?",
            "use_current_screen": False,
            "source_ids": [],
            "conversation_id": convo_id,
        },
    )
    assert chat_with_attachment.status_code == 200
    labels = " ".join(item["label"] for item in chat_with_attachment.json()["evidence"])
    assert "Attachment" in labels

    activity_start = client.post("/activity/start", json={"duration_seconds": 5, "sampling_hz": 1.0})
    assert activity_start.status_code == 200
    assert activity_start.json()["ok"] is True
    session_id = activity_start.json()["session"]["id"]

    activity_current = client.get("/activity/current")
    assert activity_current.status_code == 200

    activity_stop = client.post("/activity/stop", json={"session_id": session_id})
    assert activity_stop.status_code == 200
    assert activity_stop.json()["session"]["status"] in {"stopped", "completed"}
    assert activity_stop.json()["summary"]
