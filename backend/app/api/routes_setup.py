from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from app.config import settings
from app.services.model_backend import LocalModelBackend
from app.services.supervisor_client import SupervisorClient

router = APIRouter()

class UpdateModelConfig(BaseModel):
    model_path: Optional[str] = None
    endpoint_url: Optional[str] = None
    model_name: Optional[str] = None

class UpdateSupervisorConfig(BaseModel):
    provider: Optional[str] = "gemini"
    model: Optional[str] = "gemini-2.5-pro"
    api_key: Optional[str] = None

class ModeToggleRequest(BaseModel):
    app_mode: str # "preview" or "connected"

@router.get("/setup/status")
async def get_setup_status():
    model_backend = LocalModelBackend()
    caps = await model_backend.inspect_capabilities()
    supervisor = SupervisorClient()

    return {
        "app_mode": settings.app_mode,
        "model": caps,
        "supervisor": {
            "configured": supervisor.is_configured(),
            "provider": supervisor.provider,
            "model": supervisor.model,
            "has_key": bool(supervisor.api_key)
        }
    }

@router.post("/setup/mode")
async def set_app_mode(req: ModeToggleRequest):
    if req.app_mode in ["preview", "connected"]:
        settings.app_mode = req.app_mode
    return {"app_mode": settings.app_mode}

@router.post("/setup/model")
async def update_model_setup(req: UpdateModelConfig):
    if req.model_path is not None:
        settings.local_model_path = req.model_path
    if req.endpoint_url is not None:
        settings.local_model_endpoint = req.endpoint_url
    if req.model_name is not None:
        settings.local_model_name = req.model_name

    backend = LocalModelBackend()
    caps = await backend.inspect_capabilities()
    return {"status": "updated", "capabilities": caps}

@router.post("/setup/supervisor")
async def update_supervisor_setup(req: UpdateSupervisorConfig):
    if req.provider is not None:
        settings.supervisor_provider = req.provider
    if req.model is not None:
        settings.supervisor_model = req.model
    if req.api_key is not None:
        settings.supervisor_api_key = req.api_key

    client = SupervisorClient()
    return {
        "status": "updated",
        "configured": client.is_configured(),
        "provider": client.provider,
        "model": client.model
    }

@router.post("/setup/supervisor/test")
async def test_supervisor_connection():
    client = SupervisorClient()
    result = await client.test_connection()
    return result
