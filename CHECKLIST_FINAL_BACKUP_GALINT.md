# Checklist Final de Backup GALINT

## Objetivo

Fechar a validação operacional do backup do GALINT antes de tratar o fluxo como pronto para uso recorrente em produção.

## Pré-requisitos

1. `GALINT_DATABASE_URI` configurada corretamente.
2. `pg_dump` e `psql` encontrados no ambiente.
3. `BACKUP_RETENTION_DAYS` e `BACKUP_RETENTION_COUNT` definidos conforme a política do ambiente.
4. Acesso ao PostgreSQL com permissão para criar um banco temporário de homologação.

## Homologação Técnica

1. Abrir a tela de backup e conferir o diagnóstico de prontidão.
2. Gerar um backup SQL.
3. Executar a homologação isolada com `python scripts/validate_backup_restore.py`.
4. Confirmar que o restore conclui sem erro.
5. Conferir que o banco temporário é removido ao final.

## Go-live Controlado

1. Registrar qual backup foi homologado.
2. Aprovar a janela de manutenção.
3. Fazer um backup de segurança imediatamente antes de qualquer implantação.
4. Manter o rollback documentado e testado.
5. Não usar um ZIP ou SQL sem homologação registrada.

## Critério de Finalização

O plano fica operacionalmente fechado quando:

1. o diagnóstico mostra ambiente pronto;
2. o backup SQL foi gerado com sucesso;
3. a restauração isolada foi validada;
4. a retenção está ativa;
5. o procedimento de go-live e rollback está documentado.