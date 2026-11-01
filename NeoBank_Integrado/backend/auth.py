import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from dotenv import load_dotenv
from fastapi import HTTPException

# Carrega o .env da raiz do projeto (pasta acima de /backend)
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ_PROJETO / ".env")

ALGORITMO = "HS256"
MINUTOS_SESSAO = 30


def _obter_chave():
    chave = os.getenv("NEOBANK_JWT_SECRET")

    if not chave:
        raise RuntimeError(
            "A variável NEOBANK_JWT_SECRET não está configurada no .env."
        )

    return chave


def criar_token(cliente_id: int) -> str:
    agora = datetime.now(timezone.utc)

    dados = {
        "sub": str(cliente_id),  # o JWT exige que "sub" seja texto
        "iat": agora,
        "exp": agora + timedelta(minutes=MINUTOS_SESSAO),
    }

    return jwt.encode(dados, _obter_chave(), algorithm=ALGORITMO)


def verificar_token(token: str) -> int:
    try:
        dados = jwt.decode(token, _obter_chave(), algorithms=[ALGORITMO])
        return int(dados["sub"])

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Sessão expirada. Entre novamente."
        )

    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="Sessão inválida. Entre novamente."
        )