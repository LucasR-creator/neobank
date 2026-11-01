from pathlib import Path
import logging

import psycopg
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr
from pwdlib import PasswordHash
from psycopg.errors import UniqueViolation

from backend.database import conectar
from backend.auth import criar_token, verificar_token
from backend.funcionalidades import router as funcionalidades_router, preparar


# ==========================================
# CONFIGURAÇÃO DO NEOBANK
# ==========================================

app = FastAPI(
    title="NeoBank API",
    description="Sistema bancário digital fictício",
    version="1.3.0"
)

app.include_router(funcionalidades_router)

PASTA_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

password_hash = PasswordHash.recommended()

logger = logging.getLogger("uvicorn.error")


# ==========================================
# PARA-QUEDAS: NUNCA MAIS "Internal Server Error" EM TEXTO
# ==========================================

@app.exception_handler(Exception)
async def erro_geral(request: Request, erro: Exception):
    logger.exception("Erro não tratado em %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno no servidor. Consulte o terminal."}
    )


# ==========================================
# MODELOS DE DADOS
# ==========================================

class Cliente(BaseModel):
    nome: str
    email: EmailStr
    senha: str


class DadosLogin(BaseModel):
    email: EmailStr
    senha: str


# ==========================================
# FUNÇÕES AUXILIARES
# ==========================================

def abrir_pagina(nome_arquivo: str):
    arquivo = PASTA_FRONTEND / nome_arquivo

    if not arquivo.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Página {nome_arquivo} não encontrada."
        )

    return FileResponse(arquivo)


def obter_cliente_autenticado(request: Request):
    token = request.cookies.get("neobank_sessao")

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Você precisa entrar na sua conta."
        )

    try:
        return verificar_token(token)

    except HTTPException:
        raise

    except RuntimeError:
        logger.exception("Falha na configuração da autenticação")
        raise HTTPException(
            status_code=503,
            detail="Autenticação temporariamente indisponível."
        )

    except Exception:
        logger.exception("Erro ao validar sessão")
        raise HTTPException(
            status_code=401,
            detail="Sessão inválida. Entre novamente."
        )


def pagina_protegida(request: Request, nome_arquivo: str):
    try:
        obter_cliente_autenticado(request)

    except HTTPException as erro:
        if erro.status_code == 401:
            return RedirectResponse(
                url="/login.html",
                status_code=303
            )

        raise

    return abrir_pagina(nome_arquivo)


# ==========================================
# PÁGINA INICIAL
# ==========================================

@app.get("/")
def inicio():
    return abrir_pagina("index.html")


@app.get("/site")
def pagina_inicial():
    return abrir_pagina("index.html")


# ==========================================
# STATUS DA API
# ==========================================

@app.get("/api/status")
def status():
    return {
        "banco": "NeoBank",
        "mensagem": "Bem-vindo ao NeoBank!",
        "status": "online"
    }


@app.get("/api/status-banco")
def status_banco():
    """Teste rápido: abra /api/status-banco para ver se o banco responde."""
    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()

        return {"banco": "conectado"}

    except Exception as erro:
        logger.exception("Teste de banco falhou")
        raise HTTPException(
            status_code=503,
            detail="Banco indisponível. Verifique o arquivo .env e o PostgreSQL."
        )


# ==========================================
# PÁGINAS PÚBLICAS
# ==========================================

@app.get("/cadastro.html")
def pagina_cadastro():
    return abrir_pagina("cadastro.html")


@app.get("/login.html")
def pagina_login():
    return abrir_pagina("login.html")


# ==========================================
# PÁGINAS PROTEGIDAS
# ==========================================

@app.get("/dashboard.html")
def pagina_dashboard(request: Request):
    return pagina_protegida(request, "dashboard.html")


@app.get("/pix.html")
def pagina_pix(request: Request):
    return pagina_protegida(request, "pix.html")


@app.get("/cartoes.html")
def pagina_cartoes(request: Request):
    return pagina_protegida(request, "cartoes.html")


@app.get("/extrato.html")
def pagina_extrato(request: Request):
    return pagina_protegida(request, "extrato.html")


@app.get("/investimentos.html")
def pagina_investimentos(request: Request):
    return pagina_protegida(request, "investimentos.html")


@app.get("/pagamentos.html")
def pagina_pagamentos(request: Request):
    return pagina_protegida(request, "pagamentos.html")


@app.get("/suporte.html")
def pagina_suporte(request: Request):
    return pagina_protegida(request, "suporte.html")


@app.get("/configuracoes.html")
def pagina_configuracoes(request: Request):
    return pagina_protegida(request, "configuracoes.html")


# ==========================================
# CADASTRO DE CLIENTES
# ==========================================

@app.post("/clientes", status_code=201)
def cadastrar_cliente(cliente: Cliente):
    nome = cliente.nome.strip()
    email = str(cliente.email).strip().lower()

    if not nome:
        raise HTTPException(
            status_code=400,
            detail="Informe seu nome."
        )

    if len(cliente.senha) < 8:
        raise HTTPException(
            status_code=400,
            detail="A senha deve ter pelo menos 8 caracteres."
        )

    try:
        senha_protegida = password_hash.hash(cliente.senha)

    except Exception:
        logger.exception("Erro ao proteger a senha")
        raise HTTPException(
            status_code=503,
            detail="Não foi possível processar a senha."
        )

    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO clientes
                    (nome, email, senha_hash)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (nome, email, senha_protegida)
                )

                novo_id = cursor.fetchone()[0]

    except UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail="Este e-mail já está cadastrado."
        )

    except Exception:
        logger.exception("Erro no banco durante cadastro")
        raise HTTPException(
            status_code=503,
            detail="Não foi possível cadastrar o cliente."
        )

    with conectar() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("INSERT INTO contas (cliente_id, saldo) VALUES (%s, 0) ON CONFLICT (cliente_id) DO NOTHING", (novo_id,))

    return {
        "mensagem": "Cliente cadastrado com sucesso!",
        "id": novo_id,
        "nome": nome,
        "email": email
    }


# ==========================================
# LOGIN DO CLIENTE
# ==========================================

@app.post("/login")
def fazer_login(dados: DadosLogin, response: Response):
    email = str(dados.email).strip().lower()

    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, nome, senha_hash
                    FROM clientes
                    WHERE LOWER(email) = %s
                    """,
                    (email,)
                )

                cliente = cursor.fetchone()

    except Exception:
        logger.exception("Erro no banco durante login")
        raise HTTPException(
            status_code=503,
            detail="Não foi possível consultar sua conta."
        )

    if cliente is None:
        raise HTTPException(
            status_code=401,
            detail="E-mail ou senha incorretos."
        )

    id_cliente, nome, senha_salva = cliente

    try:
        senha_correta = password_hash.verify(
            dados.senha,
            senha_salva
        )

    except Exception:
        logger.exception("Erro ao verificar senha")
        raise HTTPException(
            status_code=503,
            detail="Não foi possível verificar sua senha."
        )

    if not senha_correta:
        raise HTTPException(
            status_code=401,
            detail="E-mail ou senha incorretos."
        )

    try:
        token = criar_token(id_cliente)

    except Exception:
        logger.exception("Erro ao criar token JWT")
        raise HTTPException(
            status_code=503,
            detail=(
                "Não foi possível iniciar a sessão. "
                "Verifique a configuração JWT."
            )
        )

    response.set_cookie(
        key="neobank_sessao",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=1800,
        path="/"
    )

    return {
        "mensagem": "Login realizado com sucesso!",
        "id": id_cliente,
        "nome": nome
    }


# ==========================================
# CONSULTAR CLIENTE AUTENTICADO
# ==========================================

@app.get("/clientes/me")
def meus_dados(request: Request):
    cliente_id = obter_cliente_autenticado(request)

    try:
        with conectar() as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, nome, email
                    FROM clientes
                    WHERE id = %s
                    """,
                    (cliente_id,)
                )

                cliente = cursor.fetchone()

    except Exception:
        logger.exception("Erro ao consultar cliente")
        raise HTTPException(
            status_code=503,
            detail="Não foi possível consultar seus dados."
        )

    if cliente is None:
        raise HTTPException(
            status_code=404,
            detail="Cliente não encontrado."
        )

    return {
        "id": cliente[0],
        "nome": cliente[1],
        "email": cliente[2]
    }


# ==========================================
# LOGOUT
# ==========================================

@app.post("/logout")
def fazer_logout(response: Response):
    response.delete_cookie(
        key="neobank_sessao",
        path="/",
        samesite="lax"
    )

    return {
        "mensagem": "Você saiu da sua conta."
    }


# SALDO REAL DA CONTA FICTÍCIA
@app.get("/conta/saldo")
def consultar_saldo(request: Request):
    cliente_id = obter_cliente_autenticado(request)
    with conectar() as db:
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO contas (cliente_id, saldo) VALUES (%s, 0) ON CONFLICT (cliente_id) DO NOTHING", (cliente_id,))
            cursor.execute("SELECT saldo FROM contas WHERE cliente_id=%s", (cliente_id,))
            saldo = cursor.fetchone()[0]
    return {"saldo": float(saldo), "moeda": "BRL"}
