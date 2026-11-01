from backend.database import conectar

def criar_tabela_contas():
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS contas (
                    id SERIAL PRIMARY KEY,
                    cliente_id INTEGER NOT NULL UNIQUE,
                    saldo NUMERIC(15, 2) NOT NULL DEFAULT 0.00,

                    CONSTRAINT fk_conta_cliente
                        FOREIGN KEY (cliente_id)
                        REFERENCES clientes(id),

                    CONSTRAINT saldo_nao_negativo
                        CHECK (saldo >= 0)
                )
            """)

        conexao.commit()
        print("Tabela de contas criada com sucesso!")

    except Exception as erro:
        conexao.rollback()
        print("Erro ao criar tabela:", erro)

    finally:
        conexao.close()


criar_tabela_contas()