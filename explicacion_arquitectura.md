# Explicación de la Arquitectura y Despliegue (Foco Académico) 🎓

Este documento sirve como guía para sustentar tu proyecto ante el docente. Explica detalladamente **cómo** se desplegó el sistema y **qué** servicios de AWS se utilizaron, junto con la justificación técnica de cada uno.

---

## 🚀 ¿Cómo se desplegó el proyecto?

Le puedes explicar al docente que implementaron **Infraestructura como Código (IaC)**:

1. **Infraestructura como Código (IaC):** En lugar de crear los servicios a mano en la consola de AWS (lo cual es propenso a errores), definieron toda la infraestructura en una plantilla declarativa de **AWS CloudFormation** (`template.yaml`).
2. **Empaquetado Multiplataforma:** Crearon un script en Python (`build_package.py`) que compila las dependencias (`pypdf` y `pydantic`) descargando específicamente las librerías binarias para Linux (`manylinux_x86_64`). Esto asegura que el código funcione en el entorno de AWS Lambda aunque se compile desde una computadora con Windows o macOS.
3. **Automatización:** Subieron los paquetes comprimidos a un bucket de despliegues en S3 y utilizaron la **AWS CLI** (`aws cloudformation deploy`) para levantar todo el stack tecnológico en minutos.
4. **Cumplimiento de Restricciones (AWS Academy):** Dado que AWS Academy bloquea la creación manual de roles IAM por seguridad, la plantilla asocia dinámicamente el rol pre-existente **`LabRole`** a todas las funciones Lambda, lo cual garantiza que tengan los permisos necesarios para escribir en DynamoDB, leer de S3 y consumir de SQS.

---

## 🏗️ Servicios de AWS Utilizados y su Justificación

El proyecto implementa una **Arquitectura Serverless basada en Eventos (Event-Driven)**. A continuación, los servicios utilizados:

### 1. Amazon API Gateway (HTTP API v2)
* **Función:** Es la puerta de entrada (Entrypoint) del sistema. Expone las rutas HTTP `POST /jobs` y `GET /jobs/{id}/results`.
* **Justificación:** Se eligió una **HTTP API** en lugar de una REST API clásica por ser más ligera, rápida (menor latencia) y económica. Cuenta con configuración integrada de CORS para permitir la conexión directa desde el navegador del usuario.

### 2. AWS Lambda (Cómputo Serverless)
* **Función:** Ejecuta la lógica del negocio en Python 3.12 sin necesidad de servidores encendidos continuamente.
* **Justificación:** Son funciones autoescalables que solo cobran por milisegundo de ejecución:
  * `cv-create-job`: Recibe la vacante y genera URLs firmadas.
  * `cv-worker`: Se activa con la cola SQS, extrae el texto del PDF, anonimiza y evalúa con Groq.
  * `cv-get-results`: Lee la base de datos y ordena los resultados para el cliente.

### 3. Amazon S3 (Almacenamiento de Objetos)
* **Función:** Contiene dos buckets:
  * `cv-uploads-${AWS::AccountId}`: Almacena los archivos PDF de los CVs subidos.
  * `cv-frontend-${AWS::AccountId}`: Aloja el código estático del Frontend (index.html, JS, CSS).
* **Justificación:** Es altamente seguro y escalable. Para subir los CVs de forma segura sin sobrecargar la API ni exponer credenciales, se utilizaron **S3 Presigned URLs (URLs firmadas)**, permitiendo al frontend subir los archivos binarios directamente a S3 en un flujo seguro.

### 4. Amazon SQS (Cola de Mensajes - Desacoplamiento)
* **Función:** Recibe las notificaciones de carga de S3 (`s3:ObjectCreated`) y las encola para que el Worker las procese.
* **Justificación:** Proporciona **resiliencia** y **desacoplamiento**. Si la API de Groq experimenta latencia o caída temporal, los mensajes no se pierden; se quedan en la cola de SQS. Cuenta con una **Dead Letter Queue (DLQ)** que almacena los CVs fallidos tras 3 reintentos para no perder información y facilitar el debugging.

### 5. Amazon DynamoDB (Base de Datos NoSQL)
* **Función:** Almacena la información de las ofertas de trabajo y las evaluaciones de los candidatos.
* **Justificación:** Base de datos NoSQL de baja latencia. Utiliza **Single-Table Design** (Diseño de Tabla Única) bajo la tabla `cv-ranker-results`:
  * **Partition Key (PK):** `job_id` (une todos los datos del mismo puesto).
  * **Sort Key (SK):** `META` (metadatos del puesto) o `CV#{cv_id}` (evaluaciones de los candidatos).
  * Permite realizar una sola consulta eficiente (`query`) para traer tanto los requisitos del puesto como la lista de postulantes ordenados en un solo viaje de red.
