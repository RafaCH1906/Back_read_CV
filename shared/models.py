from typing import List, Optional, Literal
from pydantic import BaseModel, Field

Seniority = Literal["junior", "mid", "senior", "unknown"]
ConfidenceFlag = Literal["ok", "low_extraction_quality", "error"]
ResultStatus = Literal["completed", "failed", "mock"]


class JobMetadata(BaseModel):
    """Item con sk='META' — lo crea create_job, el Worker solo lo lee."""
    job_id: str
    sk: str = "META"
    job_title: str = ""
    required_skills: List[str] = Field(default_factory=list)
    years_experience: int = 0
    recruiter_id: str = ""
    status: str = "created"
    created_at: int


class CvResult(BaseModel):
    """Item con sk='CV#{cv_id}' — esto es lo que escribe el Worker."""
    job_id: str
    sk: str  # f"CV#{cv_id}"
    cv_id: str
    filename: str
    status: ResultStatus
    processed_at: int
    score: Optional[int] = None
    strengths: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    summary: str = ""
    seniority: Seniority = "unknown"
    soft_skills_note: str = ""
    confidence_flag: ConfidenceFlag = "ok"


class GroqEvaluationResponse(BaseModel):
    """Schema esperado del JSON que devuelve Groq (antes de agregarle
    job_id/cv_id/filename/etc. al guardar en DynamoDB)."""
    score: int = Field(..., ge=0, le=100)
    strengths: List[str]
    gaps: List[str]
    summary: str
    seniority: Seniority
    soft_skills_note: str
    confidence_flag: ConfidenceFlag


class CreateJobRequest(BaseModel):
    job_title: str
    required_skills: List[str]
    years_experience: int
    cv_count: int = Field(..., gt=0)


class UploadUrlItem(BaseModel):
    cv_id: str
    presigned_url: str
    s3_key: str


class CreateJobResponse(BaseModel):
    job_id: str
    upload_urls: List[UploadUrlItem]
    expires_in_seconds: int


class JobRecord(BaseModel):
    job_id: str
    sk: str = "META"
    job_title: str
    required_skills: List[str]
    years_experience: int
    cv_count: int
    status: str = "pending"
    created_at: str
    cv_ids: List[str]
