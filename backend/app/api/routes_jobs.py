from fastapi import APIRouter, HTTPException
from app.core.registry import registry

router = APIRouter()

FUTURE_PRESETS = [
    {
        "id": "support-ticket-triage",
        "title": "Customer Support Triage",
        "version": "0.1.0-planned",
        "description": "Route inbound bug reports and refund inquiries to responsible engineering or billing teams.",
        "is_active": False,
        "badge": "Coming Soon"
    },
    {
        "id": "document-entity-extractor",
        "title": "Document Entity Extractor",
        "version": "0.1.0-planned",
        "description": "Extract structured line items, dates, and vendor addresses from unformatted purchase invoices.",
        "is_active": False,
        "badge": "Coming Soon"
    }
]

@router.get("/jobs")
async def list_jobs():
    active_jobs = registry.list_jobs()
    return {
        "jobs": active_jobs,
        "future_presets": FUTURE_PRESETS
    }

@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = registry.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return {
        "id": job.id,
        "title": job.title,
        "version": job.version,
        "description": job.description,
        "config_schema": job.config_schema.model_dump(),
        "metrics": [m.model_dump() for m in job.metrics],
        "default_training_options": job.default_training_options.model_dump(),
        "supported_models": job.supported_models,
        "supported_backends": job.supported_backends
    }
