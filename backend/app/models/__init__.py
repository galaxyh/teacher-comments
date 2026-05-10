"""ORM models — one module per table per ARCH-001 §2.1.

Importing this package eagerly imports all model modules so that Alembic's
autogenerate sees every table without explicit imports in env.py.
"""

from app.models.batch_job import BatchJob
from app.models.drive_file import DriveFile
from app.models.llm_call_audit import LLMCallAudit
from app.models.pii_mapping import PIIMapping
from app.models.processed_artifact import ProcessedArtifact
from app.models.semester_evaluation import SemesterEvaluation
from app.models.system_event import SystemEvent
from app.models.teacher import Teacher

__all__ = [
    "BatchJob",
    "DriveFile",
    "LLMCallAudit",
    "PIIMapping",
    "ProcessedArtifact",
    "SemesterEvaluation",
    "SystemEvent",
    "Teacher",
]
