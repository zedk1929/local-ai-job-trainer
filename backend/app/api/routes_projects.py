from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from app.services.run_store import run_store
from app.core.registry import registry

router = APIRouter()

class CreateProjectRequest(BaseModel):
    name: str
    job_id: str = "survey-cleaner"
    description: Optional[str] = ""
    survey_context: Optional[str] = ""
    taxonomy: Optional[List[Dict[str, str]]] = None
    coding_rules: Optional[List[str]] = None

class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    survey_context: Optional[str] = None
    taxonomy: Optional[List[Dict[str, str]]] = None
    coding_rules: Optional[List[str]] = None
    active_adapter_id: Optional[str] = None
    selected_dataset_id: Optional[str] = None
    response_col: Optional[str] = None
    id_col: Optional[str] = None
    label_topics_col: Optional[str] = None
    label_sentiment_col: Optional[str] = None
    label_needs_review_col: Optional[str] = None

@router.get("/projects")
async def list_projects():
    return await run_store.list_projects()

@router.post("/projects")
async def create_project(req: CreateProjectRequest):
    job = registry.get(req.job_id)
    if not job:
        raise HTTPException(status_code=400, detail=f"Invalid job ID: {req.job_id}")

    taxonomy = req.taxonomy or [t for t in job.config_schema.default_taxonomy]
    coding_rules = req.coding_rules or [r for r in job.config_schema.default_rules]
    survey_context = req.survey_context or "Campus café gathering customer feedback on menu quality, pricing, speed, and seating."

    proj = await run_store.create_project(
        name=req.name,
        job_id=req.job_id,
        description=req.description or "",
        survey_context=survey_context,
        taxonomy=taxonomy,
        coding_rules=coding_rules
    )
    return proj

@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    proj = await run_store.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj

@router.patch("/projects/{project_id}")
async def update_project(project_id: str, req: UpdateProjectRequest):
    proj = await run_store.update_project(
        project_id=project_id,
        name=req.name,
        survey_context=req.survey_context,
        taxonomy=req.taxonomy,
        coding_rules=req.coding_rules,
        active_adapter_id=req.active_adapter_id,
        selected_dataset_id=req.selected_dataset_id,
        response_col=req.response_col,
        id_col=req.id_col,
        label_topics_col=req.label_topics_col,
        label_sentiment_col=req.label_sentiment_col,
        label_needs_review_col=req.label_needs_review_col
    )
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj
