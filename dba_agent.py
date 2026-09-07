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
    return os.environ.get("GEMINI_API_KEY", FALLBACK_API_KEY)

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

    db_type_label = "PostgreSQL" if metrics.get("db_type") == "postgres" else "MariaDB / MySQL"
    preliminary = calculate_preliminary_health_score(metrics)

    prompt = f"""
Você é um Arquiteto de Dados e DBA Especialista de nível Staff/Senior em {db_type_label}.
Analise as seguintes métricas de performance, esquemas e configurações extraídas ao vivo de um banco {db_type_label}:

=== INFORMAÇÕES DO BANCO ===
Banco: {metrics.get('database')}
Host: {metrics.get('host')}
Versão: {metrics.get('version')}
Cache Hit Ratio Geral: {metrics.get('cache_hit_ratio')}%

=== MÉTRICAS COLETADAS EM FORMATO JSON ===
{json.dumps(metrics, indent=2, ensure_ascii=False, default=str)}

=== OBJETIVO ===
Forneça um relatório executivo e técnico em Markdown com a seguinte estrutura:

# 📊 Diagnóstico de Saúde e Performance: {metrics.get('database')} ({db_type_label})

## 1. 🏥 Veredito Geral e Resumo Executivo
- Nota de Saúde sugerida (0 a 100) e justificativa clara e objetiva.
- Estado geral de I/O, concorrência e memória.

## 2. ⚠️ Gargalos Críticos e Riscos Identificados
- Liste os gargalos prioritários detectados (ex: queries lentas, tabelas com seq scans massivos, tabelas sem chave primária, bloat de dead tuples, índices duplicados ou ausentes, parâmetros de memória subdimensionados).
- Explique o impacto de cada um no consumo de CPU, I/O de disco e latência.

## 3. 🎯 Recomendações Práticas e Comandos SQL Prontos
- Forneça os comandos SQL exatos para otimização (ex: `CREATE INDEX CONCURRENTLY ...`, `VACUUM ANALYZE ...`, `ALTER TABLE ... ADD PRIMARY KEY ...`).
- Se houver queries lentas identificadas, mostre a versão otimizada ou índices recomendados para elas.

## 4. ⚙️ Ajustes Sugeridos em Parâmetros de Configuração
- Sugestões para parâmetros do arquivo de configuração (`postgresql.conf` ou `my.cnf`), como tamanhos de buffer, memória de ordenação e conexões, baseados no tamanho do banco.

Seja extremamente direto, técnico, profissional e foque em ganhos reais de performance.
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
        return "Erro: Chave de API do Gemini não configurada."

    client = genai.Client(api_key=key)

    context = ""
    if current_metrics:
        db_type = "PostgreSQL" if current_metrics.get("db_type") == "postgres" else "MariaDB"
        context = f"""
Contexto do Banco Ativo no momento:
- Tipo: {db_type}
- Nome da Base: {current_metrics.get('database')}
- Versão: {current_metrics.get('version')}
- Cache Hit Ratio: {current_metrics.get('cache_hit_ratio')}%
- Resumo de Tabelas: {len(current_metrics.get('table_sizes', []))} tabelas analisadas
"""

    system_instruction = f"""
Você é um Agente DBA Especialista e Arquiteto de Banco de Dados altamente solícito e experiente.
Seu papel é responder dúvidas do usuário, sugerir comandos SQL exatos, explicar planos de execução (EXPLAIN), ajudar no particionamento e no tuning de queries.
{context}
Responda sempre com clareza, formatação Markdown bonita, blocos de código SQL prontos para execução e boas práticas de banco de dados.
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

