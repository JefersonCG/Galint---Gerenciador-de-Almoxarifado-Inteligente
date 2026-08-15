# README TECNICO - Desenvolvimento e Implantacao de Backup + ConversionEngine

## 1. Objetivo

Este guia descreve como desenvolver, validar, implantar e operar um sistema de backup e restauracao assistida baseado na arquitetura atual do GALINT.

Escopo deste documento:
- Backup SQL PostgreSQL (pg_dump/psql)
- Pacote completo (.zip) com dump SQL + manifest + artefatos de disco
- Pipeline de analise e implantacao via ConversionEngine
- Restore com progresso, lock operacional e trilha auditavel
- Rotina de homologacao e testes automatizados

Nao e objetivo deste documento:
- Definir TEF, SMS, WhatsApp ou outros modulos nao ligados a backup/conversao
- Cobrir restore manual fora do fluxo oficial

---

## 2. Arquitetura de referencia

### 2.1 Componentes principais

- Service de backup:
  - galint_flask/services/backup.py
- Service de conversion:
  - galint_flask/services/conversion_engine.py
- Jobs de restore em background:
  - galint_flask/services/backup_restore_jobs.py
- Camada web de configuracoes/rotas:
  - galint_flask/views/pages.py
- Interface backup:
  - galint_flask/templates/config_backup.html
- Interface conversion:
  - galint_flask/templates/config_conversionengine.html

### 2.2 Fluxo macro

1. Operador gera backup SQL ou pacote completo.
2. Arquivo e listado em instance/backups.
3. Operador envia artefato ao ConversionEngine.
4. ConversionEngine faz staging isolado e analise estrutural.
5. Engine gera pacote tecnico e, quando seguro, artefato apto para implantacao.
6. Implantacao aciona restore em job dedicado com progresso.
7. Em pacote completo compativel, restore inclui SQL + ativos externos.

### 2.3 Principio arquitetural

- O restore oficial deve passar por staging e analise do ConversionEngine.
- Backup completo nao deve virar restore destrutivo direto sem validacao.
- Conversao deve ser conservadora: deploy direto so quando perfil estrutural e compativel.

---

## 3. Contratos e tipos de backup

### 3.1 Tipos suportados pelo BackupService

- database
  - gera somente dump SQL
- complete
  - gera ZIP com dump SQL + manifest.json + README interno + assets

Constantes relevantes no codigo:
- BackupService.DATABASE_BACKUP_KIND
- BackupService.COMPLETE_BACKUP_KIND
- BackupService.MANIFEST_SCHEMA_VERSION

### 3.2 Estrutura do pacote completo

Exemplo esperado:

```text
galint_backup_full_YYYYMMDD_HHMMSS.zip
  database/
    galint_backup_YYYYMMDD_HHMMSS.sql
  assets/
    static/uploads/...
    static/logo/...
    instance/barcodes/...
    instance/reports/...
    instance/network_settings.json
    instance/secret_key.txt
  manifest.json
  README_backup_completo.txt
```

### 3.3 Campos minimos do manifest

- backup_kind
- manifest_schema_version
- created_at
- app_version
- host
- database_dump.name
- database_dump.archive_path
- compatibility.minimum_app_version
- asset_entries[] com exists, size_bytes, sha256, criticality e group

---

## 4. Pre-requisitos de ambiente

## 4.1 Runtime

- Python 3.10+ (recomendado 3.11+)
- PostgreSQL instalado
- pg_dump e psql disponiveis
- Permissoes de leitura/escrita em instance/backups

### 4.2 Configuracao minima

- SQLALCHEMY_DATABASE_URI apontando para PostgreSQL
- BACKUP_PG_DUMP opcional
- BACKUP_PSQL opcional

### 4.3 Variaveis de ambiente suportadas

- GALINT_BACKUP_TIMEOUT_SECONDS / BACKUP_TIMEOUT_SECONDS
- GALINT_PG_CONNECT_TIMEOUT_SECONDS / PGCONNECT_TIMEOUT
- GALINT_PG_LOCK_TIMEOUT_MS / PG_LOCK_TIMEOUT_MS
- GALINT_PG_STATEMENT_TIMEOUT_MS / PG_STATEMENT_TIMEOUT_MS
- GALINT_RESTORE_CONNECTION_DRAIN_SECONDS / RESTORE_CONNECTION_DRAIN_SECONDS
- GALINT_RESTORE_MAINTENANCE_DB / RESTORE_MAINTENANCE_DB
- GALINT_BACKUP_RETENTION_DAYS / BACKUP_RETENTION_DAYS
- GALINT_BACKUP_RETENTION_COUNT / BACKUP_RETENTION_COUNT

---

## 5. Setup local de desenvolvimento

### 5.1 Preparar ambiente

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 5.2 Subir aplicacao

```powershell
$env:GALINT_DISABLE_BACKGROUND_SERVICES = "true"
python app.py
```

### 5.3 Verificar tela de backup e conversion

- Configuracoes -> Backup
- Configuracoes -> ConversionEngine

---

## 6. Rotas operacionais (camada web)

Rotas principais em galint_flask/views/pages.py:

- GET /configuracoes/backup
- POST /configuracoes/backup
- POST /configuracoes/restaurar
- POST /configuracoes/restaurar/iniciar
- GET /configuracoes/restaurar/status/<job_id>
- GET /configuracoes/conversionengine
- POST /configuracoes/conversionengine/iniciar
- POST /configuracoes/conversionengine/analisar-backup
- GET /configuracoes/conversionengine/status/<job_id>
- GET /configuracoes/conversionengine/download/<job_id>
- GET /configuracoes/conversionengine/pacote/<job_id>
- POST /configuracoes/conversionengine/implantar/<job_id>
- POST /configuracoes/backup/excluir

Observacoes:
- Rotas sensiveis exigem sessao admin.
- Existe autentificacao leve para endpoints JSON de restore/conversion.
- Restore e conversion rodam em job para nao bloquear request web.

---

## 7. Desenvolvimento do BackupService

### 7.1 Checklist tecnico para alterar backup.py

1. Nao quebrar create_backup(database).
2. Garantir compatibilidade para create_backup(complete).
3. Manter validacao de caminho seguro em _safe_backup_path.
4. Atualizar _read_backup_metadata quando alterar manifest.
5. Manter _apply_retention_policy apos criacao de backup.
6. Preservar restore com progresso e mensagens robustas.
7. Garantir rollback e mensagens claras em ValueError.

### 7.2 Regras de seguranca

- Bloquear path traversal por nome de backup.
- Aceitar somente sufixos .sql e .zip no restore.
- Validar entradas do ZIP antes de extractall.
- No restore de assets, limitar destinos a static/ e instance/.
- Nunca confiar em caminho vindo do cliente sem normalizacao.

### 7.3 Delta operacional pos-backup

O restore SQL com progresso utiliza captura/reaplicacao de delta para reduzir perda de movimentos recentes.

Regras:
- Captura antes do restore.
- Restore do dump.
- Reaplicacao do delta.
- Report de progresso em fases.

---

## 8. Desenvolvimento do ConversionEngine

### 8.1 Escopo atual do engine

- Entrada .sql, .zip (com .sql/.sqlite/.db), .sqlite/.db
- Staging isolado por job
- Profiling estrutural e volumetrico
- Score de compatibilidade com schema alvo do GALINT
- Artefatos de saida para analise/deploy

### 8.2 Passos internos do run_conversion

1. Validar origem.
2. Preparar staging isolado.
3. Perfil da origem (dump SQL ou SQLite).
4. Carregar schema alvo do SQLAlchemy metadata.
5. Resolver mapeamentos por nome e alias.
6. Calcular score e resumo de compatibilidade.
7. Gerar artefatos tecnicos e opcao de deploy quando permitido.

### 8.3 Regra de conservadorismo

Deploy direto somente quando resumo indicar deployable verdadeiro.

Se nao for deployable:
- manter somente pacote tecnico para analise
- retornar tarefas e gaps de compatibilidade

---

## 9. Pipeline de implantacao recomendado

### 9.1 Homologacao (obrigatoria)

1. Gerar backup completo do ambiente atual.
2. Executar validacao de restore em banco temporario.
3. Rodar ConversionEngine em artefato de teste.
4. Revisar score, mappings e tasks.
5. Registrar evidencias de teste.

Script util:

```powershell
python scripts/validate_backup_restore.py
```

### 9.2 Producoes controladas

1. Janela de manutencao aprovada.
2. Backup completo novo (timestamp da janela).
3. Envio ao ConversionEngine.
4. Validacao final e autorizacao admin.
5. Implantacao via endpoint de deploy.
6. Acompanhar job de restore ate status success.
7. Smoke test funcional (login, itens, entradas, saidas, relatorios).

### 9.3 Rollback

1. Selecionar backup imediatamente anterior.
2. Iniciar restore com progresso.
3. Revalidar consistencia de dados operacionais.
4. Documentar causa raiz e correcao.

---

## 10. Observabilidade e operacao

### 10.1 O que monitorar

- Tempo total de backup
- Tempo total de restore
- Tamanho de dumps/pacotes
- Quantidade de falhas por etapa
- Score medio de compatibilidade no ConversionEngine
- Quantidade de deploys bloqueados

### 10.2 Logs minimos

- Inicio/fim de backup
- Tipo de backup gerado
- Manifest version
- Inicio/fim de restore
- Origem do deploy (sql_dump/zip_package/sqlite)
- Erros com stack trace tecnico e mensagem operacional amigavel

---

## 11. Testes obrigatorios

### 11.1 Testes unitarios/integracao

- scripts/tests/test_backup_complete_package.py
  - garante ZIP completo e remocao de SQL intermediario

### 11.2 Testes de operacao

- scripts/validate_backup_restore.py
  - restaura em banco temporario e valida conectividade/tabelas

### 11.3 Cenarios que nao podem falhar

1. Backup SQL em ambiente valido PostgreSQL
2. Backup completo com manifest + assets
3. Restore SQL com progresso
4. Restore pacote completo com SQL + assets
5. Bloqueio de ZIP malicioso com path invalido
6. Delecao segura de backups
7. Conversao de backup existente para job do engine

---

## 12. Padrao de evolucao tecnica

### 12.1 Versao de manifest

Ao mudar estrutura do pacote:
- incrementar MANIFEST_SCHEMA_VERSION
- manter backward compatibility quando possivel
- incluir migracao/documentacao de leitura no ConversionEngine

### 12.2 Evolucoes recomendadas

1. Validacao automatica de restore periodica (drill)
2. Politica de RPO/RTO por ambiente
3. Assinatura criptografica de pacote
4. Criptografia de artefatos sensiveis em repouso
5. Integracao de checklist de release com backup valido obrigatorio

---

## 13. Checklist de implantacao em nova maquina

1. Instalar PostgreSQL e ferramentas pg_dump/psql.
2. Configurar SQLALCHEMY_DATABASE_URI.
3. Validar create_backup(database).
4. Validar create_backup(complete).
5. Validar list_backups na tela.
6. Validar abertura da tela de ConversionEngine.
7. Subir um job de analise de backup existente.
8. Validar download de pacote tecnico.
9. Validar restore em homologacao.
10. Aprovar entrada em producao.

---

## 14. Decisoes de seguranca obrigatorias

- Sem restore destrutivo fora do fluxo oficial.
- Sem leitura/escrita de caminhos fora de static/ e instance/ no restore de assets.
- Sem bypass de permissao admin para endpoints de backup/restore/deploy.
- Sem executar deploy direto quando score/summary nao autorizar.

---

## 15. Referencias de codigo

- galint_flask/services/backup.py
- galint_flask/services/conversion_engine.py
- galint_flask/views/pages.py
- galint_flask/templates/config_backup.html
- scripts/validate_backup_restore.py
- scripts/tests/test_backup_complete_package.py
- docs/operacao/conversionengine-backup.md

---

## 16. Conclusao

Para reproduzir um sistema como o atual de Backup + ConversionEngine, a chave e manter o modelo de operacao conservador:

- backup confiavel e validado
- staging isolado para analise
- deploy controlado por compatibilidade
- restore com progresso e seguranca
- trilha operacional clara para homologacao e producao

Esse desenho reduz risco de perda de dados e evita restauracoes destrutivas fora de governanca tecnica.
