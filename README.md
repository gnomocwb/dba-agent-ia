# ⚡ DBA Agent Studio

> **Agente de IA e Dashboard Web para Monitoramento, Diagnóstico de Performance e Otimização de Bancos de Dados PostgreSQL e MariaDB/MySQL.**

Desenvolvido com **Python (FastAPI)** e alimentado pelo **Google Gemini (SDK google-genai)**.

---

## 🌟 Funcionalidades

- 🔌 **Gerenciador Multi-Banco**: Conecte-se facilmente a múltiplas instâncias PostgreSQL e MariaDB (locais ou remotas).
- 📊 **Métricas de Performance em Tempo Real**:
  - **Eficiência de Cache**: Cache Hit Ratio de Heap/Buffer e Índices.
  - **Queries Lentas**: Identificação de gargalos e tempos médios (`pg_stat_statements` / Slow Query Logs).
  - **Uso de Índices vs Scans Sequenciais**: Detecção de tabelas que exigem criação de índices.
  - **Saúde do Esquema**: Detecção de tabelas sem Primary Key e bloat de tuplas mortas.
  - **Tamanho de Tabelas e Índices**: Análise de espaço em disco.
- 🧠 **Agente DBA Especialista (Google Gemini)**:
  - **Health Score (0 a 100)**: Nota técnica de saúde calculada para a base de dados.
  - **Diagnóstico Completo**: Análise de I/O, concorrência, memória e DDLs.
  - **Recomendações com Comandos SQL**: DDLs prontos para copiar (`CREATE INDEX CONCURRENTLY...`, `VACUUM ANALYZE...`, tuning de parâmetros de configuração).
- 💬 **Chat Interativo com o Agente DBA**: Converse diretamente com a IA sobre o banco de dados ativo.
- 🎨 **Interface Web Moderna**: Painel responsivo em tema Dark Mode.

---

## 🚀 Como Executar

### 1. Pré-requisitos
- Python 3.10+
- Chave de API do [Google AI Studio (Gemini)](https://aistudio.google.com/)

### 2. Instalação
```bash
# Clone o repositório
git clone <URL_DO_SEU_REPOSITORIO>
cd <PASTA_DO_REPOSITORIO>

# Crie e ative o ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# ou no Windows:
.\.venv\Scripts\Activate.ps1

# Instale as dependências
pip install fastapi uvicorn psycopg2-binary mysql-connector-python google-genai aiofiles
```

### 3. Inicie o Servidor
```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

Abra no navegador: [http://127.0.0.1:8000](http://127.0.0.1:8000)

---

## 📁 Estrutura do Projeto

```text
├── app.py                     # Servidor Web FastAPI e endpoints REST
├── db_manager.py              # Gerenciador seguro de conexões multi-banco
├── dba_agent.py               # Agente DBA com Google Gemini (diagnóstico e chat)
├── collectors/
│   ├── postgres.py            # Coletor de métricas PostgreSQL
│   └── mariadb.py             # Coletor de métricas MariaDB/MySQL
├── static/
│   ├── index.html             # Interface Web do Dashboard
│   ├── style.css              # Estilos visuais (Dark Mode)
│   └── app.js                 # Lógica de integração e frontend
├── connections.example.json   # Modelo de configuração de conexões
└── README.md
```

