import os
import boto3

_dynamodb = boto3.resource("dynamodb")

TABLE_NAME = os.environ.get("TABLE", "cv-ranker-results")


def get_table():
    return _dynamodb.Table(TABLE_NAME)


def get_job_metadata(job_id: str) -> dict | None:
    """Lee el item de metadata (sk='META') creado por create_job."""
    table = get_table()
    response = table.get_item(Key={"job_id": job_id, "sk": "META"})
    return response.get("Item")


def save_cv_result(job_id: str, cv_id: str, item_data: dict) -> None:
    """
    Escribe/sobrescribe el resultado de un CV (sk='CV#{cv_id}').
    put_item con esta key es idempotente: si SQS reintenta el mismo mensaje,
    el resultado se sobrescribe en vez de duplicarse.
    """
    table = get_table()
    item = {"job_id": job_id, "sk": f"CV#{cv_id}", "cv_id": cv_id, **item_data}
    table.put_item(Item=item)


def put_job(job_data: dict) -> None:
    """
    Guarda los metadatos iniciales del job (sk='META').
    """
    table = get_table()
    item = {"job_id": job_data["job_id"], "sk": "META", **job_data}
    table.put_item(Item=item)
