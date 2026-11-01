"""Execute com: python inicializar_banco.py (depois de configurar .env)."""
from backend.funcionalidades import preparar
if __name__=='__main__':
    preparar()
    print('Tabelas NeoBank criadas e contas existentes verificadas.')
