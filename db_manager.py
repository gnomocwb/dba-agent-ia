import json
import os
import uuid
from typing import Dict, Any, List, Optional
from decimal import Decimal
from datetime import datetime, date, timedelta
import psycopg2
import psycopg2.extras
import mysql.connector

CONNECTIONS_FILE = os.path.join(os.path.dirname(__file__), "connections.json")

class SafeJSONEncoder(json.JSONEncoder):
    """Codificador JSON customizado que lida com Decimal, datas e outros tipos comuns em bancos."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, timedelta):
            return str(obj)
        elif isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        return super().default(obj)

def load_connections() -> List[Dict[str, Any]]:
    """Carrega as conexões salvas ou cria perfis padrão se o arquivo não existir."""
    if not os.path.exists(CONNECTIONS_FILE):
        default_conns = [
            {
                "id": "pg-gnomo-local",
                "name": "PostgreSQL - GNOMO Local",
                "db_type": "postgres",
                "host": "localhost",
                "port": 5432,
                "database": "GNOMODBVLP",
                "user": "gnomo",
                "password": "",
                "client_encoding": "latin1"
            },
            {
                "id": "mariadb-ecommerce-local",
                "name": "MariaDB - E-Commerce Local",
                "db_type": "mariadb",
                "host": "localhost",
                "port": 3306,
                "database": "e_commerce",
                "user": "root",
                "password": "",
                "client_encoding": "utf8mb4"
            }
        ]
        save_connections(default_conns)
        return default_conns

    try:
        with open(CONNECTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_connections(connections: List[Dict[str, Any]]) -> None:
    """Salva as conexões no arquivo JSON."""
    with open(CONNECTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(connections, f, indent=2, ensure_ascii=False)

def get_connection_by_id(conn_id: str) -> Optional[Dict[str, Any]]:
    """Busca um perfil de conexão pelo ID."""
    conns = load_connections()
    for c in conns:
        if c.get("id") == conn_id:
            return c
    return None

def upsert_connection(conn_data: Dict[str, Any]) -> Dict[str, Any]:
    """Cria ou atualiza uma conexão."""
    conns = load_connections()
    conn_id = conn_data.get("id") or str(uuid.uuid4())
    conn_data["id"] = conn_id
    
    try:
        conn_data["port"] = int(conn_data.get("port", 5432 if conn_data.get("db_type") == "postgres" else 3306))
    except ValueError:
        conn_data["port"] = 5432 if conn_data.get("db_type") == "postgres" else 3306

    updated = False
    for i, c in enumerate(conns):
        if c.get("id") == conn_id:
            conns[i] = conn_data
            updated = True
            break
    
    if not updated:
        conns.append(conn_data)
        
    save_connections(conns)
    return conn_data

def delete_connection(conn_id: str) -> bool:
    """Remove uma conexão pelo ID."""
    conns = load_connections()
    initial_len = len(conns)
    conns = [c for c in conns if c.get("id") != conn_id]
    if len(conns) != initial_len:
        save_connections(conns)
        return True
    return False

def test_db_connection(conn_data: Dict[str, Any]) -> Dict[str, Any]:
    """Testa a conectividade com o banco especificado."""
    db_type = conn_data.get("db_type", "postgres").lower()
    host = conn_data.get("host", "localhost")
    port = int(conn_data.get("port", 5432 if db_type == "postgres" else 3306))
    database = conn_data.get("database", "")
    user = conn_data.get("user", "")
    password = conn_data.get("password", "")
    encoding = conn_data.get("client_encoding", "utf8")

    if db_type == "postgres":
        try:
            conn_params = {
                "dbname": database,
                "user": user,
                "password": password,
                "host": host,
                "port": port,
                "connect_timeout": 5
            }
            if encoding:
                conn_params["client_encoding"] = encoding

            conn = psycopg2.connect(**conn_params)
            cur = conn.cursor()
            cur.execute("SELECT version();")
            version_str = cur.fetchone()[0]
            cur.close()
            conn.close()
            return {"success": True, "version": version_str, "message": "Conectado com sucesso ao PostgreSQL!"}
        except Exception as e:
            return {"success": False, "error": str(e), "message": f"Falha ao conectar no PostgreSQL: {str(e)}"}

    elif db_type in ["mariadb", "mysql"]:
        try:
            conn = mysql.connector.connect(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                connection_timeout=5
            )
            cur = conn.cursor()
            cur.execute("SELECT VERSION();")
            version_str = cur.fetchone()[0]
            cur.close()
            conn.close()
            return {"success": True, "version": version_str, "message": "Conectado com sucesso ao MariaDB/MySQL!"}
        except Exception as e:
            return {"success": False, "error": str(e), "message": f"Falha ao conectar no MariaDB: {str(e)}"}

    else:
        return {"success": False, "error": f"Tipo de banco não suportado: {db_type}"}

def get_live_postgres_connection(conn_data: Dict[str, Any]):
    """Abre uma conexão com PostgreSQL pronta para uso."""
    params = {
        "dbname": conn_data.get("database"),
        "user": conn_data.get("user"),
        "password": conn_data.get("password"),
        "host": conn_data.get("host", "localhost"),
        "port": int(conn_data.get("port", 5432)),
        "connect_timeout": 8
    }
    if conn_data.get("client_encoding"):
        params["client_encoding"] = conn_data.get("client_encoding")
    return psycopg2.connect(**params)

def get_live_mariadb_connection(conn_data: Dict[str, Any]):
    """Abre uma conexão com MariaDB/MySQL pronta para uso."""
    return mysql.connector.connect(
        host=conn_data.get("host", "localhost"),
        port=int(conn_data.get("port", 3306)),
        database=conn_data.get("database"),
        user=conn_data.get("user"),
        password=conn_data.get("password"),
        connection_timeout=8
    )

