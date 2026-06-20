import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
REQUEST_TIMEOUT_SECONDS = 25


class GroqRateLimitError(Exception):
    """El request fue rechazado por límite de uso (HTTP 429). Reintentable."""
    pass


class GroqTransientError(Exception):
    """Error de red o 5xx. Reintentable."""
    pass


class GroqInvalidRequestError(Exception):
    """Error 4xx que no es rate limit (ej. payload inválido). NO reintentable."""
    pass


def evaluate_cv(api_key: str, prompt: str) -> dict:
    """
    Llama a Groq y devuelve el contenido del mensaje (string).
    El parseo/validación del JSON de evaluación se hace fuera de esta función.
    """
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,  # baja, queremos evaluaciones consistentes, no creativas
        "response_format": {"type": "json_object"},
    }

    request = urllib.request.Request(
        url=GROQ_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        logger.warning("Groq HTTPError %s: %s", e.code, error_body)

        if e.code == 429:
            raise GroqRateLimitError(f"Rate limit alcanzado: {error_body}") from e
        if 500 <= e.code < 600:
            raise GroqTransientError(f"Error de servidor Groq {e.code}: {error_body}") from e
        # 400, 401, 403, etc. -> no tiene sentido reintentar
        raise GroqInvalidRequestError(f"Request inválido ({e.code}): {error_body}") from e

    except urllib.error.URLError as e:
        # timeout, DNS, conexión rechazada, etc. -> transitorio, reintentar
        logger.warning("Groq URLError: %s", e)
        raise GroqTransientError(f"Error de red llamando a Groq: {e}") from e