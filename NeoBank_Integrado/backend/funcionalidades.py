"""Operações exclusivamente simuladas. Sem integração bancária real."""
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from psycopg.rows import dict_row
from backend.database import conectar
from backend.auth import verificar_token

router=APIRouter(prefix='/api')
log=logging.getLogger('uvicorn.error')

class Transferencia(BaseModel):
    destinatario_email: str
    valor: str
    descricao: str = ''
class Pagamento(BaseModel):
    tipo: str
    referencia: str
    valor: str
class Meta(BaseModel):
    nome: str = Field(min_length=2,max_length=100)
    objetivo: str
class Perfil(BaseModel):
    nome: str = Field(min_length=2,max_length=120)
class Cartao(BaseModel):
    bloqueado: bool
    compras_online: bool
    limite: int = Field(ge=500,le=10000)
class Chamado(BaseModel):
    assunto: str = Field(min_length=3,max_length=100)
    mensagem: str = Field(min_length=10,max_length=1000)

def dinheiro(valor):
    try:
        d=Decimal(str(valor).replace(',','.'))
        if not d.is_finite() or d<=0 or d>Decimal('1000000.00') or d.as_tuple().exponent < -2:
            raise ValueError()
        return d
    except (InvalidOperation,ValueError):
        raise HTTPException(422,'Valor inválido. Use até duas casas decimais.')

def cliente(request:Request):
    token=request.cookies.get('neobank_sessao')
    if not token: raise HTTPException(401,'Faça login para continuar.')
    try: return verificar_token(token)
    except RuntimeError: raise HTTPException(503,'Configure NEOBANK_JWT_SECRET no arquivo .env.')

def garantir_conta(cur, cid):
    cur.execute('INSERT INTO contas (cliente_id,saldo) VALUES (%s,0) ON CONFLICT (cliente_id) DO NOTHING',(cid,))

def preparar():
    with conectar() as db:
        with db.cursor() as cur:
            cur.execute('''CREATE TABLE IF NOT EXISTS clientes (id SERIAL PRIMARY KEY, nome TEXT NOT NULL, email TEXT NOT NULL UNIQUE, senha_hash TEXT NOT NULL)''')
            cur.execute('''CREATE TABLE IF NOT EXISTS contas (id SERIAL PRIMARY KEY, cliente_id INTEGER NOT NULL UNIQUE REFERENCES clientes(id), saldo NUMERIC(15,2) NOT NULL DEFAULT 0 CHECK(saldo>=0))''')
            cur.execute('''INSERT INTO contas(cliente_id,saldo) SELECT id,0 FROM clientes ON CONFLICT(cliente_id) DO NOTHING''')
            cur.execute('''CREATE TABLE IF NOT EXISTS movimentos (id BIGSERIAL PRIMARY KEY, cliente_id INTEGER NOT NULL REFERENCES clientes(id), tipo VARCHAR(20) NOT NULL, categoria VARCHAR(30) NOT NULL, descricao TEXT NOT NULL, valor NUMERIC(15,2) NOT NULL CHECK(valor>0), criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW())''')
            cur.execute('''CREATE TABLE IF NOT EXISTS preferencias_cartao (cliente_id INTEGER PRIMARY KEY REFERENCES clientes(id), bloqueado BOOLEAN NOT NULL DEFAULT FALSE, compras_online BOOLEAN NOT NULL DEFAULT TRUE, limite INTEGER NOT NULL DEFAULT 3000)''')
            cur.execute('''CREATE TABLE IF NOT EXISTS metas (id BIGSERIAL PRIMARY KEY, cliente_id INTEGER NOT NULL REFERENCES clientes(id), nome VARCHAR(100) NOT NULL, objetivo NUMERIC(15,2) NOT NULL CHECK(objetivo>0), criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW())''')
            cur.execute('''CREATE TABLE IF NOT EXISTS chamados (id BIGSERIAL PRIMARY KEY, cliente_id INTEGER NOT NULL REFERENCES clientes(id), assunto VARCHAR(100) NOT NULL, mensagem TEXT NOT NULL, criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW())''')

@router.get('/resumo')
def resumo(cid:int=Depends(cliente)):
    with conectar() as db:
        with db.cursor(row_factory=dict_row) as cur:
            garantir_conta(cur,cid)
            cur.execute('SELECT saldo FROM contas WHERE cliente_id=%s',(cid,)); saldo=cur.fetchone()['saldo']
            cur.execute("SELECT tipo,COALESCE(SUM(valor),0) AS total FROM movimentos WHERE cliente_id=%s AND criado_em>=date_trunc('month',now()) GROUP BY tipo",(cid,))
            totais={r['tipo']:float(r['total']) for r in cur.fetchall()}
            cur.execute('SELECT id,tipo,categoria,descricao,valor,criado_em FROM movimentos WHERE cliente_id=%s ORDER BY id DESC LIMIT 5',(cid,))
            return {'saldo':float(saldo),'entradas':totais.get('entrada',0),'saidas':totais.get('saida',0),'movimentos':[{**r,'valor':float(r['valor']),'criado_em':r['criado_em'].isoformat()} for r in cur.fetchall()]}

@router.get('/movimentos')
def movimentos(cid:int=Depends(cliente)):
    with conectar() as db:
        with db.cursor(row_factory=dict_row) as cur:
            cur.execute('SELECT id,tipo,categoria,descricao,valor,criado_em FROM movimentos WHERE cliente_id=%s ORDER BY id DESC LIMIT 300',(cid,))
            return [{**r,'valor':float(r['valor']),'criado_em':r['criado_em'].isoformat()} for r in cur.fetchall()]

@router.post('/pix')
def pix(data:Transferencia,cid:int=Depends(cliente)):
    valor=dinheiro(data.valor)
    email=data.destinatario_email.strip().lower()
    if '@' not in email or len(email)>254: raise HTTPException(422,'Informe o e-mail cadastrado do destinatário.')
    if len(data.descricao)>100: raise HTTPException(422,'Descrição muito longa.')
    with conectar() as db:
        with db.cursor() as cur:
            cur.execute('SELECT id,nome FROM clientes WHERE lower(email)=%s',(email,)); dest=cur.fetchone()
            if not dest: raise HTTPException(404,'Destinatário não encontrado. Use outro cliente cadastrado no NeoBank.')
            did,nome=dest
            if did==cid: raise HTTPException(400,'Não é permitido transferir para a própria conta.')
            garantir_conta(cur,cid);garantir_conta(cur,did)
            cur.execute('SELECT cliente_id,saldo FROM contas WHERE cliente_id IN (%s,%s) ORDER BY cliente_id FOR UPDATE',(cid,did))
            saldos=dict(cur.fetchall())
            if saldos[cid]<valor: raise HTTPException(400,'Saldo insuficiente para a transferência.')
            cur.execute('UPDATE contas SET saldo=saldo-%s WHERE cliente_id=%s',(valor,cid))
            cur.execute('UPDATE contas SET saldo=saldo+%s WHERE cliente_id=%s',(valor,did))
            descricao=data.descricao.strip() or 'Transferência simulada'
            cur.execute('INSERT INTO movimentos(cliente_id,tipo,categoria,descricao,valor) VALUES (%s,%s,%s,%s,%s)',(cid,'saida','pix',f'Pix para {nome} · {descricao}',valor))
            cur.execute('INSERT INTO movimentos(cliente_id,tipo,categoria,descricao,valor) VALUES (%s,%s,%s,%s,%s)',(did,'entrada','pix',f'Pix recebido · {descricao}',valor))
    return {'mensagem':'Pix fictício realizado com sucesso.','destinatario':nome,'valor':float(valor)}

@router.post('/pagamentos')
def pagar(data:Pagamento,cid:int=Depends(cliente)):
    valor=dinheiro(data.valor)
    if data.tipo not in ('boleto','recarga'):raise HTTPException(422,'Tipo de pagamento inválido.')
    if not (3<=len(data.referencia.strip())<=100):raise HTTPException(422,'Referência inválida.')
    with conectar() as db:
        with db.cursor() as cur:
            garantir_conta(cur,cid)
            cur.execute('SELECT saldo FROM contas WHERE cliente_id=%s FOR UPDATE',(cid,))
            if cur.fetchone()[0]<valor:raise HTTPException(400,'Saldo insuficiente.')
            cur.execute('UPDATE contas SET saldo=saldo-%s WHERE cliente_id=%s',(valor,cid))
            cur.execute('INSERT INTO movimentos(cliente_id,tipo,categoria,descricao,valor) VALUES (%s,%s,%s,%s,%s)',(cid,'saida',data.tipo,f'{data.tipo.title()} simulado · {data.referencia.strip()}',valor))
    return {'mensagem':'Pagamento fictício registrado.','valor':float(valor)}

@router.get('/cartao')
def ver_cartao(cid:int=Depends(cliente)):
    with conectar() as db:
        with db.cursor(row_factory=dict_row) as cur:
            cur.execute('INSERT INTO preferencias_cartao(cliente_id) VALUES (%s) ON CONFLICT DO NOTHING',(cid,))
            cur.execute('SELECT bloqueado,compras_online,limite FROM preferencias_cartao WHERE cliente_id=%s',(cid,))
            return cur.fetchone()

@router.put('/cartao')
def alterar_cartao(data:Cartao,cid:int=Depends(cliente)):
    with conectar() as db:
        with db.cursor() as cur:
            cur.execute('INSERT INTO preferencias_cartao(cliente_id,bloqueado,compras_online,limite) VALUES (%s,%s,%s,%s) ON CONFLICT(cliente_id) DO UPDATE SET bloqueado=EXCLUDED.bloqueado,compras_online=EXCLUDED.compras_online,limite=EXCLUDED.limite',(cid,data.bloqueado,data.compras_online,data.limite))
    return {'mensagem':'Preferências do cartão fictício salvas.'}

@router.get('/metas')
def listar_metas(cid:int=Depends(cliente)):
    with conectar() as db:
        with db.cursor(row_factory=dict_row) as cur:
            cur.execute('SELECT id,nome,objetivo FROM metas WHERE cliente_id=%s ORDER BY id DESC',(cid,))
            return [{**r,'objetivo':float(r['objetivo'])} for r in cur.fetchall()]

@router.post('/metas')
def criar_meta(data:Meta,cid:int=Depends(cliente)):
    valor=dinheiro(data.objetivo)
    with conectar() as db:
        with db.cursor() as cur:
            cur.execute('INSERT INTO metas(cliente_id,nome,objetivo) VALUES (%s,%s,%s)',(cid,data.nome.strip(),valor))
    return {'mensagem':'Meta salva.'}

@router.put('/perfil')
def perfil(data:Perfil,cid:int=Depends(cliente)):
    with conectar() as db:
        with db.cursor() as cur:
            cur.execute('UPDATE clientes SET nome=%s WHERE id=%s',(data.nome.strip(),cid))
    return {'mensagem':'Nome atualizado.'}

@router.post('/chamados')
def chamado(data:Chamado,cid:int=Depends(cliente)):
    with conectar() as db:
        with db.cursor() as cur:
            cur.execute('INSERT INTO chamados(cliente_id,assunto,mensagem) VALUES (%s,%s,%s)',(cid,data.assunto,data.mensagem))
    return {'mensagem':'Solicitação registrada no NeoBank fictício.'}

@router.get('/chamados')
def listar_chamados(cid:int=Depends(cliente)):
    with conectar() as db:
        with db.cursor(row_factory=dict_row) as cur:
            cur.execute('SELECT id,assunto,mensagem,criado_em FROM chamados WHERE cliente_id=%s ORDER BY id DESC',(cid,))
            return [{**r,'criado_em':r['criado_em'].isoformat()} for r in cur.fetchall()]

class CreditoTeste(BaseModel):
    valor: str

@router.post('/credito-teste')
def credito_teste(data:CreditoTeste,cid:int=Depends(cliente)):
    """Apenas para testes locais. Não usar em um sistema real."""
    import os
    if os.getenv('NEOBANK_DEMO_CREDIT','0')!='1':
        raise HTTPException(403,'Crédito de teste desativado no .env.')
    valor=dinheiro(data.valor)
    if valor>Decimal('1000'):raise HTTPException(422,'Limite por operação de teste: R$ 1.000,00.')
    with conectar() as db:
        with db.cursor() as cur:
            garantir_conta(cur,cid)
            cur.execute('UPDATE contas SET saldo=saldo+%s WHERE cliente_id=%s',(valor,cid))
            cur.execute('INSERT INTO movimentos(cliente_id,tipo,categoria,descricao,valor) VALUES (%s,%s,%s,%s,%s)',(cid,'entrada','teste','Crédito fictício de teste',valor))
    return {'mensagem':'Crédito fictício registrado.','valor':float(valor)}
