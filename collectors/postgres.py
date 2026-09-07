import psycopg2
import psycopg2.extras
from typing import Dict, Any
from db_manager import get_live_postgres_connection

def collect_postgres_metrics(conn_data: Dict[str, Any]) -> Dict[str, Any]:
    """Coleta um conjunto completo de métricas de performance e saúde do PostgreSQL."""
    metrics = {
        "db_type": "postgres",
        "database": conn_data.get("database"),
        "host": conn_data.get("host"),
        "version": "Desconhecido",
        "cache_hit_ratio": None,
        "index_cache_hit_ratio": None,
        "connections_summary": [],
        "slow_queries": [],
        "pg_stat_statements_enabled": False,
        "table_scans": [],
        "table_sizes": [],
        "unused_indexes": [],
        "vacuum_stats": [],
        "key_settings": [],
        "errors": []
    }

    try:
        conn = get_live_postgres_connection(conn_data)
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # 1. Versão do PostgreSQL
        try:
            cur.execute("SELECT version();")
            metrics["version"] = cur.fetchone()[0]
        except Exception as e:
            metrics["errors"].append(f"Erro ao obter versão: {str(e)}")

        # 2. Cache Hit Ratio Geral (Heap/Tabelas)
        try:
            cur.execute("""
                SELECT 
                    COALESCE(sum(heap_blks_read), 0) as heap_read,
                    COALESCE(sum(heap_blks_hit), 0)  as heap_hit,
                    ROUND(
                        (COALESCE(sum(heap_blks_hit), 0)::numeric / 
                         NULLIF(COALESCE(sum(heap_blks_hit), 0) + COALESCE(sum(heap_blks_read), 0), 0) * 100
                        ), 2
                    ) as cache_hit_ratio
                FROM pg_statio_user_tables;
            """)
            row = cur.fetchone()
            if row and row["cache_hit_ratio"] is not None:
                metrics["cache_hit_ratio"] = float(row["cache_hit_ratio"])
            else:
                metrics["cache_hit_ratio"] = 100.0 # Sem leituras de disco ainda
        except Exception as e:
            metrics["errors"].append(f"Erro no Cache Hit Ratio: {str(e)}")

        # 3. Cache Hit Ratio de Índices
        try:
            cur.execute("""
                SELECT 
                    ROUND(
                        (COALESCE(sum(idx_blks_hit), 0)::numeric / 
                         NULLIF(COALESCE(sum(idx_blks_hit), 0) + COALESCE(sum(idx_blks_read), 0), 0) * 100
                        ), 2
                    ) as index_cache_hit_ratio
                FROM pg_statio_user_indexes;
            """)
            row = cur.fetchone()
            if row and row["index_cache_hit_ratio"] is not None:
                metrics["index_cache_hit_ratio"] = float(row["index_cache_hit_ratio"])
            else:
                metrics["index_cache_hit_ratio"] = 100.0
        except Exception as e:
            metrics["errors"].append(f"Erro no Index Hit Ratio: {str(e)}")

        # 4. Conexões ativas, idle e bloqueios
        try:
            cur.execute("""
                SELECT COALESCE(state, 'conectado') as state, count(*) as count
                FROM pg_stat_activity
                WHERE pid <> pg_backend_pid()
                GROUP BY state
                ORDER BY count DESC;
            """)
            metrics["connections_summary"] = [dict(r) for r in cur.fetchall()]
        except Exception as e:
            metrics["errors"].append(f"Erro ao obter conexões: {str(e)}")

        # 5. Queries Lentas (via pg_stat_statements se disponível)
        try:
            cur.execute("""
                SELECT 1 
                FROM pg_extension 
                WHERE extname = 'pg_stat_statements';
            """)
            has_ext = cur.fetchone()
            if has_ext:
                metrics["pg_stat_statements_enabled"] = True
                cur.execute("""
                    SELECT 
                        query,
                        calls, 
                        ROUND(total_exec_time::numeric, 2) as total_time_ms, 
                        ROUND(mean_exec_time::numeric, 2) as mean_time_ms,
                        ROUND(max_exec_time::numeric, 2) as max_time_ms,
                        rows as total_rows
                    FROM pg_stat_statements 
                    WHERE query NOT LIKE '%pg_%' AND query NOT LIKE '%information_schema%'
                    ORDER BY total_exec_time DESC 
                    LIMIT 10;
                """)
                metrics["slow_queries"] = [dict(r) for r in cur.fetchall()]
            else:
                metrics["pg_stat_statements_enabled"] = False
                # Fallback simples de queries ativas demoradas
                cur.execute("""
                    SELECT 
                        query, 
                        extract(epoch from (clock_timestamp() - query_start)) * 1000 as duration_ms,
                        state
                    FROM pg_stat_activity
                    WHERE state != 'idle' AND pid <> pg_backend_pid() AND query NOT LIKE '%pg_%'
                    ORDER BY duration_ms DESC 
                    LIMIT 5;
                """)
                metrics["slow_queries"] = [dict(r) for r in cur.fetchall()]
        except Exception as e:
            metrics["errors"].append(f"Erro ao obter queries lentas: {str(e)}")

        # 6. Tabelas com Sequential Scan vs Index Scan (detecção de índices ausentes)
        try:
            cur.execute("""
                SELECT 
                    schemaname,
                    relname as table_name, 
                    seq_scan, 
                    seq_tup_read,
                    idx_scan, 
                    idx_tup_fetch,
                    n_live_tup as live_rows,
                    n_dead_tup as dead_rows,
                    ROUND((seq_scan::numeric / NULLIF(seq_scan + COALESCE(idx_scan, 0), 0) * 100), 1) as seq_scan_pct
                FROM pg_stat_user_tables 
                WHERE (seq_scan + COALESCE(idx_scan, 0)) > 0
                ORDER BY seq_tup_read DESC 
                LIMIT 15;
            """)
            metrics["table_scans"] = [dict(r) for r in cur.fetchall()]
        except Exception as e:
            metrics["errors"].append(f"Erro em table scans: {str(e)}")

        # 7. Tamanho das Tabelas e Índices
        try:
            cur.execute("""
                SELECT 
                    schemaname,
                    relname as table_name,
                    pg_size_pretty(pg_total_relation_size(relid)) as total_size,
                    pg_size_pretty(pg_relation_size(relid)) as data_size,
                    pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) as index_size,
                    pg_total_relation_size(relid) as total_size_bytes
                FROM pg_catalog.pg_statio_user_tables
                ORDER BY pg_total_relation_size(relid) DESC 
                LIMIT 15;
            """)
            metrics["table_sizes"] = [dict(r) for r in cur.fetchall()]
        except Exception as e:
            metrics["errors"].append(f"Erro em tamanhos de tabela: {str(e)}")

        # 8. Índices Nunca Utilizados (candidatos à remoção para economizar I/O)
        try:
            cur.execute("""
                SELECT 
                    schemaname,
                    relname as table_name,
                    indexrelname as index_name,
                    idx_scan,
                    pg_size_pretty(pg_relation_size(indexrelid)) as index_size
                FROM pg_stat_user_indexes
                WHERE idx_scan = 0 
                  AND indexrelname NOT LIKE '%_pkey'
                  AND indexrelname NOT LIKE '%_unique%'
                ORDER BY pg_relation_size(indexrelid) DESC 
                LIMIT 10;
            """)
            metrics["unused_indexes"] = [dict(r) for r in cur.fetchall()]
        except Exception as e:
            metrics["errors"].append(f"Erro em índices não utilizados: {str(e)}")

        # 9. Dead Tuples e Status de VACUUM
        try:
            cur.execute("""
                SELECT 
                    relname as table_name,
                    n_live_tup as live_rows,
                    n_dead_tup as dead_rows,
                    ROUND((n_dead_tup::numeric / NULLIF(n_live_tup + n_dead_tup, 0) * 100), 2) as dead_tup_pct,
                    last_vacuum,
                    last_autovacuum
                FROM pg_stat_user_tables
                WHERE n_dead_tup > 100
                ORDER BY n_dead_tup DESC 
                LIMIT 10;
            """)
            metrics["vacuum_stats"] = [dict(r) for r in cur.fetchall()]
        except Exception as e:
            metrics["errors"].append(f"Erro em estatísticas de vacuum: {str(e)}")

        # 10. Configurações Críticas de Tuning do PostgreSQL
        try:
            cur.execute("""
                SELECT name, setting, unit, short_desc 
                FROM pg_settings 
                WHERE name IN (
                    'shared_buffers', 'work_mem', 'maintenance_work_mem', 
                    'effective_cache_size', 'max_connections', 'wal_buffers', 
                    'random_page_cost', 'autovacuum', 'checkpoint_completion_target'
                );
            """)
            metrics["key_settings"] = [dict(r) for r in cur.fetchall()]
        except Exception as e:
            metrics["errors"].append(f"Erro em pg_settings: {str(e)}")

        cur.close()
        conn.close()

    except Exception as e:
        metrics["errors"].append(f"Falha de conexão com PostgreSQL: {str(e)}")

    return metrics

