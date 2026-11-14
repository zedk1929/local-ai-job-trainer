from typing import Dict, List, Optional
from app.core.job_contract import JobDefinition
from app.jobs.survey_cleaner import survey_cleaner_job

class JobRegistry:
    def __init__(self):
        self._jobs: Dict[str, JobDefinition] = {}
        # Register the initial hackathon job
        self.register(survey_cleaner_job)

    def register(self, job: JobDefinition):
        self._jobs[job.id] = job

    def get(self, job_id: str) -> Optional[JobDefinition]:
        return self._jobs.get(job_id)

    def list_jobs(self) -> List[Dict]:
        return [
            {
                "id": j.id,
                "title": j.title,
                "version": j.version,
                "description": j.description,
                "is_active": True,
                "config_schema": j.config_schema.model_dump(),
                "metrics": [m.model_dump() for m in j.metrics],
                "supported_models": j.supported_models,
                "supported_backends": j.supported_backends
            }
            for j in self._jobs.values()
        ]

registry = JobRegistry()
