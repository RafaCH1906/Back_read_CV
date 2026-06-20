import json
import logging
import os
import secrets
from datetime import datetime, timezone

import boto3
from pydantic import ValidationError

from shared.models import CreateJobRequest, CreateJobResponse, UploadUrlItem, JobRecord
from shared.dynamo_client import put_job

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")

UPLOAD_BUCKET = os.environ["UPLOAD_BUCKET_NAME"]
PRESIGNED_URL_EXPIRATION = 900  # Coloque 15 min ya que pienso q será el tiempo suficiente para que alguien suba su cv


def _build_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    } # Esta funcion es para el tema de CORS


def handler(event, context):
    try:
        raw_body = json.loads(event.get("body") or "{}")
        request_data = CreateJobRequest(**raw_body)
    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning("Request inválido: %s", e)
        return _build_response(400, {"error": "invalid_request", "detail": str(e)})
    job_id = secrets.token_hex(16)
    now_iso = datetime.now(timezone.utc).isoformat()

    cv_ids = [secrets.token_hex(16) for _ in range(request_data.cv_count)]

    upload_urls: list[UploadUrlItem] = []
    try:
        for cv_id in cv_ids:
            s3_key = f"jobs/{job_id}/cvs/{cv_id}.pdf"
            presigned_url = s3_client.generate_presigned_url(
                ClientMethod="put_object",
                Params={
                    "Bucket": UPLOAD_BUCKET,
                    "Key": s3_key,
                    "ContentType": "application/pdf",
                },
                ExpiresIn=PRESIGNED_URL_EXPIRATION,
            )
            upload_urls.append(
                UploadUrlItem(cv_id=cv_id, presigned_url=presigned_url, s3_key=s3_key)
            )
    except Exception as e:
        logger.error("Error generando presigned URLs: %s", e)
        return _build_response(500, {"error": "presigned_url_generation_failed"})

    job_record = JobRecord(
        job_id=job_id,
        job_title=request_data.job_title,
        required_skills=request_data.required_skills,
        years_experience=request_data.years_experience,
        cv_count=request_data.cv_count,
        status="pending",
        created_at=now_iso,
        cv_ids=cv_ids,
    )

    try:
        put_job(job_record.model_dump())
    except Exception as e:
        logger.error("Error guardando job en DynamoDB: %s", e)
        return _build_response(500, {"error": "job_creation_failed"})

    logger.info("Job creado: job_id=%s cv_count=%d", job_id, request_data.cv_count)

    response = CreateJobResponse(
        job_id=job_id,
        upload_urls=upload_urls,
        expires_in_seconds=PRESIGNED_URL_EXPIRATION,
    )
    return _build_response(201, response.model_dump())