import json
import logging
from decimal import Decimal
from boto3.dynamodb.conditions import Key

from shared.dynamo_client import get_table

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Funcion para convertir int o float
def decimal_to_native(obj):
    if isinstance(obj, list):
        return [decimal_to_native(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: decimal_to_native(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        # Si es un entero decimal, convertir a int, de lo contrario a float
        return int(obj) if obj % 1 == 0 else float(obj)
    return obj

# Funcion para construir la respuesta
def _build_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }

# Funcion principal para la peticion GET /jobs/{id}/results 
def handler(event, context):
    logger.info("Event recibido en get_results: %s", json.dumps(event))
    job_id = (event.get("pathParameters") or {}).get("id")
    if not job_id:
        return _build_response(400, {"error": "missing_job_id"})

    try:
        table = get_table()
        response = table.query(
            KeyConditionExpression=Key("job_id").eq(job_id)
        )
        items = response.get("Items", [])

        if not items:
            return _build_response(404, {"error": "job_not_found"})
        job_meta = {}
        cv_results = []

        for item in items:
            sk = item.get("sk", "")
            if sk == "META":
                job_meta = item
            elif sk.startswith("CV#"):
                cv_results.append(item)

        if not job_meta:
            return _build_response(404, {"error": "job_metadata_not_found"})

        for cv in cv_results:
            cv.pop("sk", None)
        job_meta.pop("sk", None)
        cv_results.sort(
            key=lambda x: x.get("score") if x.get("score") is not None else -1,
            reverse=True
        )

        payload = {
            "job": decimal_to_native(job_meta),
            "results": decimal_to_native(cv_results),
            "total": len(cv_results),
        }

        return _build_response(200, payload)

    except Exception as e:
        logger.error("Error al obtener resultados para job_id %s: %s", job_id, e, exc_info=True)
        return _build_response(500, {"error": "internal_server_error", "detail": str(e)})
