import os
from pathlib import Path
 
import psycopg
from dotenv import load_dotenv
 
# Carrega o .env da raiz do projeto (pasta acima de /backend)
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ_PROJETO / ".env")
 
 
def conectar():
 
    senha = os.getenv("NEOBANK_DB_PASSWORD")
 
    if not senha:
        raise RuntimeError(
            "A variável NEOBANK_DB_PASSWORD não está configurada."
        )
 
    return psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="neobank_db",
        user="postgres",
        password=senha,
        connect_timeout=5
    )

