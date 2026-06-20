# CV Ranker Backend 🚀

Backend serverless e interactivo basado en eventos para evaluar Currículums Vitae (CVs) en formato PDF contra los requisitos de una oferta de empleo. Utiliza Amazon S3, Amazon SQS, AWS Lambda, Amazon DynamoDB y la API de Groq (Llama-3.3-70b).

Este repositorio está adaptado para ser desplegado de forma segura en **AWS Academy Learner Labs** utilizando el rol de ejecución pre-creado `LabRole`.

---

## 🛠️ Arquitectura del Sistema

El flujo de procesamiento es 100% asíncrono y desacoplado:

```text
[Frontend] --(POST /jobs)--> [Lambda create_job] --> [DynamoDB (META)]
    |                              |
    | (Retorna URLs Firmadas)      v
    +-----------------------> [Bucket S3 (Uploads)]
                                   |
                         (s3:ObjectCreated)
                                   v
                             [Cola SQS]
                                   |
                                   v
                         [Lambda Worker SQS]
                                   |
                   (Descarga PDF + Extrae Texto)
                                   |
                           (Anonimiza CV)
                                   |
                         (Llamada API Groq)
                                   |
                                   v
                          [DynamoDB (CV#id)] <--- [Lambda get_results] <--- [Frontend (Polling)]
```

---

## 📂 Estructura del Código

```text
backend/
  ├── dist/                # Contiene los archivos ZIP listos para AWS Lambda (se genera localmente)
  ├── functions/
  │     ├── create_job/    # Handler de POST /jobs (Genera URLs de subida)
  │     ├── get_results/   # Handler de GET /jobs/{id}/results (Ordena y devuelve resultados)
  │     └── worker/        # Worker SQS (Descarga de S3, extracción de texto, Groq y DynamoDB)
  ├── shared/              # Código y utilidades compartidas entre Lambdas
  │     ├── anonymizer.py  # Filtro regex para correos, LinkedIn y teléfonos
  │     ├── dynamo_client.py# Cliente y funciones de DynamoDB (Single-table)
  │     ├── groq_client.py # Cliente REST para Groq (con User-Agent para evadir Cloudflare)
  │     └── models.py      # Definición de esquemas de validación Pydantic
  ├── build_package.py     # Script Python para compilar dependencias para Linux x86_64
  ├── test_local.py        # Simulador local en memoria de todo el flujo
  ├── template.yaml        # Plantilla CloudFormation/SAM corregida para AWS Academy
  └── .gitignore           # Evita subir archivos ZIP temporales y secretos a GitHub
```

---

## 🔌 API Contract (Para el Desarrollador Frontend)

### 1. Crear un Trabajo de Evaluación
* **Endpoint:** `POST /jobs`
* **Content-Type:** `application/json`
* **Cuerpo de la Petición:**
  ```json
  {
    "job_title": "Backend Python Developer (AWS)",
    "required_skills": ["Python", "AWS", "DynamoDB"],
    "years_experience": 5,
    "cv_count": 2
  }
  ```
* **Respuesta (201 Created):**
  ```json
  {
    "job_id": "c171ed99c44a33d5f20932c13f477fc0",
    "upload_urls": [
      {
        "cv_id": "93fd4530fa70c5ddcfc8c88e7d442ae5",
        "presigned_url": "https://cv-uploads-12345.s3.amazonaws.com/jobs/c171ed99c44a33d5f20932c13f477fc0/cvs/93fd4530fa70c5ddcfc8c88e7d442ae5.pdf?AWSAccessKeyId=...",
        "s3_key": "jobs/c171ed99c44a33d5f20932c13f477fc0/cvs/93fd4530fa70c5ddcfc8c88e7d442ae5.pdf"
      },
      {
        "cv_id": "38ed1c57565d57eaa24312e4dba07702",
        "presigned_url": "https://cv-uploads-12345.s3.amazonaws.com/jobs/c171ed99c44a33d5f20932c13f477fc0/cvs/38ed1c57565d57eaa24312e4dba07702.pdf?AWSAccessKeyId=...",
        "s3_key": "jobs/c171ed99c44a33d5f20932c13f477fc0/cvs/38ed1c57565d57eaa24312e4dba07702.pdf"
      }
    ],
    "expires_in_seconds": 900
  }
  ```

> [!IMPORTANT]
> **Instrucciones para el Frontend (Subida a S3):**
> Para cada archivo PDF seleccionado por el usuario, el frontend debe realizar una petición HTTP **`PUT`** directamente a la `presigned_url` correspondiente.
> - **Método:** `PUT`
> - **Headers:** `Content-Type: application/pdf`
> - **Body:** El archivo PDF en formato binario (no enviar como multipart/form-data).
> - **CORS:** El bucket S3 tiene configurado CORS para aceptar peticiones `PUT` desde cualquier origen (`*`).

---

### 2. Consultar Resultados (Polling)
* **Endpoint:** `GET /jobs/{id}/results` (Reemplaza `{id}` por el `job_id` recibido en el POST)
* **Respuesta (200 OK):**
  ```json
  {
    "job": {
      "job_id": "c171ed99c44a33d5f20932c13f477fc0",
      "job_title": "Backend Python Developer (AWS)",
      "required_skills": ["Python", "AWS", "DynamoDB"],
      "years_experience": 5,
      "cv_count": 2,
      "status": "pending",
      "created_at": "2026-06-20T06:37:16.661703+00:00",
      "cv_ids": [
        "93fd4530fa70c5ddcfc8c88e7d442ae5",
        "38ed1c57565d57eaa24312e4dba07702"
      ]
    },
    "results": [
      {
        "job_id": "c171ed99c44a33d5f20932c13f477fc0",
        "cv_id": "93fd4530fa70c5ddcfc8c88e7d442ae5",
        "filename": "93fd4530fa70c5ddcfc8c88e7d442ae5.pdf",
        "status": "completed",
        "processed_at": 1781937437,
        "score": 90,
        "strengths": [
          "Experiencia en Python y AWS",
          "Conocimiento de DynamoDB",
          "Experiencia en despliegues en AWS con CloudFormation"
        ],
        "gaps": [],
        "summary": "El candidato tiene una sólida experiencia en desarrollo backend con Python y AWS, cumpliendo con los requisitos técnicos del puesto.",
        "seniority": "senior",
        "soft_skills_note": "No se mencionan soft skills explícitamente en el CV.",
        "confidence_flag": "ok"
      },
      {
        "job_id": "c171ed99c44a33d5f20932c13f477fc0",
        "cv_id": "38ed1c57565d57eaa24312e4dba07702",
        "filename": "38ed1c57565d57eaa24312e4dba07702.pdf",
        "status": "completed",
        "processed_at": 1781937438,
        "score": 0,
        "strengths": [],
        "gaps": [
          "Falta de experiencia en desarrollo backend",
          "No se menciona experiencia con Python",
          "No se menciona experiencia con AWS o DynamoDB"
        ],
        "summary": "El candidato no cumple con los requisitos del puesto de Backend Python Developer (AWS) debido a la falta de experiencia...",
        "seniority": "junior",
        "soft_skills_note": "No se mencionan habilidades blandas relevantes",
        "confidence_flag": "low_extraction_quality"
      }
    ],
    "total": 2
  }
  ```

> [!TIP]
> Los resultados devueltos en la lista `results` se encuentran automáticamente **ordenados de mayor a menor puntuación (score)**. Si un CV aún no termina de procesarse, no aparecerá en `results` hasta que el worker termine su ejecución (o aparecerá con `status: pending/failed` en su caso).

---

## 🧪 Pruebas Locales (Sin Costo de AWS)

Para verificar el correcto funcionamiento de toda la lógica de validación, procesamiento y llamadas al LLM localmente:

1. Crea un archivo `.env` en la raíz del backend (ya ignorado por git):
   ```env
   GROQ_API_KEY=gsk_tu_api_key_aqui
   ```
2. Ejecuta el script de prueba:
   ```bash
   python test_local.py
   ```
El script simulará por completo los eventos de S3, las llamadas a la API de Groq y la base de datos DynamoDB en memoria.

---

## 🚀 Despliegue en AWS desde una Instancia EC2 (AWS Academy)

### Paso 1: Configurar el Rol IAM en tu Instancia EC2
En AWS Academy, las credenciales temporales de laboratorio expiran constantemente. Para no tener que configurar credenciales manualmente en la terminal:
1. Ve a la consola de AWS EC2.
2. Selecciona tu instancia EC2.
3. Ve a **Acciones -> Seguridad -> Modificar rol IAM**.
4. Asigna el rol **`LabInstanceProfile`** (o en su defecto `LabRole`) a la instancia y guarda los cambios.
5. A partir de ahora, la CLI de AWS en tu EC2 obtendrá permisos automáticamente sin requerir `aws configure`.

### Paso 2: Clonar y Preparar el Entorno en la EC2
Conéctate por SSH a tu instancia EC2 y ejecuta:
```bash
# 1. Clonar el repositorio
git clone <URL_DE_TU_REPOSITORIO_GITHUB>
cd <NOMBRE_DEL_REPO>/backend

# 2. Instalar dependencias del sistema (ej. Amazon Linux)
sudo yum install python3 -y
```

### Paso 3: Compilar y Empaquetar
Ejecuta el script de empaquetado. Éste se encargará de descargar las dependencias compatibles con el microprocesador Linux x86_64 de Lambda:
```bash
python3 build_package.py
```
Esto generará los zips en la carpeta `dist/`.

### Paso 4: Crear el Bucket de Despliegue e Intercambiar Archivos
CloudFormation necesita leer los zips desde un bucket de S3:
```bash
# 1. Crear un bucket de despliegues (nombre debe ser único a nivel global)
aws s3 mb s3://mis-deploys-cv-ranker-12345

# 2. Subir los ZIPs compilados
aws s3 cp dist/ s3://mis-deploys-cv-ranker-12345/ --recursive --exclude "deployment.zip"
```

### Paso 5: Lanzar el Despliegue de CloudFormation
Lanza el despliegue inyectando el bucket de S3 creado y tu clave de API de Groq:
```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name cv-ranker-stack \
  --parameter-overrides DeploymentBucket=mis-deploys-cv-ranker-12345 GroqApiKey=gsk_TU_API_KEY_DE_GROQ \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM
```

Al terminar, la CLI imprimirá el **`ApiEndpoint`** en la sección de **Outputs** en tu terminal. Pásale este endpoint a tu compañero de frontend y ¡listo!
