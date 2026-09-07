import os
import json
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db_manager import (
    load_connections,
    save_connections,
    get_connection_by_id,
    upsert_connection,
    delete_connection,
    test_db_connection,
    SafeJSONEncoder
)
from collectors.postgres import collect_postgres_metrics
from collectors.mariadb import collect_mariadb_metrics
from dba_agent import (
    analyze_database_with_gemini,
    calculate_preliminary_health_score,
    chat_with_dba,
    get_api_key
)

app = FastAPI(title="DBA Agent Studio", description="Agente de Performance e Diagnóstico para PostgreSQL e MariaDB")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

def load_app_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
        "gemini_model": "gemini-3.5-flash-lite"
    }

def save_app_config(cfg: Dict[str, Any]):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

class ConnectionInput(BaseModel):
    id: Optional[str] = None
    name: str
    db_type: str
    host: str = "localhost"
    port: int = 5432
    database: str
    user: str
    password: str = ""
    client_encoding: Optional[str] = None

class TestConnectionInput(BaseModel):
    db_type: str
    host: str = "localhost"
    port: int = 5432
    database: str
    user: str
    password: str = ""
    client_encoding: Optional[str] = None

class ChatInput(BaseModel):
    message: str
    history: List[Dict[str, str]] = []
    connection_id: Optional[str] = None
    model: Optional[str] = None

# Cache temporário de métricas por connection_id
cached_metrics: Dict[str, Dict[str, Any]] = {}

@app.get("/api/connections")
def api_get_connections():
    conns = load_connections()
    # Remove senhas na listagem geral para segurança visual
    safe_conns = []
    for c in conns:
        copy_c = dict(c)
        copy_c["has_password"] = bool(copy_c.get("password"))
        if "password" in copy_c:
            copy_c["password"] = "******" if copy_c["password"] else ""
        safe_conns.append(copy_c)
    return {"connections": safe_conns}

@app.post("/api/connections")
def api_save_connection(conn: ConnectionInput):
    data = conn.model_dump()
    # Se senha veio como "******", preserva a senha anterior salva
    if data.get("password") == "******" and data.get("id"):
        existing = get_connection_by_id(data["id"])
        if existing:
            data["password"] = existing.get("password", "")
            
    saved = upsert_connection(data)
    return {"success": True, "connection": saved}

@app.delete("/api/connections/{conn_id}")
def api_delete_connection(conn_id: str):
    success = delete_connection(conn_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conexão não encontrada")
    if conn_id in cached_metrics:
        del cached_metrics[conn_id]
    return {"success": True}

@app.post("/api/test-connection")
def api_test_connection(conn: TestConnectionInput):
    result = test_db_connection(conn.model_dump())
    return result

@app.get("/api/metrics/{conn_id}")
def api_get_metrics(conn_id: str):
    conn_data = get_connection_by_id(conn_id)
    if not conn_data:
        raise HTTPException(status_code=404, detail="Conexão não encontrada")

    db_type = conn_data.get("db_type", "postgres").lower()
    if db_type == "postgres":
        metrics = collect_postgres_metrics(conn_data)
    elif db_type in ["mariadb", "mysql"]:
        metrics = collect_mariadb_metrics(conn_data)
    else:
        raise HTTPException(status_code=400, detail=f"Tipo de banco não suportado: {db_type}")

    # Calcula score preliminar
    score_info = calculate_preliminary_health_score(metrics)
    metrics["preliminary_score"] = score_info

    # Atualiza cache
    cached_metrics[conn_id] = metrics

    # Retorna JSON serializado de forma segura
    return json.loads(json.dumps(metrics, cls=SafeJSONEncoder))

@app.post("/api/analyze/{conn_id}")
def api_analyze_database(conn_id: str, payload: Dict[str, Any] = Body(default={})):
    conn_data = get_connection_by_id(conn_id)
    if not conn_data:
        raise HTTPException(status_code=404, detail="Conexão não encontrada")

    # Coleta métricas atualizadas se não estiverem no cache
    metrics = cached_metrics.get(conn_id)
    if not metrics:
        db_type = conn_data.get("db_type", "postgres").lower()
        if db_type == "postgres":
            metrics = collect_postgres_metrics(conn_data)
        else:
            metrics = collect_mariadb_metrics(conn_data)
        cached_metrics[conn_id] = metrics

    config = load_app_config()
    api_key = payload.get("gemini_api_key") or config.get("gemini_api_key")
    model = payload.get("model") or config.get("gemini_model", "gemini-3.5-flash-lite")

    analysis_res = analyze_database_with_gemini(metrics, api_key=api_key, model=model)
    return analysis_res

@app.post("/api/chat")
def api_chat(payload: ChatInput):
    current_metrics = None
    if payload.connection_id and payload.connection_id in cached_metrics:
        current_metrics = cached_metrics[payload.connection_id]
        
    config = load_app_config()
    model = payload.model or config.get("gemini_model", "gemini-3.5-flash-lite")
    api_key = config.get("gemini_api_key")

    response_text = chat_with_dba(
        user_message=payload.message,
        history=payload.history,
        current_metrics=current_metrics,
        api_key=api_key,
        model=model
    )
    return {"reply": response_text}

@app.get("/api/config")
def api_get_config():
    config = load_app_config()
    key = config.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", "")
    masked_key = (key[:6] + "..." + key[-4:]) if len(key) > 10 else ("Configurada" if key else "")
    return {
        "gemini_api_key_masked": masked_key,
        "has_api_key": bool(key or get_api_key()),
        "gemini_model": config.get("gemini_model", "gemini-3.5-flash-lite")
    }

@app.post("/api/config")
def api_update_config(payload: Dict[str, Any] = Body(...)):
    config = load_app_config()
    if "gemini_api_key" in payload and payload["gemini_api_key"]:
        config["gemini_api_key"] = payload["gemini_api_key"].strip()
    if "gemini_model" in payload and payload["gemini_model"]:
        config["gemini_model"] = payload["gemini_model"]
    save_app_config(config)
    return {"success": True}

# Servir arquivos estáticos do frontend
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def serve_index():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Interface Web Frontend em preparação..."}

if __name__ == "__main__":
    import uvicorn
    print("Iniciando DBA Agent Studio em http://127.0.0.1:8000 ...")
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)

