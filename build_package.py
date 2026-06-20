import os
import shutil
import subprocess
import sys
import zipfile

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    build_dir = os.path.join(root_dir, "build")
    dist_dir = os.path.join(root_dir, "dist")
    package_dir = os.path.join(build_dir, "package")

    # Limpiar compilaciones anteriores
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)

    os.makedirs(package_dir, exist_ok=True)
    os.makedirs(dist_dir, exist_ok=True)

    print("Instalando dependencias para AWS Lambda (Linux x86_64)...")
    cmd = [
        sys.executable, "-m", "pip", "install",
        "pypdf==4.3.1", "pydantic>=2.0.0",
        "-t", package_dir,
        "--platform", "manylinux2014_x86_64",
        "--only-binary=:all:",
        "--python-version", "3.12",
        "--implementation", "cp",
        "--quiet"
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print("Dependencias descargadas e instaladas con éxito.")
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] No se pudieron instalar las dependencias: {e}")
        print("Asegúrate de tener conexión a Internet y que pip esté actualizado.")
        sys.exit(1)

    print("Copiando código fuente (funciones + módulo shared)...")
    # Copiamos las carpetas de código
    shutil.copytree(os.path.join(root_dir, "shared"), os.path.join(package_dir, "shared"))
    shutil.copytree(os.path.join(root_dir, "functions"), os.path.join(package_dir, "functions"))

    # Crear el zip base unificado
    zip_path = os.path.join(dist_dir, "deployment.zip")
    print(f"Generando ZIP unificado en: {zip_path}...")
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(package_dir):
            for file in files:
                filepath = os.path.join(root, file)
                arcname = os.path.relpath(filepath, package_dir)
                # Evitar incluir cachés locales
                if "__pycache__" in filepath or file.endswith(".pyc"):
                    continue
                zipf.write(filepath, arcname)

    # Copiar a los nombres individuales esperados por la plantilla de CloudFormation
    shutil.copyfile(zip_path, os.path.join(dist_dir, "create_job.zip"))
    shutil.copyfile(zip_path, os.path.join(dist_dir, "get_results.zip"))
    shutil.copyfile(zip_path, os.path.join(dist_dir, "worker.zip"))
    
    print("\n¡Empaquetado Exitoso!")
    print(f"Los siguientes archivos ZIP se guardaron en: {dist_dir}")
    print("  - create_job.zip (Listo para POST /jobs)")
    print("  - get_results.zip (Listo para GET /jobs/{id}/results)")
    print("  - worker.zip (Listo para procesar eventos SQS)")
    print("\nSiguientes pasos:")
    print("  1. Sube los archivos ZIP a tu bucket de despliegues en S3:")
    print("     aws s3 cp dist/ s3://<nombre-de-tu-bucket-de-despliegues>/ --recursive --exclude \"deployment.zip\"")
    print("  2. Despliega la plantilla CloudFormation usando la CLI:")
    print("     aws cloudformation deploy --template-file template.yaml --stack-name cv-ranker-stack \\")
    print("       --parameter-overrides DeploymentBucket=<nombre-de-tu-bucket-de-despliegues> GroqApiKey=<tu-api-key> \\")
    print("       --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM")

if __name__ == "__main__":
    main()
