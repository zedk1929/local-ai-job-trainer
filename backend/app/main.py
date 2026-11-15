from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db, mark_interrupted_baseline_batches
from app.services.run_store import run_store

from app.api.routes_health import router as health_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_projects import router as projects_router
from app.api.routes_setup import router as setup_router
from app.api.routes_datasets import router as datasets_router
from app.api.routes_runs import router as runs_router
from app.api.routes_inference import router as inference_router
from app.api.routes_baseline import router as baseline_router
from app.api.routes_analysis import router as analysis_router, recover_analyses

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB schema
    await init_db()
    # Mark any lingering interrupted runs and baseline batches safely
    await run_store.mark_interrupted_runs()
    await mark_interrupted_baseline_batches()
    await recover_analyses()
    yield

app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="Consumer app for teaching local AI specific jobs (Hackathon demo: Survey Cleaner)",
    lifespan=lifespan
)

# Enable CORS for local Vite development frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health_router, prefix="/api", tags=["Health & Capabilities"])
app.include_router(jobs_router, prefix="/api", tags=["Job Registry"])
app.include_router(projects_router, prefix="/api", tags=["Projects"])
app.include_router(setup_router, prefix="/api", tags=["Model & Supervisor Setup"])
app.include_router(datasets_router, prefix="/api", tags=["Datasets"])
app.include_router(runs_router, prefix="/api", tags=["Runs & Training"])
app.include_router(inference_router, prefix="/api", tags=["Inference & Export"])
app.include_router(baseline_router, prefix="/api", tags=["Baseline Evaluation"])
app.include_router(analysis_router, prefix="/api", tags=["Failure Analysis"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
