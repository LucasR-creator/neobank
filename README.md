# NeoBank — versão integrada de demonstração

## Funcionalidades

- Cadastro e login JWT com cookie HTTP-only, perfil e logout.
- Dashboard: saldo e movimentações consultados no PostgreSQL.
- Crédito fictício local para testes, limitado a R$ 1.000 por operação, habilitado com `NEOBANK_DEMO_CREDIT=1`. **Desative para qualquer uso compartilhado.**
- Pix interno simulado entre **duas contas NeoBank cadastradas**. A operação é atômica no PostgreSQL, exige saldo e grava extrato de ambas as contas.
- Pagamentos fictícios (boleto e recarga), debitando saldo fictício e registrando extrato.
- Extrato consultável, filtros e exportação CSV.
- Cartão virtual ilustrativo com preferências de bloqueio, compras online e limite salvas no banco.
- Simulador de investimentos (sem compra de ativos) e metas salvas no banco.
- Configurações: consultar e alterar nome do cliente.
- Suporte: perguntas frequentes e chamados registrados no banco.

## Observações e limites

O visual original da página inicial, login, cadastro e dashboard foi preservado. As páginas de operações receberam interface unificada para funcionar com a API. O gráfico do Dashboard e o cartão são ilustrativos. Os botões de investimentos que representam cálculos não movimentam saldo. Não há verificação de e-mail, recuperação de senha, 2FA, proteção CSRF, HTTPS, auditoria bancária, limitação de taxa nem requisitos de produção. Não publique esta aplicação na internet como banco real.

Se surgir `Autenticação temporariamente indisponível`, verifique a chave `NEOBANK_JWT_SECRET` no `.env` e reinicie o servidor. Após trocar a chave, faça login novamente. Se o saldo falhar, teste `/api/status-banco` e execute `python inicializar_banco.py`.
