import os
from typing import Dict, Any, List, Optional
from google.cloud import datastore
from google.oauth2 import service_account

def get_datastore_client(conn_data: Dict[str, Any]) -> datastore.Client:
    """Instancia o cliente do Google Cloud Datastore com suporte a Service Account ou ADC."""
    project_id = conn_data.get("project_id") or conn_data.get("database") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    credentials_path = conn_data.get("credentials_path")
    database_id = conn_data.get("database_id") # Para Firestore/Datastore multitenant

    credentials = None
    if credentials_path and os.path.exists(credentials_path):
        credentials = service_account.Credentials.from_service_account_file(credentials_path)

    kwargs = {}
    if project_id:
        kwargs["project"] = project_id
    if credentials:
        kwargs["credentials"] = credentials
    if database_id and database_id != "(default)":
        kwargs["database"] = database_id

    return datastore.Client(**kwargs)

def collect_datastore_metrics(conn_data: Dict[str, Any]) -> Dict[str, Any]:
    """Coleta métricas de performance, esquemas e saúde de entidades do Google Cloud Datastore."""
    project_id = conn_data.get("project_id") or conn_data.get("database") or "default"
    metrics = {
        "db_type": "datastore",
        "database": project_id,
        "project_id": project_id,
        "database_id": conn_data.get("database_id", "(default)"),
        "host": "datastore.googleapis.com",
        "version": "Google Cloud Datastore (Firestore API v1)",
        "cache_hit_ratio": None,
        "total_kinds_count": 0,
        "total_entities_count": 0,
        "total_bytes": 0,
        "kinds_summary": [],
        "properties_summary": [],
        "hotspot_risks": [],
        "composite_indexes_info": [],
        "errors": []
    }

    try:
        client = get_datastore_client(conn_data)

        # 1. Kinds cadastrados (__kind__)
        kinds = []
        try:
            kind_query = client.query(kind="__kind__")
            kind_query.keys_only()
            kinds = [entity.key.id_or_name for entity in kind_query.fetch() if not entity.key.id_or_name.startswith("__")]
            metrics["total_kinds_count"] = len(kinds)
        except Exception as e:
            metrics["errors"].append(f"Erro ao listar __kind__: {str(e)}")

        # 2. Estatísticas de Kinds e Tamanhos em Disco (__Stat_Kind__)
        try:
            stat_query = client.query(kind="__Stat_Kind__")
            stats_entities = list(stat_query.fetch())
            
            total_entities = 0
            total_bytes = 0
            kinds_stat_list = []

            for stat in stats_entities:
                kind_name = stat.get("kind_name", "")
                if kind_name.startswith("__"):
                    continue

                count = int(stat.get("count", 0))
                bytes_size = int(stat.get("bytes", 0))
                builtin_idx_bytes = int(stat.get("builtin_index_bytes", 0))
                composite_idx_bytes = int(stat.get("composite_index_bytes", 0))
                total_idx_bytes = builtin_idx_bytes + composite_idx_bytes

                total_entities += count
                total_bytes += bytes_size

                kinds_stat_list.append({
                    "kind_name": kind_name,
                    "estimated_rows": count,
                    "bytes_size": bytes_size,
                    "total_size_mb": round((bytes_size + total_idx_bytes) / (1024 * 1024), 2),
                    "data_size_mb": round(bytes_size / (1024 * 1024), 2),
                    "index_size_mb": round(total_idx_bytes / (1024 * 1024), 2)
                })

            metrics["total_entities_count"] = total_entities
            metrics["total_bytes"] = total_bytes
            metrics["kinds_summary"] = sorted(kinds_stat_list, key=lambda k: k.get("bytes_size", 0), reverse=True)
        except Exception as e:
            metrics["errors"].append(f"Estatísticas globais __Stat_Kind__ indisponíveis: {str(e)}")

        # 3. Propriedades e Indexação (__property__)
        try:
            prop_query = client.query(kind="__property__")
            prop_entities = list(prop_query.fetch(limit=100))
            props_by_kind = {}
            for p in prop_entities:
                kind_name = p.key.parent.id_or_name if p.key.parent else "Unknown"
                prop_name = p.key.id_or_name
                repr_types = p.get("property_representation", [])
                if kind_name not in props_by_kind:
                    props_by_kind[kind_name] = []
                props_by_kind[kind_name].append({
                    "property": prop_name,
                    "types": repr_types
                })
            metrics["properties_summary"] = [{"kind": k, "properties": v} for k, v in props_by_kind.items()]
        except Exception as e:
            metrics["errors"].append(f"Erro ao listar __property__: {str(e)}")

        # 4. Detecção de Riscos de Hotspots (Monotonic Key Writes)
        # Analisa chaves em busca de IDs puramente incrementais ou timestamps que causam hotspots de partição
        try:
            hotspot_alerts = []
            for kind in kinds[:5]:
                sample_query = client.query(kind=kind)
                sample_query.keys_only()
                keys = [e.key.id_or_name for e in sample_query.fetch(limit=15)]
                
                # Se todas forem inteiros pequenos/sequenciais
                int_keys = [k for k in keys if isinstance(k, int)]
                if len(int_keys) >= 5:
                    sorted_diffs = [int_keys[i+1] - int_keys[i] for i in range(len(int_keys)-1)]
                    if all(0 <= d <= 5 for d in sorted_diffs):
                        hotspot_alerts.append({
                            "kind": kind,
                            "reason": "Chaves sequenciais/auto-incrementais detectadas. Risco alto de hotspot de escrita em tablets Bigtable."
                        })
            metrics["hotspot_risks"] = hotspot_alerts
        except Exception as e:
            metrics["errors"].append(f"Erro na análise de hotspots: {str(e)}")

    except Exception as e:
        metrics["errors"].append(f"Falha de autenticação/conexão com Google Cloud Datastore: {str(e)}")

    return metrics

