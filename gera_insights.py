import mysql.connector
from google import genai # Importação atualizada

import os

# 1. Configurar a API do Gemini
CHAVE_API = os.environ.get("GEMINI_API_KEY", "SUA_CHAVE_AQUI")

# 2. Configurações de Conexão com o MariaDB
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": "e_commerce"
}

def coletar_metricas_banco():
    print("Conectando ao banco de dados para extrair métricas...")
    try:
        conexao = mysql.connector.connect(**DB_CONFIG)
        cursor = conexao.cursor(dictionary=True)

        query_metricas = """
            SELECT 
                table_name AS 'Tabela', 
                table_rows AS 'Linhas_Estimadas',
                ROUND(((data_length + index_length) / 1024 / 1024), 2) AS 'Tamanho_MB',
                ROUND((index_length / 1024 / 1024), 2) AS 'Tamanho_Indice_MB'
            FROM information_schema.TABLES 
            WHERE table_schema = 'e_commerce';
        """
        cursor.execute(query_metricas)
        metricas = cursor.fetchall()

        esquemas = []
        cursor.execute("SHOW TABLES")
        tabelas = cursor.fetchall()
        
        for tab in tabelas:
            nome_tabela = tab['Tables_in_e_commerce']
            cursor.execute(f"SHOW CREATE TABLE {nome_tabela}")
            resultado = cursor.fetchone()
            esquemas.append(resultado[f'Create Table'])

        return metricas, esquemas

    except mysql.connector.Error as err:
        print(f"Erro ao conectar ao banco: {err}")
        return None, None
    finally:
        if 'conexao' in locals() and conexao.is_connected():
            cursor.close()
            conexao.close()

def analisar_com_gemini(metricas, esquemas):
    print("Enviando dados para análise do Gemini...\n")
    
    texto_metricas = "\n".join([str(m) for m in metricas])
    texto_esquemas = "\n\n".join(esquemas)

    prompt = f"""
    Você é um Arquiteto de Dados e DBA Especialista em MariaDB.
    Abaixo estão as métricas atuais (tamanho e linhas) e as estruturas (DDL) do meu banco de dados de e-commerce.

    **Métricas Atuais (information_schema):**
    {texto_metricas}

    **Estrutura das Tabelas (DDL):**
    {texto_esquemas}

    Com base nesses dados (onde cada tabela tem aproximadamente 10.000 linhas), me forneça um relatório detalhado com:
    1. **Saúde do Banco:** O tamanho dos índices em relação aos dados está saudável?
    2. **Gargalos de Performance:** Considerando tabelas de 10 mil linhas (que podem crescer), existem gargalos visíveis no modelo atual?
    3. **Recomendações de Índices:** Quais índices adicionais eu devo criar para otimizar buscas (ex: buscas por data do pedido, email do cliente, ou junções)? Forneça os comandos SQL exatos.
    4. **Tipagem de Dados:** Alguma sugestão para otimizar os tipos de dados (VARCHAR, INT, DATETIME) visando economizar espaço e memória?
    """

    # Inicia o cliente da nova biblioteca
    client = genai.Client(api_key=CHAVE_API)
    
    # Nova forma de chamar o modelo
    resposta = client.models.generate_content(
        model='gemini-3.7-flash',
        contents=prompt,
    )
    
    print("-" * 50)
    print("🧠 INSIGHTS DO GEMINI:")
    print("-" * 50)
    print(resposta.text)
    print("-" * 50)

if __name__ == "__main__":
    metricas_db, esquemas_db = coletar_metricas_banco()
    
    if metricas_db and esquemas_db:
        analisar_com_gemini(metricas_db, esquemas_db)