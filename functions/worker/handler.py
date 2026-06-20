import json
import logging
import os
import time

from pypdf import PdfReader
from io import BytesIO
import boto3

from pydantic import ValidationError

from shared.groq_client import (
    evaluate_cv,
    GroqRateLimitError,
    GroqTransientError,
    GroqInvalidRequestError,
)
from shared.anonymizer import anonymize_cv_text
from shared.dynamo_client import get_job_metadata, save_cv_result
from shared.models import GroqEvaluationResponse

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

REQUIRED_RESULT_FIELDS = {
    "score", "strengths", "gaps", "summary",
    "seniority", "soft_skills_note", "confidence_flag",
}


def build_prompt(job_meta: dict, cv_text: str) -> str:
    return f"""Eres un evaluador de CVs para procesos de reclutamiento.
Compara el siguiente CV contra el puesto descrito. No asumas datos que no
estén explícitamente en el texto. Si el CV tiene información muy limitada
o mal extraída, indícalo en confidence_flag como "low_extraction_quality".

No le asignes peso numérico a soft skills en el score (solo son evidencia
cualitativa); el score debe basarse en experiencia relevante, skills
técnicas y seniority.

PUESTO: {job_meta.get('job_title', '')}
SKILLS REQUERIDAS: {job_meta.get('required_skills', [])}
AÑOS DE EXPERIENCIA REQUERIDOS: {job_meta.get('years_experience', 0)}

CV (anonimizado):
{cv_text}

Responde ÚNICAMENTE con un JSON con este formato exacto:
{{
  "score": <entero 0-100>,
  "strengths": ["...", "..."],
  "gaps": ["...", "..."],
  "summary": "...",
  "seniority": "junior|mid|senior",
  "soft_skills_note": "...",
  "confidence_flag": "ok|low_extraction_quality"
}}"""

# Funcion para extraer el texto del CV desde el bucket de S3
def extract_text_from_pdf(bucket: str, key: str) -> str:
    obj = s3.get_object(Bucket=bucket, Key=key)
    pdf_bytes = obj["Body"].read()
    reader = PdfReader(BytesIO(pdf_bytes))
    pages_text = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages_text).strip()

# Funcion para parsear el job_id y el cv_id desde la key
def parse_job_id_and_cv_id(key: str) -> tuple[str, str]:
    parts = key.split("/")
    job_id = parts[1]
    filename = parts[-1]
    cv_id = filename.rsplit(".", 1)[0]
    return job_id, cv_id


# Funcion para guardar el resultado de la evaluacion
def save_result(job_id: str, cv_id: str, filename: str, result: dict, status: str) -> None:
    save_cv_result(job_id, cv_id, {
        "filename": filename,
        "status": status,
        "processed_at": int(time.time()),
        **result,
    })


# Funcion para parsear la respuesta de Groq
def parse_groq_response(raw_content: str) -> dict:
    parsed = json.loads(raw_content)  # puede lanzar JSONDecodeError
    validated = GroqEvaluationResponse(**parsed)
    return validated.model_dump()

# Funcion principal para procesar el s3 record
def process_s3_record(s3_record: dict) -> None:
    bucket = s3_record["s3"]["bucket"]["name"]
    key = s3_record["s3"]["object"]["key"]
    job_id, cv_id = parse_job_id_and_cv_id(key)
    filename = key.split("/")[-1]

    logger.info("Procesando CV job_id=%s cv_id=%s", job_id, cv_id)

    job_meta = get_job_metadata(job_id)
    if not job_meta:
        # Job no existe -> no es un error transitorio, no tiene sentido reintentar
        logger.error("Job %s no encontrado, descartando CV %s", job_id, cv_id)
        return

    raw_text = extract_text_from_pdf(bucket, key)
    if not raw_text:
        save_result(
            job_id, cv_id, filename,
            {"score": 0, "strengths": [], "gaps": [],
             "summary": "No se pudo extraer texto del PDF (posiblemente escaneado/imagen).",
             "seniority": "unknown", "soft_skills_note": "",
             "confidence_flag": "low_extraction_quality"},
            status="completed",
        )
        return

    clean_text = anonymize_cv_text(raw_text)
    prompt = build_prompt(job_meta, clean_text)

    try:
        raw_response = evaluate_cv(GROQ_API_KEY, prompt)
        result = parse_groq_response(raw_response)
    except GroqInvalidRequestError as e:
        # No reintentable: guardamos como failed y seguimos (no relanzamos)
        logger.error("Request inválido a Groq para cv_id=%s: %s", cv_id, e)
        save_result(
            job_id, cv_id, filename,
            {"score": None, "strengths": [], "gaps": [],
             "summary": f"Evaluación falló: {e}", "seniority": "unknown",
             "soft_skills_note": "", "confidence_flag": "error"},
            status="failed",
        )
        return
    except (GroqRateLimitError, GroqTransientError, json.JSONDecodeError, ValueError, ValidationError) as e:
        # Reintentable: relanzamos para que SQS reintente el mensaje completo
        logger.warning("Error reintentable procesando cv_id=%s: %s", cv_id, e)
        raise

    save_result(job_id, cv_id, filename, result, status="completed")
    logger.info("CV evaluado OK job_id=%s cv_id=%s score=%s", job_id, cv_id, result.get("score"))


def handler(event, context):
    for sqs_record in event["Records"]:
        body = json.loads(sqs_record["body"])

        # S3 manda un evento de prueba (s3:TestEvent) al configurar la notificación;
        # no tiene la estructura 'Records', hay que ignorarlo explícitamente.
        if "Records" not in body:
            logger.info("Ignorando evento que no es de S3 (probablemente s3:TestEvent)")
            continue

        for s3_record in body["Records"]:
            process_s3_record(s3_record)

    return {"statusCode": 200}