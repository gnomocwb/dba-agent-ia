import mysql.connector
from typing import Dict, Any, List
from db_manager import get_live_mariadb_connection

def collect_mariadb_metrics(conn_data: Dict[str, Any]) -> Dict[str, Any]:
    """Coleta um conjunto completo de métricas de performance e saúde do MariaDB/MySQL."""
    database_name = conn_data.get("database", "")
    metrics = {
        "db_type": "mariadb",
        "database": database_name,
        "host": conn_data.get("host"),
        "version": "Desconhecido",
        "cache_hit_ratio": None,
        "buffer_pool_details": {},
        "status_variables": {},
        "connections_summary": [],
        "table_sizes": [],
        "tables_without_pk": [],
        "table_ddls": {},
        "key_settings": [],
        "errors": []
    }

    try:
        conn = get_live_mariadb_connection(conn_data)
        cur = conn.cursor(dictionary=True)

        # 1. Versão
        try:
            cur.execute("SELECT VERSION();")
            row = cur.fetchone()
            metrics["version"] = list(row.values())[0] if row else "Desconhecido"
        except Exception as e:
            metrics["errors"].append(f"Erro ao obter versão: {str(e)}")

        # 2. Status Globais & Buffer Pool Hit Ratio
        try:
            cur.execute("""
                SHOW GLOBAL STATUS WHERE Variable_name IN (
                    'Innodb_buffer_pool_read_requests',
                    'Innodb_buffer_pool_reads',
                    'Innodb_buffer_pool_pages_total',
                    'Innodb_buffer_pool_pages_free',
                    'Innodb_buffer_pool_pages_data',
                    'Threads_connected',
                    'Threads_running',
                    'Slow_queries',
                    'Questions',
                    'Uptime',
                    'Created_tmp_disk_tables',
                    'Created_tmp_tables',
                    'Handler_read_rnd_next',
                    'Select_full_join',
                    'Select_scan'
                );
            """)
            status_rows = cur.fetchall()
            status_map = {r["Variable_name"]: r["Value"] for r in status_rows}
            metrics["status_variables"] = status_map

            read_requests = float(status_map.get("Innodb_buffer_pool_read_requests", 0))
            reads = float(status_map.get("Innodb_buffer_pool_reads", 0))

            if read_requests > 0:
                if read_requests >= reads:
                    hit_ratio = round((1.0 - (reads / read_requests)) * 100.0, 2)
                else:
                    # Durante warm-up inicial pós-boot, leituras físicas podem superar requisições lógicas
                    hit_ratio = round((read_requests / (read_requests + reads)) * 100.0, 2)
                metrics["cache_hit_ratio"] = max(0.0, min(100.0, hit_ratio))
            else:
                metrics["cache_hit_ratio"] = 100.0

            metrics["buffer_pool_details"] = {
                "pages_total": status_map.get("Innodb_buffer_pool_pages_total"),
                "pages_free": status_map.get("Innodb_buffer_pool_pages_free"),
                "pages_data": status_map.get("Innodb_buffer_pool_pages_data")
            }

            metrics["connections_summary"] = [
                {"state": "Conectados", "count": int(status_map.get("Threads_connected", 0))},
                {"state": "Executando (Ativos)", "count": int(status_map.get("Threads_running", 0))}
            ]
        except Exception as e:
            metrics["errors"].append(f"Erro ao obter status do InnoDB: {str(e)}")

        # 3. Tamanho das Tabelas e Índices no Schema Atual
        try:
            cur.execute("""
                SELECT 
                    table_name AS table_name, 
                    COALESCE(table_rows, 0) AS estimated_rows,
                    ROUND(((data_length + index_length) / 1024 / 1024), 2) AS total_size_mb,
                    ROUND((data_length / 1024 / 1024), 2) AS data_size_mb,
                    ROUND((index_length / 1024 / 1024), 2) AS index_size_mb,
                    ROUND((index_length / NULLIF(data_length + index_length, 0) * 100), 1) as index_ratio_pct,
                    engine
                FROM information_schema.TABLES 
                WHERE table_schema = %s
                ORDER BY (data_length + index_length) DESC 
                LIMIT 20;
            """, (database_name,))
            metrics["table_sizes"] = cur.fetchall()
        except Exception as e:
            metrics["errors"].append(f"Erro ao obter tamanho de tabelas: {str(e)}")

        # 4. Tabelas Sem Chave Primária (anti-pattern crítico para performance e replicação)
        try:
            cur.execute("""
                SELECT t.table_name
                FROM information_schema.tables t
                LEFT JOIN information_schema.table_constraints tc 
                    ON t.table_schema = tc.table_schema 
                    AND t.table_name = tc.table_name 
                    AND tc.constraint_type = 'PRIMARY KEY'
                WHERE t.table_schema = %s 
                  AND t.table_type = 'BASE TABLE'
                  AND tc.constraint_name IS NULL;
            """, (database_name,))
            metrics["tables_without_pk"] = [r["table_name"] for r in cur.fetchall()]
        except Exception as e:
            metrics["errors"].append(f"Erro ao verificar chaves primárias: {str(e)}")

        # 5. DDL das Tabelas Principais (para o DBA Agent propor índices)
        try:
            cur.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE';")
            tables = cur.fetchall()
            # Limitar aos top 10 para não sobrecarregar
            top_tables = [list(t.values())[0] for t in tables][:10]
            
            for tab_name in top_tables:
                try:
                    cur.execute(f"SHOW CREATE TABLE `{tab_name}`")
                    res = cur.fetchone()
                    if res:
                        metrics["table_ddls"][tab_name] = res.get("Create Table")
                except Exception:
                    pass
        except Exception as e:
            metrics["errors"].append(f"Erro ao obter DDLs: {str(e)}")

        # 6. Variáveis Chave de Configuração
        try:
            cur.execute("""
                SHOW GLOBAL VARIABLES WHERE Variable_name IN (
                    'innodb_buffer_pool_size',
                    'max_connections',
                    'query_cache_size',
                    'join_buffer_size',
                    'tmp_table_size',
                    'max_heap_table_size',
                    'slow_query_log',
                    'long_query_time',
                    'innodb_log_file_size',
                    'innodb_flush_log_at_trx_commit'
                );
            """)
            metrics["key_settings"] = cur.fetchall()
        except Exception as e:
            metrics["errors"].append(f"Erro ao obter variáveis globais: {str(e)}")

        cur.close()
        conn.close()

    except Exception as e:
        metrics["errors"].append(f"Falha de conexão com MariaDB/MySQL: {str(e)}")

    return metrics
