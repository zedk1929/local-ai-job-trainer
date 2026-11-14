from fastapi import APIRouter
from app.config import settings
from app.services.model_backend import LocalModelBackend
from app.services.supervisor_client import SupervisorClient
from app.services.training_backend import TrainingBackend

router = APIRouter()

@router.get("/health")
async def get_health():
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "app_mode": settings.app_mode
    }

@router.get("/capabilities")
async def get_capabilities():
    model_backend = LocalModelBackend()
    model_caps = await model_backend.inspect_capabilities()

    supervisor = SupervisorClient()
    training_backend = TrainingBackend()
    training_avail, training_msg = training_backend.is_training_available(model_caps)

    return {
        "app_mode": settings.app_mode,
        "model_inference": {
            "available": model_caps["inference_available"],
            "model_configured": model_caps["model_configured"],
            "model_name": model_caps["model_name"],
            "model_path": model_caps["model_path"],
            "endpoint_url": model_caps["endpoint_url"],
            "active_adapter": model_caps["active_adapter"],
            "notes": model_caps["notes"]
        },
        "supervisor_api": {
            "configured": supervisor.is_configured(),
            "provider": supervisor.provider,
            "model": supervisor.model
        },
        "adapter_training": {
            "supported": training_avail,
            "backend": settings.training_backend,
            "message": training_msg
        }
    }
