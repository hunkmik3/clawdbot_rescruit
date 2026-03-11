from uuid import uuid4

from fastapi import APIRouter
from fastapi import BackgroundTasks
from fastapi import HTTPException
from fastapi import Response

from app.models.schemas import JobCreateRequest, JobCreateResponse, JobStatusResponse
from app.services.job_store import create_job, delete_all_jobs, delete_job, list_jobs, load_job
from app.services.pipeline import run_job
from app.services.google_sheets import export_to_google_sheets
from pydantic import BaseModel


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/jobs", response_model=JobCreateResponse)
def create_job_endpoint(payload: JobCreateRequest, background_tasks: BackgroundTasks) -> JobCreateResponse:
    platforms = [platform.lower().strip() for platform in payload.platforms if platform.strip()]
    if not platforms:
        raise HTTPException(status_code=400, detail="At least one platform is required")

    job_id = str(uuid4())
    body = payload.model_dump()
    body["platforms"] = platforms

    create_job(job_id=job_id, payload=body)
    background_tasks.add_task(run_job, job_id)

    return JobCreateResponse(job_id=job_id, status="pending")


@router.get("/jobs")
def list_jobs_endpoint() -> list[dict]:
    return list_jobs()


@router.delete("/jobs")
def delete_all_jobs_endpoint() -> dict[str, int]:
    deleted_count = delete_all_jobs()
    return {"deleted_count": deleted_count}


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job_endpoint(job_id: str) -> Response:
    try:
        delete_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str) -> JobStatusResponse:
    try:
        data = load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return JobStatusResponse(
        job_id=job_id,
        status=data.get("status", "unknown"),
        error=data.get("error"),
        candidate_count=len(data.get("candidates", [])),
    )


@router.get("/jobs/{job_id}/results")
def get_job_results(job_id: str) -> dict:
    try:
        data = load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "job_id": job_id,
        "status": data.get("status"),
        "error": data.get("error"),
        "outputs": data.get("outputs", {}),
        "candidates": data.get("candidates", []),
    }


class ExportRequest(BaseModel):
    sheet_id: str
    tab_name: str = "Candidates"


@router.post("/jobs/{job_id}/export")
def export_job_results(job_id: str, request: ExportRequest) -> dict:
    try:
        data = load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    candidates = data.get("candidates", [])
    if not candidates:
        raise HTTPException(status_code=400, detail="No candidates to export")

    try:
        url = export_to_google_sheets(candidates, request.sheet_id, request.tab_name)
        return {
            "status": "success",
            "sheet_url": url,
            "exported_count": len(candidates)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")


class DeepScanRequest(BaseModel):
    screen_name: str
    connection_type: str = "followers"  # or "following"
    max_items: int = 20


@router.post("/jobs/deep-scan", response_model=JobCreateResponse)
def create_deep_scan_job(payload: DeepScanRequest, background_tasks: BackgroundTasks) -> JobCreateResponse:
    """Special endpoint to create a job that scrapes connections."""
    job_id = str(uuid4())
    
    body = {
        "keywords": [f"Deep Scan: {payload.screen_name}"],
        "platforms": ["x_connections"],
        "screen_name": payload.screen_name,
        "connection_type": payload.connection_type,
        "max_items": payload.max_items
    }
    
    create_job(job_id=job_id, payload=body)
    
    # Chuyển payload thành dict đơn giản để tránh lỗi serialization trong background task
    payload_dict = payload.model_dump()
    background_tasks.add_task(run_deep_scan_job, job_id, payload_dict)
    
    return JobCreateResponse(job_id=job_id, status="pending")

def run_deep_scan_job(job_id: str, payload_dict: dict):
    from app.services.twitter_scraper import scrape_twitter_connections
    from app.services.normalize import normalize_candidate
    from app.services.job_store import save_job, load_job, update_job_status
    
    update_job_status(job_id, "running")
    data = load_job(job_id)
    
    try:
        items = scrape_twitter_connections(
            screen_name=payload_dict.get("screen_name"),
            connection_type=payload_dict.get("connection_type", "followers"),
            max_items=payload_dict.get("max_items", 20)
        )
        
        candidates = []
        for item in items:
            try:
                candidate = normalize_candidate(item, "x")
                candidates.append(candidate.model_dump())
            except Exception:
                continue
        
        data["status"] = "succeeded"
        data["candidates"] = candidates
        data["candidate_count"] = len(candidates)
        data["outputs"] = {"x_connections": {"count": len(candidates)}}
        save_job(job_id, data)
    except Exception as e:
        data = load_job(job_id)
        data["status"] = "failed"
        data["error"] = str(e)
        save_job(job_id, data)
