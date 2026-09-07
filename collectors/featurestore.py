import os
from typing import Dict, Any, List, Optional
from google.cloud import aiplatform
from google.oauth2 import service_account

def init_aiplatform(conn_data: Dict[str, Any]):
    """Inicializa o SDK do Vertex AI com as credenciais fornecidas."""
    project_id = conn_data.get("project_id") or conn_data.get("database") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = conn_data.get("location", "us-central1")
    credentials_path = conn_data.get("credentials_path")

    credentials = None
    if credentials_path and os.path.exists(credentials_path):
        credentials = service_account.Credentials.from_service_account_file(credentials_path)

    aiplatform.init(
        project=project_id,
        location=location,
        credentials=credentials
    )
    return project_id, location

def collect_featurestore_metrics(conn_data: Dict[str, Any]) -> Dict[str, Any]:
    """Coleta métricas de saúde, drift, serving online e catálogo do Vertex AI Feature Store."""
    project_id = conn_data.get("project_id") or conn_data.get("database") or "default"
    location = conn_data.get("location", "us-central1")
    
    metrics = {
        "db_type": "featurestore",
        "database": f"{project_id} ({location})",
        "project_id": project_id,
        "location": location,
        "host": f"{location}-aiplatform.googleapis.com",
        "version": "Google Cloud Vertex AI Feature Store",
        "cache_hit_ratio": None,
        "total_featurestores": 0,
        "total_entity_types": 0,
        "total_features": 0,
        "featurestores_summary": [],
        "drift_alerts": [],
        "online_serving_nodes": 0,
        "unmonitored_features_count": 0,
        "errors": []
    }

    try:
        init_aiplatform(conn_data)

        # 1. Listar Featurestores
        fs_list = []
        try:
            featurestores = aiplatform.Featurestore.list()
            metrics["total_featurestores"] = len(featurestores)

            total_entities = 0
            total_features_count = 0
            unmonitored = 0
            total_nodes = 0

            for fs in featurestores:
                fs_name = fs.name
                fs_dict = {
                    "name": fs_name,
                    "create_time": str(fs.create_time),
                    "update_time": str(fs.update_time),
                    "online_serving_nodes": 0,
                    "entity_types": []
                }

                # Online Serving Config
                try:
                    if hasattr(fs, "online_serving_config") and fs.online_serving_config:
                        nodes = getattr(fs.online_serving_config, "fixed_node_count", 0)
                        fs_dict["online_serving_nodes"] = nodes
                        total_nodes += nodes
                except Exception:
                    pass

                # Entity Types & Features
                try:
                    entity_types = fs.list_entity_types()
                    total_entities += len(entity_types)

                    for et in entity_types:
                        et_name = et.name
                        features = et.list_features()
                        feat_count = len(features)
                        total_features_count += feat_count

                        monitoring_enabled = False
                        try:
                            if hasattr(et, "monitoring_config") and et.monitoring_config:
                                monitoring_enabled = True
                            else:
                                unmonitored += feat_count
                        except Exception:
                            unmonitored += feat_count

                        fs_dict["entity_types"].append({
                            "name": et_name,
                            "features_count": feat_count,
                            "monitoring_enabled": monitoring_enabled,
                            "features_sample": [f.name for f in features[:5]]
                        })
                except Exception as e:
                    metrics["errors"].append(f"Erro ao listar entity types de {fs_name}: {str(e)}")

                fs_list.append(fs_dict)

            metrics["featurestores_summary"] = fs_list
            metrics["total_entity_types"] = total_entities
            metrics["total_features"] = total_features_count
            metrics["online_serving_nodes"] = total_nodes
            metrics["unmonitored_features_count"] = unmonitored

        except Exception as e:
            metrics["errors"].append(f"Erro ao listar Featurestores: {str(e)}")

        # 2. Alertas de Drift e Riscos de MLOps
        alerts = []
        if metrics["unmonitored_features_count"] > 0:
            alerts.append({
                "type": "monitoring_missing",
                "severity": "warning",
                "message": f"{metrics['unmonitored_features_count']} feature(s) sem monitoramento contínuo de drift ativado."
            })
        if metrics["total_features"] > 0 and metrics["online_serving_nodes"] == 0:
            alerts.append({
                "type": "no_online_nodes",
                "severity": "info",
                "message": "Nenhum nó fixo de online serving provisionado (modo offline ou autoscaling serverless)."
            })
        metrics["drift_alerts"] = alerts

    except Exception as e:
        metrics["errors"].append(f"Falha de autenticação/conexão com Vertex AI Feature Store: {str(e)}")

    return metrics

