import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_DIR = Path("data/jobs")
DATA_DIR.mkdir(parents=True, exist_ok=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def job_path(job_id: str) -> Path:
    return DATA_DIR / f"{job_id}.json"


def create_job(job_id: str, payload: dict[str, Any]) -> None:
    data = {
        "job_id": job_id,
        "status": "pending",
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "request": payload,
        "outputs": {},
        "candidates": [],
        "error": None,
    }
    job_path(job_id).write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")


def load_job(job_id: str) -> dict[str, Any]:
    path = job_path(job_id)
    if not path.exists():
        raise FileNotFoundError(f"Job not found: {job_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_job(job_id: str, data: dict[str, Any]) -> None:
    data["updated_at"] = utc_now_iso()
    job_path(job_id).write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")


def update_job_status(job_id: str, status: str, error: str | None = None) -> None:
    data = load_job(job_id)
    data["status"] = status
    data["error"] = error
    save_job(job_id, data)


def list_jobs() -> list[dict[str, Any]]:
    jobs = []
    for path in sorted(DATA_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        jobs.append({
            "job_id": data.get("job_id", path.stem),
            "status": data.get("status", "unknown"),
            "request": data.get("request", {}),
            "candidate_count": len(data.get("candidates", [])),
            "error": data.get("error"),
            "created_at": data.get("created_at", ""),
        })
    return jobs


def list_job_records() -> list[dict[str, Any]]:
    """Return full persisted job payloads from disk."""
    records: list[dict[str, Any]] = []
    for path in sorted(DATA_DIR.glob("*.json")):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            # Skip corrupted files to avoid breaking active scans.
            continue
    return records


def delete_job(job_id: str) -> None:
    """Delete a single job record from disk."""
    path = job_path(job_id)
    if not path.exists():
        raise FileNotFoundError(f"Job not found: {job_id}")
    path.unlink()


def delete_all_jobs() -> int:
    """Delete all persisted job records and return deleted count."""
    deleted = 0
    for path in DATA_DIR.glob("*.json"):
        try:
            path.unlink()
            deleted += 1
        except FileNotFoundError:
            continue
    return deleted
