import os
import json
from typing import Dict, Any, List, Optional
from google import genai
from google.genai import types

# A chave de API deve vir de variável de ambiente ou inserida pelo usuário no painel
FALLBACK_API_KEY = os.environ.get("GEMINI_API_KEY", "")

def get_api_key(provided_key: Optional[str] = None) -> str:
    """Retorna a chave da API do Gemini prioritária."""
    if provided_key and provided_key.strip():
        return provided_key.strip()
    
    # 1. Tenta carregar do config.json local (salvo pela interface web)
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if cfg.get("gemini_api_key") and cfg["gemini_api_key"].strip():
                    return cfg["gemini_api_key"].strip()
        except Exception:
            pass

    # 2. Tenta carregar do arquivo .env
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line_clean = line.strip()
                    if line_clean.startswith("GEMINI_API_KEY="):
                        val = line_clean.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            return val
        except Exception:
            pass

    # 3. Variável de ambiente do sistema operacional
    return os.environ.get("GEMINI_API_KEY", FALLBACK_API_KEY).strip()

def calculate_preliminary_health_score(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Calcula um score preliminar determinístico (0-100) e alertas antes da análise da IA."""
    score = 100
    deductions = []
    
    db_type = metrics.get("db_type")
    
    # 1. Avaliação do Cache Hit Ratio
    cache_ratio = metrics.get("cache_hit_ratio")
    if cache_ratio is not None:
        if cache_ratio < 80.0:
            penalty = 25
            score -= penalty
            deductions.append(f"Cache Hit Ratio muito baixo ({cache_ratio}%). Muitas leituras físicas em disco (-{penalty} pts).")
        elif cache_ratio < 95.0:
            penalty = 10
            score -= penalty
            deductions.append(f"Cache Hit Ratio abaixo do ideal ({cache_ratio}%). Recomendável > 95% (-{penalty} pts).")

    # 2. Avaliação específica do PostgreSQL
    if db_type == "postgres":
        # Scans sequenciais em tabelas grandes
        table_scans = metrics.get("table_scans", [])
        high_seq = [t for t in table_scans if t.get("seq_scan_pct", 0) > 70 and t.get("seq_tup_read", 0) > 10000]
        if high_seq:
            penalty = min(20, len(high_seq) * 5)
            score -= penalty
            deductions.append(f"{len(high_seq)} tabela(s) com alto volume de leituras sequenciais sem uso de índice (-{penalty} pts).")
        
        # Dead tuples (necessidade de VACUUM)
        vac_stats = metrics.get("vacuum_stats", [])
        high_dead = [v for v in vac_stats if v.get("dead_tup_pct", 0) > 20]
        if high_dead:
            penalty = 10
            score -= penalty
            deductions.append(f"{len(high_dead)} tabela(s) com alta porcentagem de tuplas mortas (acumulando bloat) (-{penalty} pts).")
            
        # pg_stat_statements ausente
        if not metrics.get("pg_stat_statements_enabled"):
            deductions.append("Extensão 'pg_stat_statements' desativada. Análise detalhada de queries lentas limitada (-5 pts).")
            score -= 5

    # 3. Avaliação específica do MariaDB
    elif db_type == "mariadb":
        # Tabelas sem PK
        no_pk = metrics.get("tables_without_pk", [])
        if no_pk:
            penalty = min(25, len(no_pk) * 10)
            score -= penalty
            deductions.append(f"{len(no_pk)} tabela(s) sem Chave Primária (anti-pattern crítico) (-{penalty} pts).")
            
        # Tabelas temporárias criadas em disco
        status = metrics.get("status_variables", {})
        tmp_disk = int(status.get("Created_tmp_disk_tables", 0))
        tmp_total = int(status.get("Created_tmp_tables", 0))
        if tmp_total > 0 and (tmp_disk / tmp_total) > 0.20:
            penalty = 10
            score -= penalty
            deductions.append(f"Mais de 20% das tabelas temporárias foram criadas em disco ({tmp_disk}/{tmp_total}) (-{penalty} pts).")

    # 4. Avaliação específica do Google Datastore
    elif db_type in ["datastore", "google_datastore"]:
        hotspots = metrics.get("hotspot_risks", [])
        if hotspots:
            penalty = min(30, len(hotspots) * 15)
            score -= penalty
            deductions.append(f"{len(hotspots)} kind(s) com risco crítico de hotspot de escrita (chaves sequenciais) (-{penalty} pts).")
        if metrics.get("errors"):
            score -= 10
            deductions.append("Avisos/erros detectados durante coleta de metadados da GCP (-10 pts).")

    # 5. Avaliação específica do Vertex AI Feature Store
    elif db_type in ["featurestore", "google_featurestore"]:
        unmonitored = metrics.get("unmonitored_features_count", 0)
        total_feat = metrics.get("total_features", 0)
        if total_feat > 0 and unmonitored > 0:
            penalty = min(25, int((unmonitored / total_feat) * 25))
            score -= penalty
            deductions.append(f"{unmonitored} feature(s) sem monitoramento contínuo de drift ativado (-{penalty} pts).")
        if metrics.get("total_features", 0) > 0 and metrics.get("online_serving_nodes", 0) == 0:
            deductions.append("Nenhum nó de online serving fixo provisionado (tempo de resposta sob demanda).")

    final_score = max(10, min(100, score))
    
    if final_score >= 90:
        status_label = "Excelente"
        badge_class = "success"
    elif final_score >= 75:
        status_label = "Bom"
        badge_class = "info"
    elif final_score >= 50:
        status_label = "Atenção"
        badge_class = "warning"
    else:
        status_label = "Crítico"
        badge_class = "danger"

    return {
        "score": final_score,
        "status": status_label,
        "badge_class": badge_class,
        "deductions": deductions
    }

def analyze_database_with_gemini(metrics: Dict[str, Any], api_key: Optional[str] = None, model: str = "gemini-3.5-flash-lite") -> Dict[str, Any]:
    """Aciona o Gemini para realizar uma auditoria completa de performance e saúde do banco."""
    key = get_api_key(api_key)
    if not key:
        return {
            "success": False,
            "error": "Chave de API do Gemini não configurada."
        }

    client = genai.Client(api_key=key)

    db_type = metrics.get("db_type", "postgres").lower()
    if db_type == "postgres":
        db_type_label = "PostgreSQL Relational DB"
        focus_structure = """
## 1. 🏥 Veredito Geral e Resumo Executivo
## 2. ⚠️ Gargalos Críticos e Riscos (queries lentas, scans sequenciais, bloat de dead tuples, índices)
## 3. 🎯 Recomendações Práticas e Comandos SQL Prontos (CREATE INDEX CONCURRENTLY, VACUUM ANALYZE)
## 4. ⚙️ Ajustes Sugeridos em postgresql.conf (shared_buffers, work_mem, effective_cache_size)
"""
    elif db_type in ["mariadb", "mysql"]:
        db_type_label = "MariaDB / MySQL Relational DB"
        focus_structure = """
## 1. 🏥 Veredito Geral e Resumo Executivo
## 2. ⚠️ Gargalos Críticos (tabelas sem PK, buffer pool hit ratio, temp tables em disco)
## 3. 🎯 Recomendações Práticas e Comandos SQL Prontos (ALTER TABLE, CREATE INDEX, refatoração de query)
## 4. ⚙️ Ajustes Sugeridos em my.cnf (innodb_buffer_pool_size, tmp_table_size)
"""
    elif db_type in ["datastore", "google_datastore"]:
        db_type_label = "Google Cloud Datastore / Firestore (NoSQL Document Store)"
        focus_structure = """
## 1. 🏥 Veredito Geral e Resumo Executivo (Volume de Entidades, Kinds e Tamanho em Disco)
## 2. ⚠️ Riscos de Hotspots de Escrita e Contenção em Shards Bigtable
## 3. 🎯 Otimização de Custos e Faturamento GCP (Projection Queries e index.yaml)
## 4. 🛠️ Recomendações de Modelagem de Chaves e Estrutura de Propriedades
"""
    elif db_type in ["featurestore", "google_featurestore"]:
        db_type_label = "Google Cloud Vertex AI Feature Store (MLOps & Feature Store)"
        focus_structure = """
## 1. 🏥 Veredito Geral e Resumo Executivo (Featurestores, Entity Types e Features Registradas)
## 2. ⚠️ Avaliação de Data Drift e Monitoramento de Features para Modelos de Machine Learning
## 3. ⚡ Latência de Online Serving e Dimensionamento de Nós
## 4. 🎯 Políticas de Retenção de Dados (TTL), Ingestion Freshness e Redução de Custos na GCP
"""
    else:
        db_type_label = metrics.get("db_type", "Banco de Dados")
        focus_structure = """
## 1. 🏥 Veredito Geral e Resumo Executivo
## 2. ⚠️ Gargalos Críticos
## 3. 🎯 Recomendações Práticas
## 4. ⚙️ Ajustes de Configuração
"""

    preliminary = calculate_preliminary_health_score(metrics)

    prompt = f"""
Você é um Arquiteto de Dados e Especialista Senior em {db_type_label}.
Analise as seguintes métricas de performance, esquemas e configurações extraídas ao vivo:

=== INFORMAÇÕES DO BANCO / SERVIÇO ===
Identificação: {metrics.get('database')}
Host / Endpoint: {metrics.get('host')}
Versão / API: {metrics.get('version')}

=== MÉTRICAS COLETADAS EM FORMATO JSON ===
{json.dumps(metrics, indent=2, ensure_ascii=False, default=str)}

=== OBJETIVO ===
Forneça um relatório executivo e técnico em Markdown estruturado exatamente com os tópicos a seguir:

# 📊 Diagnóstico de Saúde e Performance: {metrics.get('database')} ({db_type_label})
{focus_structure}

Seja extremamente direto, técnico, profissional e foque em otimização prática e redução de custos/latência.
"""

    # Lista de modelos prioritários garantindo resposta imediata sem gargalo de cota
    candidate_models = [model]
    for m in ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.7-flash"]:
        if m not in candidate_models:
            candidate_models.append(m)

    last_error = None
    for candidate in candidate_models:
        try:
            response = client.models.generate_content(
                model=candidate,
                contents=prompt,
            )
            return {
                "success": True,
                "analysis_markdown": response.text,
                "preliminary_score": preliminary,
                "model_used": candidate
            }
        except Exception as e:
            last_error = str(e)
            continue

    return {
        "success": False,
        "error": last_error or "Não foi possível comunicar com a API do Gemini.",
        "preliminary_score": preliminary
    }

def chat_with_dba(
    user_message: str,
    history: List[Dict[str, str]],
    current_metrics: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    model: str = "gemini-3.5-flash-lite"
) -> str:
    """Conversação interativa com o Agente DBA mantendo o contexto do banco de dados atual."""
    key = get_api_key(api_key)
    if not key:
        return """⚠️ **Chave de API do Gemini não configurada.**

Para ativar o chat com o Agente DBA e os diagnósticos com Inteligência Artificial:
1. Acesse a aba **⚙️ Configurações** no topo da tela.
2. Cole sua chave de API do Gemini (obtida gratuitamente no [Google AI Studio](https://aistudio.google.com/app/apikey)).
3. Clique em **Salvar Preferências**.

*Nota: Você também pode criar um arquivo `.env` na raiz do projeto contendo `GEMINI_API_KEY=sua_chave` ou definir a variável de ambiente no sistema.*"""

    client = genai.Client(api_key=key)

    context = ""
    if current_metrics:
        raw_type = current_metrics.get("db_type", "")
        if raw_type == "postgres":
            db_type = "PostgreSQL"
        elif raw_type == "mariadb":
            db_type = "MariaDB"
        elif raw_type == "datastore":
            db_type = "Google Cloud Datastore / Firestore"
        elif raw_type == "featurestore":
            db_type = "Google Cloud Vertex AI Feature Store"
        else:
            db_type = raw_type or "Banco de Dados"

        target_name = current_metrics.get('database') or current_metrics.get('project_id') or "N/A"
        item_count = len(current_metrics.get('table_sizes', []) or current_metrics.get('kinds', []) or current_metrics.get('featurestores', []))

        context = f"""
Contexto da Base/Recurso Ativo no momento:
- Tipo: {db_type}
- Identificador/Base: {target_name}
- Eficiência / Cache Hit: {current_metrics.get('cache_hit_ratio', 'N/A')}%
- Resumo de Recursos: {item_count} itens analisados
"""

    system_instruction = f"""
Você é um Agente DBA Especialista e Arquiteto de Dados em PostgreSQL, MariaDB, Google Cloud Datastore e Vertex AI Feature Store, altamente solícito e experiente.
Seu papel é responder dúvidas do usuário, sugerir comandos SQL ou gcloud/Python SDK exatos, explicar planos de execução (EXPLAIN), ajudar no particionamento, indexação, prevenção de hotspots no Datastore e otimização de serving no Feature Store.
{context}
Responda sempre com clareza, formatação Markdown bonita, blocos de código prontos para execução e boas práticas de banco de dados e arquitetura de dados.
"""

    contents = []
    contents.append({"role": "user", "parts": [{"text": system_instruction}]})
    contents.append({"role": "model", "parts": [{"text": "Entendido! Estou pronto para atuar como seu Arquiteto e DBA Especialista neste banco. Como posso ajudar você agora?"}]})

    for turn in history[-8:]:
        role = "user" if turn.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": turn.get("content", "")}]})

    contents.append({"role": "user", "parts": [{"text": user_message}]})

    candidate_models = [model]
    for m in ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.7-flash"]:
        if m not in candidate_models:
            candidate_models.append(m)

    for candidate in candidate_models:
        try:
            resp = client.models.generate_content(
                model=candidate,
                contents=contents
            )
            return resp.text
        except Exception:
            continue

    return "Erro ao consultar o Agente DBA em todos os modelos disponíveis."

