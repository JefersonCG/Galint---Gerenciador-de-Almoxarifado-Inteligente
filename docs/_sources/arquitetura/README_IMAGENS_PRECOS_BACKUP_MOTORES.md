# README - Imagens, API de Precos, Backup e Motores GALINT

Este README documenta como funcionam quatro frentes operacionais do GALINT e como aplica-las corretamente:

1. pesquisa e aplicacao de imagens dos itens;
2. API de sugestao de precos de reposicao;
3. sistema de backup SQL e backup completo;
4. motores de processamento: `BackupService`, `ConversionEngine`, jobs de restore e motores auxiliares de estoque/conversao.

Arquivos principais:

- `galint_flask/services/item_foto_service.py`
- `galint_flask/services/price_suggestion_service.py`
- `galint_flask/services/backup.py`
- `galint_flask/services/backup_restore_jobs.py`
- `galint_flask/services/conversion_engine.py`
- `galint_flask/services/inventory_engine.py`
- `galint_flask/services/unit_conversion_engine.py`
- `galint_flask/views/inventory.py`
- `galint_flask/views/nf.py`
- `galint_flask/views/pages.py`
- `galint_flask/templates/inventory/list.html`
- `galint_flask/templates/inventory/form.html`
- `galint_flask/templates/nf/index.html`
- `galint_flask/templates/config_backup.html`
- `galint_flask/templates/config_conversionengine.html`

## 1. Pesquisa e aplicacao de imagens

### Ideia central

O GALINT nao faz scraping automatico de imagens de produtos por conta propria. O fluxo atual e assistido:

1. a tela monta uma consulta com descricao, marca, categoria e unidade;
2. o usuario abre Google/Bing ou copia a busca;
3. o usuario escolhe uma imagem publica e cola a URL;
4. o backend valida, baixa, processa e salva a imagem no padrao interno;
5. o item passa a apontar para `foto_path`.

Isso evita depender de provedores instaveis, reduz risco de captcha/bloqueio e deixa a decisao visual com o operador.

### Onde aparece na UI

Existem tres superficies principais:

1. Listagem de inventario:
   - `galint_flask/templates/inventory/list.html`
   - modal `#photoAssistantModal`

2. Formulario de item:
   - `galint_flask/templates/inventory/form.html`
   - modal `#modalFotoUrl`

3. Cadastro de item pela tela de documentos fiscais:
   - `galint_flask/templates/nf/index.html`
   - modal `#docfPhotoAssistantModal`
   - campo hidden `foto_url`

Na tela de NF, o botao de busca de imagem do novo item so deve aparecer quando existe contexto minimo: descricao, categoria e marca preenchidas. O modal prepara `foto_url`; o download real acontece no fechamento/cadastro do item.

### Como a URL vira arquivo interno

Servico: `ItemFotoService`.

Metodo principal:

```python
ItemFotoService.download_foto_from_url(image_url, codigo_item)
```

Fluxo:

1. Recebe a URL.
2. Valida seguranca com `_ensure_url_safe`:
   - aceita somente `http` e `https`;
   - bloqueia `localhost`, loopback e hosts privados;
   - bloqueia host que nao resolve de forma segura.
3. Faz `requests.get` com timeout de 10 segundos.
4. Rejeita HTTP 400+.
5. Rejeita `Content-Type` que nao comeca com `image/` quando o header existe.
6. Baixa em streaming com limite de 6 MB.
7. Processa bytes da imagem com PIL.
8. Corrige orientacao EXIF.
9. Converte para canvas quadrado 800x800 com fundo branco e padding.
10. Salva comprimido em WebP, tentando ficar ate 200 KB.
11. Se WebP falhar, cai para JPEG.
12. Retorna caminho relativo como:

```text
uploads/itens/<codigo>_<timestamp>.webp
```

### Regras de arquivo

Upload manual usa:

```python
ItemFotoService.upload_foto(file, codigo_item)
```

Validacoes:

- extensoes aceitas: `png`, `jpg`, `jpeg`, `jpe`, `webp`, `gif`;
- tamanho maximo de upload: 5 MB;
- nome seguro via `secure_filename`;
- destino: `galint_flask/static/uploads/itens`.

Observacao: upload manual salva o arquivo original com nome unico. Download por URL passa pelo processamento/compressao padronizado.

### Endpoints de aplicacao de foto

Rotas em `galint_flask/views/inventory.py`:

```text
POST /itens/foto/url
POST /itens/foto/upload
POST /itens/<codigo>/foto/url
```

Uso recomendado para URL global:

```http
POST /itens/foto/url
Content-Type: application/json

{
  "codigo": "CODIGO_ITEM",
  "image_url": "https://site-publico/imagem.jpg"
}
```

Resposta esperada:

```json
{
  "success": true,
  "message": "Foto atualizada",
  "foto_path": "uploads/itens/CODIGO_YYYYMMDD_HHMMSS.webp"
}
```

Se o item ja tinha foto, o endpoint remove a foto anterior quando o novo caminho e diferente.

### Aplicacao em cadastro de item

No cadastro/edicao de item em `inventory.py`, quando `foto_url` vem no payload:

```python
foto_path = ItemFotoService.download_foto_from_url(payload["foto_url"], codigo)
```

No cadastro de novo item por NF, `nf.py` tambem chama:

```python
ItemFotoService.download_foto_from_url(foto_url, codigo)
```

Se a foto falhar na NF, o sistema mostra aviso, mas nao precisa bloquear obrigatoriamente todo o cadastro do item.

### Invariantes de imagem

1. Banco guarda apenas caminho relativo em `foto_path`.
2. Arquivo fisico fica em `static/uploads/itens`.
3. URL precisa ser publica; host privado e bloqueado.
4. Download por URL sempre deve passar pelo `ItemFotoService`.
5. Upload e URL exigem usuario admin nas rotas de inventario.
6. Foto antiga deve ser removida ao substituir, quando aplicavel.
7. A UI deve preparar busca; o backend deve validar e persistir.

## 2. API de precos de reposicao

### Ideia central

O preco de reposicao e uma sugestao de mercado para itens sem comprovante fiscal suficiente. Ele nao substitui NF/cupom. O sistema busca sugestoes, o usuario escolhe/confirma, e so entao o valor e salvo no item.

Servico principal:

```python
price_suggestion_service.get_replacement_suggestions(query, uf, limit)
```

Classe de retorno por sugestao:

```python
PriceSuggestion
```

Campos retornados:

- `source`
- `title`
- `price`
- `currency`
- `url`
- `uf`
- `uf_raw`
- dados do vendedor quando disponiveis.

### Provedores e fallback

A ordem real de busca e:

1. Mercado Livre API:
   - endpoint `https://api.mercadolibre.com/sites/MLB/search`;
   - pode usar token via env:
     - `MERCADO_LIVRE_ACCESS_TOKEN`
     - `MERCADOLIVRE_ACCESS_TOKEN`
     - `MELI_ACCESS_TOKEN`
     - `ML_ACCESS_TOKEN`
   - se anonimo der 401/403, registra indisponibilidade.

2. Mercado Livre Web:
   - abre `https://lista.mercadolivre.com.br/<query>`;
   - extrai objetos `POLYCARD` do HTML;
   - captura titulo, preco e URL.

3. Telhanorte:
   - endpoint VTEX publico:

```text
https://www.telhanorte.com.br/api/catalog_system/pub/products/search/<query>
```

4. Busca web publica:
   - pesquisa DuckDuckGo HTML com `query preco R$ comprar`;
   - abre resultados;
   - tenta extrair preco por JSON-LD, meta tags, `product:price:amount`, `itemprop=price`, `price`, `priceAmount`, `salePrice` ou padrao `R$`.

O resultado final passa por deduplicacao por titulo, URL sem querystring e preco em centavos.

### Cache

O servico tem cache em memoria por 1 hora:

```text
(query normalizada, uf, limit) -> payload
```

Esse cache nao e persistido em banco e some ao reiniciar o servidor.

### Estatisticas retornadas

A resposta inclui:

```json
{
  "query": "cimento cp ii 50 kg",
  "uf": "SP",
  "suggestions": [],
  "stats": {
    "count": 0,
    "median": null,
    "min": null,
    "max": null
  },
  "providers": []
}
```

Quando existem precos, `stats.median`, `stats.min` e `stats.max` sao calculados a partir das sugestoes validas.

### Endpoint por item

Rota:

```text
GET /itens/<codigo>/precos/reposicao/sugestoes?q=<termo>&uf=<UF>&unit=<unidade>
```

Fluxo:

1. Carrega o item.
2. Usa `q` ou descricao do item.
3. Enriquece a busca com unidade/embalagem via `_enrich_replacement_price_query`.
4. Resolve UF.
5. Chama `price_suggestion_service`.
6. Retorna sugestoes e estatisticas.

### Endpoint por categoria/lote

Rota:

```text
GET /itens/categoria/<categoria>/precos/reposicao/lote?item_limit=10&suggestion_limit=10&uf=SP
```

Regras:

- exige admin;
- pega no maximo 10 itens por chamada;
- entra apenas item sem `preco_reposicao_unitario` valido;
- bloqueia itens com base fiscal ou documento de compra;
- monta query por item;
- busca em paralelo com ate 4 workers;
- retorna resumo com `pending_total`, `shown`, `has_more`.

Esse e o fluxo usado pelo modal de lote por categoria na listagem de inventario.

### Endpoint manual pela tela de NF

Rota:

```text
GET /nf/api/precos/reposicao/sugestoes?q=<termo>&uf=<UF>&codigo=<codigo>
```

Uso principal: lancamento manual/sem NF na tela de documentos fiscais.

Se `q` nao vier, o endpoint tenta montar consulta com:

- item existente;
- descricao;
- marca;
- embalagem;
- conteudo.

### Salvamento do preco

Rota:

```text
POST /itens/<codigo>/precos/reposicao
```

Payload esperado:

```json
{
  "preco_reposicao_unitario": 42.90,
  "preco_reposicao_fonte": "Mercado Livre",
  "preco_reposicao_uf": "SP",
  "preco_reposicao_query": "cimento cp ii 50 kg",
  "preco_reposicao_url": "https://...",
  "preco_reposicao_unidade_preco": "saco"
}
```

Fluxo:

1. Exige admin.
2. Valida item.
3. Valida preco positivo.
4. Resolve unidade do preco.
5. Normaliza o preco para unidade base com `normalize_item_price`.
6. Salva:
   - `preco_reposicao_unitario`
   - `preco_reposicao_unitario_base`
   - `preco_reposicao_unidade_preco`
   - `preco_reposicao_fator_base`
   - `preco_reposicao_fonte`
   - `preco_reposicao_uf`
   - `preco_reposicao_query`
   - `preco_reposicao_url`
   - `preco_reposicao_atualizado_em`
   - `preco_reposicao_atualizado_por`
7. Atualiza tambem `ultima_edicao_em` e `ultima_edicao_por`.

### Regra fiscal importante

A busca web de preco de reposicao so deve ser usada para item sem comprovacao fiscal suficiente.

O filtro `_replacement_price_no_fiscal_backing_filters` bloqueia itens que tenham:

- documento fiscal em `DocumentoEntradaEstoqueItem`;
- lancamento financeiro com `tipo_documento` fiscal;
- origem de valor `compra_nf` ou `compra_cupom`;
- `preco_compra_fonte` fiscal;
- NF, cupom, documento ou chave de acesso que indiquem compra comprovada.

Em resumo: se ha NF/cupom, a fonte de verdade e o documento fiscal. Se nao ha comprovante, a API web ajuda a preencher uma estimativa auditavel.

### Invariantes de preco

1. Sugestao nao salva nada sozinha.
2. Usuario/admin precisa confirmar o valor escolhido.
3. `preco_reposicao_unitario_base` e o valor normalizado para a base do item.
4. Query, fonte, UF e URL devem ser preservadas para auditoria.
5. Item com NF/cupom nao deve entrar na fila web de reposicao.
6. Mercado Livre pode falhar por anti-bot; fallback e esperado, nao excecao de negocio.

## 3. Sistema de backup

### Ideia central

O GALINT tem backup PostgreSQL-only na camada oficial `BackupService`.

Existem dois formatos:

1. backup SQL:
   - arquivo `.sql` gerado por `pg_dump`;
   - contem banco;
   - pode ser restaurado localmente ou enviado ao ConversionEngine.

2. pacote completo:
   - arquivo `.zip`;
   - contem dump SQL interno;
   - contem `manifest.json`;
   - contem `README_backup_completo.txt`;
   - contem artefatos de disco selecionados;
   - deve passar pelo ConversionEngine.

Pasta padrao:

```text
instance/backups
```

### Diagnostico de prontidao

Metodo:

```python
BackupService.diagnostic_report()
```

Checa:

- `SQLALCHEMY_DATABASE_URI` configurada;
- `pg_dump` disponivel;
- `psql` disponivel;
- pasta de backups gravavel;
- conexao com PostgreSQL;
- espaco em disco;
- politica de retencao.

A tela `Configurações > Backup` mostra esses checks antes de gerar backup.

### Resolucao de pg_dump e psql no Windows

O servico tenta resolver ferramentas em ordem:

1. comando configurado (`BACKUP_PG_DUMP` / `BACKUP_PSQL`);
2. `PATH` via `shutil.which`;
3. caminho absoluto configurado;
4. binario irmao no mesmo diretorio;
5. locais comuns no Windows:
   - `%ProgramFiles%\PostgreSQL\<versao>\bin`
   - `%ProgramFiles(x86)%\PostgreSQL\<versao>\bin`
   - `C:/PostgreSQL`
   - `C:/pgsql`

### Variaveis de ambiente uteis

```text
GALINT_BACKUP_TIMEOUT_SECONDS
BACKUP_TIMEOUT_SECONDS
GALINT_PG_CONNECT_TIMEOUT_SECONDS
PGCONNECT_TIMEOUT
GALINT_PG_LOCK_TIMEOUT_MS
PG_LOCK_TIMEOUT_MS
GALINT_PG_STATEMENT_TIMEOUT_MS
PG_STATEMENT_TIMEOUT_MS
GALINT_RESTORE_CONNECTION_DRAIN_SECONDS
RESTORE_CONNECTION_DRAIN_SECONDS
GALINT_RESTORE_MAINTENANCE_DB
RESTORE_MAINTENANCE_DB
GALINT_BACKUP_RETENTION_DAYS
BACKUP_RETENTION_DAYS
GALINT_BACKUP_RETENTION_COUNT
BACKUP_RETENTION_COUNT
```

### Como gerar backup SQL

Pela UI:

```text
Configuracoes > Backup > Gerar backup SQL
```

Pela rota:

```text
POST /configuracoes/backup
backup_kind=database
```

Servico:

```python
BackupService(current_app).create_backup(backup_kind="database")
```

Comando usado internamente:

```text
pg_dump --clean --if-exists --no-owner --no-privileges -h <host> -p <port> -U <usuario> -d <database> -f instance/backups/galint_backup_YYYYMMDD_HHMMSS.sql
```

O password vem da URL do banco e e colocado em `PGPASSWORD` apenas no ambiente do subprocesso.

### Como gerar pacote completo

Pela UI:

```text
Configuracoes > Backup > Gerar pacote completo
```

Pela rota:

```text
POST /configuracoes/backup
backup_kind=complete
```

Servico:

```python
BackupService(current_app).create_backup(backup_kind="complete")
```

Fluxo:

1. Gera um `.sql` temporario via `pg_dump`.
2. Coleta artefatos de disco.
3. Monta `manifest.json`.
4. Monta `README_backup_completo.txt`.
5. Cria `galint_backup_full_YYYYMMDD_HHMMSS.zip`.
6. Inclui o SQL em `database/<backup>.sql`.
7. Inclui assets em `assets/...`.
8. Apaga o `.sql` temporario, deixando o ZIP como artefato final.
9. Aplica politica de retencao.

### O que entra no pacote completo

Diretorios:

- `galint_flask/static/uploads` -> `assets/static/uploads`
- `galint_flask/static/logo` -> `assets/static/logo`
- `instance/barcodes` -> `assets/instance/barcodes`
- `instance/reports` -> `assets/instance/reports`

Arquivos:

- `instance/network_settings.json`
- `instance/secret_key.txt`

Metadados:

- `manifest.json`
- `README_backup_completo.txt`

### Manifesto do pacote completo

O `manifest.json` registra:

- versao do schema do manifesto;
- tipo do backup (`complete`);
- data de criacao;
- nome do pacote;
- versao do GALINT;
- compatibilidade minima;
- host de origem;
- `instance_path`;
- `project_root`;
- dump SQL interno com tamanho e SHA-256;
- resumo de assets;
- lista de arquivos incluidos/ausentes com criticidade e SHA-256.

### Restauracao de backup SQL

Servico:

```python
BackupService.restore_backup_with_progress(backup_name, reporter)
```

Fluxo para `.sql`:

1. valida o arquivo;
2. captura delta pos-backup quando habilitado;
3. restaura banco via `psql`;
4. reaplica movimentos pos-backup;
5. reporta progresso.

A restauracao tambem pode ser iniciada em background:

```text
POST /configuracoes/restaurar/iniciar
GET  /configuracoes/restaurar/status/<job_id>
```

O estado fica em memoria. Reiniciar o servidor limpa os jobs.

### Restauracao de pacote completo

Pacote completo deve passar pelo ConversionEngine.

Quando liberado para deploy direto, o pipeline faz:

1. valida ZIP;
2. bloqueia path traversal;
3. extrai em staging temporario;
4. le `manifest.json`;
5. localiza dump SQL interno;
6. restaura banco;
7. restaura assets declarados no manifesto;
8. copia assets apenas para destinos permitidos:
   - `galint_flask/static`
   - `instance`

Metodo:

```python
BackupService.restore_complete_package(package_path, reporter)
```

### Retencao

Apos criar backup, `BackupService` aplica politica de retencao conforme:

- dias (`BACKUP_RETENTION_DAYS` / `GALINT_BACKUP_RETENTION_DAYS`);
- quantidade maxima (`BACKUP_RETENTION_COUNT` / `GALINT_BACKUP_RETENTION_COUNT`).

Se ambos forem zero, retencao automatica fica desativada.

### Rota legada `/backups`

Existe uma rota antiga em `galint_flask/views/backups.py`.

Ela lista/restaura arquivos JSON simples com `entradas` e `saidas`, sincronizando ledger para linhas restauradas. Esse fluxo e legado/especifico e nao substitui o backup oficial PostgreSQL em `BackupService`.

Uso operacional recomendado:

- para backup do sistema: `Configuracoes > Backup`;
- para restauracao oficial: `ConversionEngine`;
- usar `/backups` apenas para cenarios legados ja conhecidos.

## 4. ConversionEngine e motores

### O que e o ConversionEngine

`ConversionEngine` e o motor de analise, staging e preparacao de bases para o GALINT.

Ele aceita:

- `.sql` texto plano;
- `.zip` com `.sql`, `.sqlite` ou `.db`;
- `.sqlite`;
- `.db`.

Ele nao e uma conversao universal de qualquer ERP para GALINT. A versao atual faz:

1. upload/registro de origem;
2. staging isolado;
3. perfilamento de tabelas e volume;
4. comparacao com schema GALINT;
5. score de compatibilidade;
6. pacote tecnico de implantacao;
7. deploy direto somente quando seguro.

### Onde ficam os arquivos do motor

Pasta raiz:

```text
instance/conversionengine
```

Subpastas:

```text
sources  -> uploads e backups enviados ao motor
staging  -> extracoes e analises temporarias
outputs  -> pacotes tecnicos e SQL convertido
```

### Jobs do motor

`start_conversion_job` cria job in-memory por usuario.

Estado:

- `job_id`
- `user_key`
- `source_name`
- `stored_name`
- `status`
- `progress`
- `phase`
- `message`
- `metrics`
- `result`
- `logs`

Rotas:

```text
POST /configuracoes/conversionengine/iniciar
GET  /configuracoes/conversionengine/status/<job_id>
GET  /configuracoes/conversionengine/download/<job_id>
GET  /configuracoes/conversionengine/pacote/<job_id>
POST /configuracoes/conversionengine/implantar/<job_id>
```

### Envio de backup ao ConversionEngine

Pela UI:

```text
Configuracoes > Backup > selecionar um backup > Enviar ao ConversionEngine
```

Rota:

```text
POST /configuracoes/conversionengine/analisar-backup
```

Fluxo:

1. seleciona exatamente um backup;
2. copia o backup para `instance/conversionengine/sources`;
3. inicia job;
4. redireciona para a tela do ConversionEngine com `job_id`.

### Fases internas do ConversionEngine

Metodo principal:

```python
ConversionEngineService.run_conversion(...)
```

Fases:

1. `validation`:
   - valida arquivo recebido;
   - aceita apenas extensoes suportadas.

2. `staging`:
   - cria pasta isolada;
   - copia original;
   - se ZIP, extrai com protecao contra path traversal;
   - se tiver `manifest.json`, carrega metadados;
   - escolhe melhor candidato SQL/SQLite dentro do ZIP.

3. `profiling`:
   - para SQL, le `CREATE TABLE`, `COPY` e `INSERT`;
   - detecta engine provavel: PostgreSQL, MySQL ou SQLite;
   - conta tabelas, colunas e linhas;
   - para SQLite, abre com `sqlite3` e le schema/totais.

4. `matching`:
   - compara tabelas de origem com `db.metadata` do GALINT;
   - usa aliases conhecidos:
     - `items` -> `itens`
     - `entries` -> `entradas`
     - `outputs` -> `saidas`
     - `inventory_events` -> `inventario_eventos`
     - `invoices` -> `notas_fiscais`
     - `suppliers` -> `fornecedores`
   - calcula score de tabela, colunas e exatidao.

5. `packaging`:
   - gera manifesto tecnico;
   - gera README de implantacao;
   - se deployavel, copia SQL como base convertida;
   - cria pacote `.zip` de saida.

6. `finalizing`:
   - entrega resumo, mapeamentos, tarefas, bloqueios e artefatos.

### Score e deploy direto

O deploy direto so e liberado quando:

- score de compatibilidade >= 72;
- tabelas criticas existem com nome exato;
- ha tabelas mapeadas;
- todos os mapeamentos sao exatos, nao por alias;
- origem detectada e PostgreSQL;
- origem nao e SQLite;
- versao minima do pacote e compativel;
- pacote completo nao declara versao de origem diferente da atual.

Se qualquer regra falhar, o motor ainda gera pacote tecnico, mas bloqueia implantacao direta.

### Artefatos gerados

Em `outputs`:

- `<base>_manifest.json`
- `<base>_README.txt`
- `<base>.zip`
- `<base>.sql` quando deploy direto e permitido

No `BackupService`, quando deployavel:

- `<base>_deploy.sql` e copiado para `instance/backups` para o restore oficial.

### Implantacao pelo motor

Rota:

```text
POST /configuracoes/conversionengine/implantar/<job_id>
```

Se o job e deployavel:

- se origem e pacote completo GALINT, chama:

```python
BackupService.restore_complete_package(source_path, reporter)
```

- caso contrario, chama:

```python
BackupService.restore_backup_with_progress(deploy_backup_name, reporter)
```

A restauracao roda em job de restore, nao na request principal.

### BackupService como motor de resiliencia

`BackupService` tambem e um motor:

- resolve ferramentas PostgreSQL;
- valida ambiente;
- gera dump;
- monta pacote completo;
- aplica retencao;
- restaura SQL;
- restaura assets;
- garante backup recente antes de update via `ensure_backup_for_update`.

### InventoryEngine e UnitConversionEngine

Embora este README foque em imagens/precos/backup, existem dois motores operacionais conectados ao valor do estoque:

- `InventoryEngine`: registra entradas, saidas, devolucoes e ajustes no ledger, atualizando `stock_movements` e `stock_balances`.
- `UnitConversionEngine`: converte quantidade operacional para unidade base antes de gravar movimento ou normalizar preco.

Esses motores devem ser usados quando a funcionalidade mexe com saldo, unidade, embalagem ou custo normalizado.

## 5. Como aplicar na pratica

### Aplicar imagem em item existente

1. Abrir Inventario.
2. Abrir assistente de foto do item.
3. Usar busca externa sugerida.
4. Copiar URL publica da imagem.
5. Colar no modal.
6. Aplicar.
7. Backend baixa, processa e salva `foto_path`.

Endpoint equivalente:

```text
POST /itens/foto/url
```

### Aplicar imagem em novo item na NF

1. Abrir Documentos Fiscais.
2. Escolher modo de cadastro.
3. Preencher descricao, categoria e marca do novo item.
4. Abrir assistente de imagem.
5. Colar URL escolhida.
6. Ao registrar o documento/item, backend baixa e salva a foto.

### Buscar preco de reposicao para item

1. Abrir item no inventario.
2. Acionar busca de preco.
3. Informar UF quando fizer sentido.
4. Revisar provedores e sugestoes.
5. Escolher valor.
6. Salvar pelo endpoint `/itens/<codigo>/precos/reposicao`.

### Buscar preco em lote por categoria

1. Abrir listagem de inventario.
2. Abrir modal de lote por categoria.
3. O sistema carrega ate 10 pendentes sem preco e sem comprovante fiscal.
4. Selecionar sugestoes confiaveis.
5. Aplicar selecionados.
6. Modal recarrega a fila; itens salvos saem e entram os proximos pendentes.

### Gerar backup antes de operacao critica

1. Abrir `Configuracoes > Backup`.
2. Conferir diagnostico.
3. Preferir `Gerar pacote completo` quando a operacao envolve migracao, update ou troca de maquina.
4. Guardar o ZIP como artefato sensivel.
5. Para restaurar, enviar ao ConversionEngine.

### Usar ConversionEngine para validar backup/base

1. Abrir `Configuracoes > Backup`.
2. Selecionar um backup.
3. Clicar em `Enviar ao ConversionEngine`.
4. Aguardar job.
5. Revisar score, mapeamentos, manifest e bloqueios.
6. Implantar apenas se o motor liberar deploy direto.

## 6. Cuidados e falhas comuns

### Imagens

- URL de Google Images normalmente nao e a imagem final; use a URL direta do arquivo.
- Host privado e bloqueado por seguranca.
- Imagem acima de 6 MB por URL e rejeitada.
- Se o `Content-Type` nao for imagem, o backend rejeita.

### Precos

- Mercado Livre pode bloquear consulta anonima; isso e esperado.
- Fallback pode retornar poucos resultados se varejistas bloquearem bots.
- Preco web nao deve sobrescrever preco fiscal comprovado.
- Sempre salvar fonte, query e URL para auditoria.

### Backup

- Sem `pg_dump` e `psql`, backup oficial nao fica pronto.
- Pacote completo contem dados sensiveis, incluindo `secret_key.txt` quando existir.
- ZIP completo deve passar pelo ConversionEngine.
- Jobs de restore/conversion sao in-memory; reiniciar servidor limpa estado visual do job.

### Motores

- ConversionEngine nao converte magicamente qualquer schema.
- Deploy direto exige nomes exatos e compatibilidade alta.
- Mapeamento por alias ajuda diagnostico, mas bloqueia deploy direto.
- SQLite e analisado, mas nao e deploy direto nesta versao.

## 7. Checklist rapido

Antes de aplicar imagem:

- item existe ou novo item tem codigo definido;
- URL e publica;
- operador e admin;
- imagem representa o produto correto.

Antes de aplicar preco:

- item nao tem NF/cupom como fonte melhor;
- unidade do preco foi conferida;
- sugestao tem fonte e URL;
- preco base normalizado faz sentido.

Antes de aplicar backup/restore:

- diagnostico de backup esta pronto;
- backup recente existe;
- pacote completo foi validado no ConversionEngine;
- bloqueios foram revisados;
- ambiente foi reiniciado quando necessario.

## 8. Regra final de arquitetura

- Imagem: UI assiste a busca, `ItemFotoService` valida e grava.
- Preco: `PriceSuggestionService` sugere, usuario confirma, inventario salva com normalizacao.
- Backup: `BackupService` gera e restaura artefatos oficiais PostgreSQL.
- Motor: `ConversionEngine` analisa, pontua, empacota e so implanta quando o risco e aceitavel.

Essa separacao e importante: busca nao grava sozinha, sugestao nao vira verdade sem confirmacao, backup completo nao restaura sem motor, e motor nao pula staging quando ha risco.
