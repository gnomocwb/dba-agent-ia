@echo off
title DBA Agent Studio
echo ======================================================
echo           Iniciando DBA Agent Studio...
echo ======================================================

:: Se existir o executavel compilado (.exe), executa diretamente
if exist "DBA-Agent-Studio.exe" (
    echo Executando versao compilada...
    start "" "DBA-Agent-Studio.exe"
    exit /b
)

:: Caso contrario, executa via ambiente Python
if not exist .venv (
    echo Criando ambiente virtual e instalando dependencias...
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    if exist requirements.txt (
        .\.venv\Scripts\pip.exe install -r requirements.txt
    ) else (
        echo Instalando pacotes essenciais...
        .\.venv\Scripts\pip.exe install fastapi uvicorn psycopg2-binary mysql-connector-python google-genai google-cloud-datastore google-cloud-aiplatform google-cloud-monitoring aiofiles
    )
)

echo Abrindo interface web em http://127.0.0.1:8000 ...
start http://127.0.0.1:8000
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
pause