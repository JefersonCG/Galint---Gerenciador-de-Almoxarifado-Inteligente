# README - Ledger, Inventory, Backup e Engine Operacional

## Objetivo

Este README explica, de forma operacional, como o GALINT organiza a logica entre estoque, ledger, financeiro, backup e engines auxiliares. Ele tambem descreve como implantar a mesma arquitetura em outro sistema Python sem carregar junto todos os modulos visuais do GALINT.

O foco aqui e responder quatro perguntas praticas:

1. Onde nasce uma movimentacao de estoque.
2. Qual tabela e fonte de verdade para saldo e para valor financeiro.
3. Como o sistema se protege contra divergencia, unidade errada, preco de pacote e restore perigoso.
4. Como replicar o desenho em outro backend Python com SQLAlchemy, PostgreSQL e servicos transacionais.

---

## Glossario rapido

### Inventory

E a camada operacional do estoque. Ela recebe entrada, saida, devolucao, ajuste, leitura de saldo, listagem de itens, invalidacao de cache e compatibilidade com o legado.

Arquivos principais:

- [galint_flask/services/inventory.py](../../../galint_flask/services/inventory.py)
- [galint_flask/views/inventory.py](../../../galint_flask/views/inventory.py)

### InventoryEngine

E o nucleo transacional moderno. Ele nao deve ser tratado como tela, rota ou helper de template. Ele e o motor que transforma uma operacao em movimento contabil de estoque.

Arquivo principal:

- [galint_flask/services/inventory_engine.py](../../../galint_flask/services/inventory_engine.py)

### StockMovement

E o ledger fisico de estoque. Cada linha e um fato imutavel de movimento: entrada, saida, devolucao ou ajuste.

Tabela/modelo:

- [galint_flask/models.py](../../../galint_flask/models.py)

Campos essenciais:

- `product_id`: codigo do item.
- `movement_type`: `entrada`, `saida`, `devolucao`, `ajuste`.
- `quantity_base`: quantidade ja convertida para unidade canonica. Saidas ficam negativas.
- `unit_base`: unidade canonica usada no movimento.
- `reference_type`: origem logica do movimento, por exemplo `entrada_documento_item`, `inventory_engine`, `movements_saida_multipla`.
- `reference_id`: id da entidade de origem.
- `metadata_json`: contexto operacional, usuario, origem, unidade informada, fator aplicado.
- `created_at`: data do fato.

### StockBalance

E o read model/cache de saldo. Ele existe para leitura rapida, nao para substituir o ledger.

Tabela/modelo:

- [galint_flask/models.py](../../../galint_flask/models.py)

Campos essenciais:

- `product_id`: codigo do item.
- `quantity_base`: saldo atual derivado dos movimentos.
- `read_model_ready`: indica se a leitura pode preferir `StockBalance` em vez do saldo legado.
- `updated_at`: data da ultima atualizacao.

### BalanceProvider

E o resolvedor de saldo. Durante a migracao, ele decide se o item deve ser lido pelo legado ou pelo `StockBalance`.

Arquivo principal:

- [galint_flask/services/balance_provider.py](../../../galint_flask/services/balance_provider.py)

Regra operacional:

- item reconciliado e com `read_model_ready=True`: ler `StockBalance`.
- item ainda nao migrado: reconstruir saldo pelo legado normalizado.
- item originado de NF com condicoes seguras: pode preferir `StockBalance` mesmo antes do cutover formal.

### FinanceLedgerEntry

E o ledger financeiro. Ele nao e saldo fisico. Ele guarda custo, documento, fornecedor, valor unitario, valor base e comprovacao.

Tabela/modelo:

- [galint_flask/models.py](../../../galint_flask/models.py)

Campos essenciais:

- `codigo_item`: item comprado/lancado.
- `quantidade`: quantidade informada no documento.
- `unidade_quantidade`: unidade original da quantidade.
- `quantidade_base`: quantidade convertida para unidade interna.
- `valor_unitario`: preco bruto informado.
- `valor_unitario_base`: preco por unidade interna.
- `unidade_preco`: unidade do preco bruto.
- `fator_preco_base`: fator usado para chegar no preco base.
- `valor_total`: valor documental total.
- `tipo_documento`, `numero_documento`, `chave_acesso`: rastreabilidade fiscal.
- `fornecedor_id`: origem comercial.
- `comprovacao_status`: qualidade da comprovacao.

### UnitConversionEngine

E o motor de conversao de unidades. Ele transforma a quantidade informada pelo usuario na unidade base do produto.

Arquivo principal:

- [galint_flask/services/unit_conversion_engine.py](../../../galint_flask/services/unit_conversion_engine.py)

Ele resolve conversao nesta ordem:

1. identidade, quando a unidade informada ja e a unidade base;
2. grafo de conversoes cadastradas em `ProductUnitConversion`;
3. subunidades metricas, como cm para m;
4. embalagem legada, usando fator resolvido pelo normalizador.

### PriceNormalization

E a camada que impede erro financeiro de pacote. Para valor monetario, a regra e sempre usar preco base por unidade interna.

Arquivo principal:

- [galint_flask/services/price_normalization.py](../../../galint_flask/services/price_normalization.py)

Exemplo:

```text
Pacote bruto: R$ 35,00
Conteudo: 100 unidades
Preco base interno: 35 / 100 = R$ 0,35 por unidade
```

### BackupService

E o servico PostgreSQL-only de backup e restauracao.

Arquivo principal:

- [galint_flask/services/backup.py](../../../galint_flask/services/backup.py)

Ele gera dois tipos de backup:

- `database`: dump `.sql` por `pg_dump`.
- `complete`: pacote `.zip` com dump SQL, `manifest.json`, README interno e ativos de disco.

### ConversionEngine

E o motor de staging, analise e empacotamento para bases externas ou backups completos.

Arquivo principal:

- [galint_flask/services/conversion_engine.py](../../../galint_flask/services/conversion_engine.py)

Ele aceita:

- `.sql` texto;
- `.zip` com `.sql`, `.sqlite` ou `.db`;
- `.sqlite` e `.db`.

---

## Principio central do saldo

A regra de arquitetura e:

```text
Saldo autoritativo = soma de StockMovement.quantity_base por product_id
```

Todo o resto e derivado:

- `StockBalance.quantity_base`: cache/read model.
- `Item.estoque_embalagens`: projecao visual de embalagens fechadas.
- `Item.estoque_unidades_soltas`: projecao visual de fracionado.
- `saldo_display`: formatacao para usuario.
- dashboard, mobile, XLS e PDF: leituras derivadas.

Em outro sistema Python, essa regra deve ser mantida sem excecao. Se uma tela atualiza saldo direto sem gerar movimento no ledger, a arquitetura quebra.

---

## Principio central do valor financeiro

A regra financeira e:

```text
Valor de estoque = saldo em unidade interna * preco_unitario_base
```

Nunca use preco bruto de pacote diretamente contra saldo unitario.

Correto:

```text
100 unidades em estoque
pacote de 100 custa R$ 35,00
preco_unitario_base = R$ 0,35
valor = 100 * 0,35 = R$ 35,00
```

Errado:

```text
100 unidades em estoque
preco bruto do pacote = R$ 35,00
valor = 100 * 35,00 = R$ 3.500,00
```

No GALINT, os campos de reposicao e cotações externas servem para comparacao e planejamento. Eles nao devem substituir automaticamente custo fiscal comprovado de NF/Cupom.

---

## Fluxo operacional de entrada

### 1. Origem da entrada

A entrada pode nascer em:

- tela web de lancamentos;
- documento fiscal;
- importacao/backfill;
- ajuste administrativo;
- fluxo mobile.

### 2. Normalizacao de quantidade e preco

Em documento fiscal, o fluxo passa por `FinanceService.process_stock_document_item()`.

Arquivo:

- [galint_flask/services/finance_service.py](../../../galint_flask/services/finance_service.py)

Esse metodo:

1. carrega `DocumentoEntradaEstoqueItem` com item e documento;
2. respeita `movimenta_estoque=False` quando o documento e apenas financeiro;
3. impede duplicidade se ja existe `stock_movement_id` ou `entrada_id`;
4. normaliza unidade documental quando a linha parece embalagem cadastrada de forma antiga;
5. calcula `quantidade_base`, `valor_unitario_base`, `unidade_preco` e `fator_preco_base`;
6. chama `inventory_engine.register_entry()` com `commit=False`;
7. grava ids de `StockMovement` e `OperationLog` na linha documental;
8. sincroniza read model de embalagem;
9. comita a transacao;
10. notifica Telegram quando aplicavel.

### 3. Escrita no InventoryEngine

`inventory_engine.register_entry()` chama `_execute_operation()` e depois `_register_movement()`.

O motor:

1. valida `product_id`;
2. carrega `Item`;
3. converte `quantity` + `from_unit` para `quantity_base` + `unit_base` pelo `UnitConversionEngine`;
4. bloqueia unidade base de embalagem como unidade operacional canonica;
5. consulta saldo antes pelo `BalanceProvider`;
6. calcula saldo depois;
7. cria `StockMovement` positivo;
8. atualiza ou cria `StockBalance`;
9. cria `OperationLog`;
10. sincroniza projecao de embalagem quando aplicavel;
11. comita ou apenas faz `flush`, conforme parametro `commit`.

### 4. Metadados minimos recomendados

Para entrada via outro sistema Python, envie metadados neste formato:

```python
metadata = {
    "source": "documento_fiscal",
    "channel": "documento_fiscal",
    "reference_type": "entrada_documento_item",
    "reference_id": str(document_item_id),
    "documento_id": documento_id,
    "numero_documento": numero_documento,
    "tipo_documento": tipo_documento,
    "user_id": usuario_id,
    "observacao": observacao,
}
```

O par `reference_type` + `reference_id` e importante para idempotencia, auditoria e recuperacao de movimento.

---

## Fluxo operacional de saida

### 1. Origem da saida

A saida pode nascer em:

- tela web;
- aplicativo mobile;
- custodia de ferramenta;
- central de kits;
- consumo operacional por local/atividade;
- ajuste administrativo.

### 2. Regra de bloqueio de pre-cadastro

O `InventoryEngine` bloqueia saida se o item esta com `pre_cadastro_pendente=True`.

Mensagem operacional:

```text
Saida bloqueada: este item esta com pre-cadastro pendente. Finalize o pre-cadastro antes de registrar a saida.
```

### 3. Escrita no ledger

`inventory_engine.register_exit()` usa o mesmo nucleo de entrada, mas com `balance_delta_sign=-1`.

O movimento e gravado com `quantity_base` negativo. O motor bloqueia saldo negativo:

```text
if balance_after < 0: erro de saldo insuficiente
```

### 4. Metadados minimos recomendados

```python
metadata = {
    "source": "web",
    "channel": "saida_operacional",
    "reference_type": "saida",
    "reference_id": str(saida_id),
    "local_servico": local_servico,
    "atividade_operacional": atividade,
    "centro_custo": centro_custo,
    "ordem_servico": ordem_servico,
    "user_id": usuario_id,
}
```

---

## Fluxo operacional de devolucao

Devolucao e movimento positivo, mas semanticamente diferente de entrada.

Use:

```python
inventory_engine.register_return(
    product_id=codigo_item,
    quantity=quantidade,
    from_unit=unidade,
    metadata={
        "source": "central_kits",
        "channel": "devolucao_ferramenta",
        "reference_type": "devolucao_ferramenta",
        "reference_id": str(saida_id),
        "user_id": usuario_id,
    },
)
```

No GALINT, devolucoes de ferramentas nao apagam a saida historica. Elas criam novo movimento de devolucao e preservam rastreabilidade.

---

## Fluxo operacional de ajuste

Ajuste aceita quantidade positiva ou negativa:

- positiva: aumenta saldo;
- negativa: reduz saldo.

Use ajuste para inventario fisico, correcao administrativa ou regularizacao com justificativa. Nao use ajuste para esconder erro de documento fiscal; nesse caso, prefira estorno ou reparo documental.

Metadados recomendados:

```python
metadata = {
    "source": "auditoria_admin",
    "channel": "ajuste_estoque",
    "reference_type": "inventario_evento",
    "reference_id": str(evento_id),
    "motivo": motivo,
    "user_id": usuario_id,
}
```

---

## Fluxo financeiro documental

`FinanceLedgerEntry` registra a verdade financeira, especialmente para NF, cupom, fornecedor e custo medio.

Use `FinanceService.register_financial_entry()` quando precisar registrar um lancamento financeiro desacoplado ou complementar ao movimento fisico.

O metodo:

1. normaliza quantidade;
2. normaliza preco;
3. calcula valor total;
4. grava origem, fornecedor e comprovacao;
5. salva `valor_unitario_base` para relatorios financeiros;
6. atualiza preferencia de fornecedor quando ha `fornecedor_id`.

Exemplo de uso em outro sistema:

```python
FinanceService.register_financial_entry(
    codigo_item=codigo_item,
    categoria_nome=categoria,
    quantidade=quantidade_documental,
    unidade_quantidade="pacote",
    valor_unitario=35.00,
    unidade_preco="pacote",
    fornecedor_id=fornecedor_id,
    origem_valor="nf",
    tipo_documento="NF",
    numero_documento="12345",
    chave_acesso=chave_acesso,
    comprovacao_status="comprovado",
)
```

Se o pacote tem fator 100, o normalizador deve persistir:

```text
valor_unitario = 35.00
unidade_preco = pacote
fator_preco_base = 100
valor_unitario_base = 0.35
```

---

## Como o saldo e lido

### BalanceProvider

Toda leitura operacional deve passar por um resolvedor equivalente ao `BalanceProvider`.

Ele retorna um `BalanceSnapshot` com:

- `product_id`;
- `quantity_base`;
- `unit_base`;
- `source`;
- `migrated`.

Fontes possiveis:

- `stock_balance`: item migrado e pronto;
- `stock_balance_nf_origin`: item de origem NF que pode preferir cache moderno;
- `stock_balance_pending_cutover`: existe cache, mas ainda sem cutover formal;
- `legacy`: saldo reconstruido por entradas/saidas/eventos antigos.

### Regra para outro sistema

Em outro backend, evite consultar `StockBalance` diretamente em toda tela. Crie um `BalanceProvider` proprio e centralize a regra de transicao.

---

## Invalidação de cache em tempo real

O GALINT usa cache runtime em leituras caras. Depois de qualquer movimento que altere saldo, chame:

```python
inventory_service.invalidate_realtime_views()
```

Isso limpa caches de:

- autocomplete de itens;
- listagem de estoque;
- snapshot de dashboard;
- relatorio financeiro de valor de estoque.

Em outro sistema Python, a regra equivalente e:

```text
movimentou estoque -> invalidou caches de estoque, dashboard e financeiro
```

---

## Reconciliacao, backfill e cutover

### Backfill

`LedgerBackfillService` migra dados legados para `StockMovement` de forma idempotente.

Arquivo:

- [galint_flask/services/ledger_backfill_normalized.py](../../../galint_flask/services/ledger_backfill_normalized.py)

Ele reconstrói movimentos a partir de:

- `Entrada`;
- `Saida`;
- `InventarioEvento`;
- movimentos legados normalizados.

Principais metodos:

- `backfill(clear_balances=False)`: processa a base inteira.
- `sync_restored_rows(...)`: sincroniza linhas reaplicadas apos restore.
- `rebuild_products_from_legacy(product_ids)`: reconstrói itens especificos.
- `rebuild_balances()`: recalcula `StockBalance` pela soma dos movimentos.
- `rebuild_balances_for_products(product_ids)`: recalcula saldo de itens especificos.

### Reconciliacao

`LedgerReconciliationService` compara:

```text
saldo legado vs soma de StockMovement vs StockBalance
```

Classificacoes:

- `divergencia_zero`: tudo alinhado;
- `divergencia_explicavel`: diferenca aceitavel/documental;
- `divergencia_critica`: exige auditoria.

Arquivo:

- [galint_flask/services/ledger_reconciliation.py](../../../galint_flask/services/ledger_reconciliation.py)

### Cutover

`LedgerCutoverService` ativa leitura por `StockBalance` somente para produtos reconciliados.

Arquivo:

- [galint_flask/services/ledger_cutover.py](../../../galint_flask/services/ledger_cutover.py)

Regra:

- por padrao, so ativa `divergencia_zero`;
- pode aceitar `divergencia_explicavel` com `allow_explainable=True`;
- pode forcar com `force=True`, mas isso deve ser excecao operacional.

---

## Modelo minimo para implantar em outro sistema Python

### Dependencias recomendadas

```text
Python 3.11+
Flask ou FastAPI
SQLAlchemy 2.x
PostgreSQL
Alembic
pg_dump e psql no servidor de backup
```

### Tabelas minimas

#### products

```text
id/codigo
descricao
unidade_base
tipo_embalagem
unidades_por_embalagem
preco_compra_unitario
preco_compra_unitario_base
preco_compra_unidade_preco
preco_compra_fator_base
preco_reposicao_unitario
preco_reposicao_unitario_base
preco_reposicao_unidade_preco
preco_reposicao_fator_base
```

#### product_units

```text
id
product_id
unit_code
is_base
active
```

#### product_unit_conversions

```text
id
product_id
from_unit
to_unit
factor
active
```

#### stock_movements

```text
id
product_id
movement_type
quantity_base
unit_base
reference_type
reference_id
metadata_json
created_at
```

#### stock_balances

```text
product_id
quantity_base
read_model_ready
updated_at
```

#### finance_ledger_entries

```text
id
product_id
supplier_id
document_id
posted_at
quantity
quantity_unit
quantity_base
unit_price
unit_price_base
price_unit
factor_to_base
total_value
origin
document_type
document_number
access_key
proof_status
notes
```

#### operation_logs

```text
id
operation_type
product_id
quantity_input
quantity_base
unit_input
source
user_id
payload_json
created_at
status
error_message
```

---

## Ordem correta de uma transacao de movimento

Use esta ordem em outro sistema:

```text
1. abrir transacao
2. carregar produto com lock se houver alta concorrencia
3. validar permissao e status do produto
4. converter quantidade informada para unidade base
5. buscar saldo atual pelo BalanceProvider
6. calcular saldo depois
7. bloquear saldo negativo se movimento reduz estoque
8. inserir StockMovement
9. atualizar StockBalance
10. criar OperationLog
11. atualizar projecao de embalagem, se existir
12. flush
13. integrar efeitos colaterais internos ainda na transacao
14. commit
15. invalidar caches
16. disparar notificacoes assíncronas
```

Nao dispare Telegram, email ou webhooks antes do commit. Primeiro garanta o fato no banco; depois notifique.

---

## Exemplo de InventoryEngine simplificado

```python
class InventoryEngine:
    def register_movement(self, *, product_id, quantity, from_unit, movement_type, metadata):
        product = Product.query.get(product_id)
        if product is None:
            raise ValueError("Produto nao encontrado")

        conversion = unit_conversion_engine.convert_item_to_base(product, quantity, from_unit)
        delta_sign = {
            "entrada": 1,
            "devolucao": 1,
            "saida": -1,
            "ajuste": 1 if quantity >= 0 else -1,
        }[movement_type]

        balance = balance_provider.get_balance(product_id)
        quantity_delta = abs(conversion.quantity_base) * delta_sign
        balance_after = balance.quantity_base + quantity_delta

        if balance_after < 0:
            raise ValueError("Saldo insuficiente")

        movement = StockMovement(
            product_id=product_id,
            movement_type=movement_type,
            quantity_base=quantity_delta,
            unit_base=conversion.unit_base,
            reference_type=metadata.get("reference_type"),
            reference_id=metadata.get("reference_id"),
            metadata_json={
                **metadata,
                "input_quantity": quantity,
                "input_unit": from_unit,
                "factor_applied": conversion.factor_applied,
                "conversion_path": conversion.conversion_path,
            },
        )
        db.session.add(movement)

        stock_balance = StockBalance.query.get(product_id) or StockBalance(product_id=product_id)
        stock_balance.quantity_base = balance_after
        db.session.add(stock_balance)

        operation_log = OperationLog.from_movement(movement, balance_before=balance.quantity_base, balance_after=balance_after)
        db.session.add(operation_log)
        db.session.commit()
```

---

## Backup operacional

### Configuracao

O GALINT usa PostgreSQL. O backup automatico nao aceita SQLite como banco principal.

Variaveis principais:

```text
SQLALCHEMY_DATABASE_URI=postgresql://user:senha@host:5432/banco
GALINT_PG_DUMP=C:\Program Files\PostgreSQL\17\bin\pg_dump.exe
GALINT_PSQL=C:\Program Files\PostgreSQL\17\bin\psql.exe
GALINT_BACKUP_RETENTION_DAYS=30
GALINT_BACKUP_RETENTION_COUNT=20
GALINT_BACKUP_TIMEOUT_SECONDS=3600
GALINT_PG_CONNECT_TIMEOUT_SECONDS=10
GALINT_PG_LOCK_TIMEOUT_MS=5000
GALINT_PG_STATEMENT_TIMEOUT_MS=60000
```

### Onde os backups ficam

No GALINT atual:

```text
instance/backups/
```

Arquivos gerados:

```text
galint_backup_YYYYMMDD_HHMMSS.sql
galint_backup_full_YYYYMMDD_HHMMSS.zip
```

### Backup SQL

Chamado por:

```python
BackupService(app).create_backup(backup_kind="database")
```

Internamente usa:

```text
pg_dump --clean --if-exists --no-owner --no-privileges -d banco -f destino.sql
```

### Pacote completo

Chamado por:

```python
BackupService(app).create_backup(backup_kind="complete")
```

Conteudo:

```text
database/galint_backup_YYYYMMDD_HHMMSS.sql
assets/static/uploads/...
assets/static/logo/...
assets/instance/barcodes/...
assets/instance/reports/...
assets/instance/network_settings.json
assets/instance/secret_key.txt
manifest.json
README_backup_completo.txt
```

O dump SQL interno e transitorio no diretorio de backups: ele e removido depois de entrar no ZIP.

### Manifesto

O `manifest.json` registra:

- versao do schema do manifesto;
- tipo do backup;
- data UTC;
- versao do app;
- host de origem;
- caminho do `instance`;
- dump SQL interno;
- hash SHA-256;
- ativos incluidos;
- ativos ausentes;
- compatibilidade minima.

### Politica de retencao

Apos criar backup, o servico aplica retencao:

- por quantidade (`BACKUP_RETENTION_COUNT`);
- por idade (`BACKUP_RETENTION_DAYS`).

### Restore SQL

O restore direto de `.sql`:

1. valida o arquivo;
2. pode capturar delta pos-backup;
3. encerra conexoes SQLAlchemy;
4. tenta encerrar outras sessoes PostgreSQL;
5. recria schema `public`;
6. executa `psql --single-transaction -v ON_ERROR_STOP=1`;
7. aplica correcoes de schema pos-restore;
8. reaplica delta quando configurado.

### Restore completo

O restore completo do `.zip` deve passar pelo pipeline oficial:

1. extrair em staging seguro;
2. validar que nao ha path traversal;
3. ler `manifest.json`;
4. localizar dump SQL interno;
5. restaurar o banco;
6. restaurar ativos em `static` e `instance`;
7. reportar progresso.

---

## ConversionEngine operacional

O ConversionEngine e usado para analisar uma base externa ou um backup completo antes de permitir implantacao.

Fluxo:

```text
1. upload ou registro de backup existente
2. copia para instance/conversionengine/sources
3. criacao de staging isolado
4. extracao segura se for ZIP
5. localizacao do SQL/SQLite principal
6. perfilamento de tabelas, colunas e volume
7. comparacao com schema GALINT atual
8. calculo de score de compatibilidade
9. geracao de pacote tecnico em outputs
10. liberacao ou bloqueio de deploy direto
```

Pastas:

```text
instance/conversionengine/sources
instance/conversionengine/staging
instance/conversionengine/outputs
```

Regras importantes:

- ZIP e extraido somente depois de validar caminhos internos.
- O motor aceita SQL PostgreSQL, SQLite e ZIP contendo SQL/SQLite.
- O deploy direto so deve ser liberado quando a estrutura e compativel.
- Um backup completo do GALINT declara compatibilidade no manifesto.

---

## Checklist de implantacao em outro sistema Python

### Fase 1 - Base de dados

1. Criar tabelas de produto, unidades, conversoes, movimentos, saldo, ledger financeiro e logs.
2. Criar indices em `product_id`, `movement_type`, `reference_type`, `reference_id`, datas e fornecedor.
3. Garantir FK de `stock_movements.product_id` para produtos.
4. Garantir `stock_balances.product_id` como chave primaria.
5. Usar JSONB para metadados se for PostgreSQL.

### Fase 2 - Conversao de unidade

1. Definir unidade base por produto.
2. Definir aliases de unidade.
3. Criar grafo de conversao por produto.
4. Implementar fallback de embalagem legada somente quando fator for confiavel.
5. Bloquear movimento cuja unidade base final seja embalagem operacional.

### Fase 3 - Engine transacional

1. Implementar `register_entry`.
2. Implementar `register_exit`.
3. Implementar `register_return`.
4. Implementar `register_adjustment`.
5. Toda operacao deve inserir movimento e atualizar saldo na mesma transacao.
6. Toda operacao deve gerar log.
7. Toda falha deve fazer rollback.

### Fase 4 - Financeiro

1. Implementar normalizacao de linha documental.
2. Persistir preco bruto e preco base.
3. Persistir fator usado.
4. Separar custo fiscal de preco de reposicao.
5. Relatorios devem usar preco base.

### Fase 5 - Migracao

1. Construir movimentos normalizados a partir do legado.
2. Inserir movimentos de forma idempotente.
3. Recalcular `StockBalance` pela soma do ledger.
4. Reconciliar legado, ledger e cache.
5. Ativar `read_model_ready` por produto, nao globalmente no escuro.

### Fase 6 - Backup e restore

1. Exigir PostgreSQL para backup operacional.
2. Configurar `pg_dump` e `psql`.
3. Gerar backup SQL antes de migracoes destrutivas.
4. Gerar pacote completo antes de update ou troca de maquina.
5. Testar restore em staging.
6. Documentar RPO e RTO.

### Fase 7 - Observabilidade

1. Criar log de operacao.
2. Registrar metadados de conversao.
3. Registrar origem e usuario.
4. Ter rotina de reconciliacao diaria ou sob demanda.
5. Ter relatorio de divergencias criticas.

---

## Erros que nao podem voltar

### Usar preco bruto contra saldo unitario

Nunca calcule valor de estoque assim:

```text
saldo_unidades * preco_pacote
```

Use:

```text
saldo_unidades * preco_base_unitario
```

### Atualizar saldo direto no produto

Nao use:

```text
produto.saldo += quantidade
```

Use movimento:

```text
insert StockMovement + update StockBalance
```

### Fazer restore sem staging

Nao restaure ZIP completo diretamente em producao sem validar manifesto, versao, dump e ativos.

### Ativar leitura por cache sem reconciliacao

`StockBalance` so e confiavel quando deriva do ledger e o item foi reconciliado.

### Misturar reposicao com custo fiscal

Preco de reposicao ajuda compra futura. Custo fiscal/documental sustenta valor contabil e auditoria.

---

## Rotina operacional recomendada

### Diario

1. Monitorar erros de movimentacao.
2. Conferir divergencias criticas.
3. Conferir backups recentes.
4. Validar espaco em disco.

### Antes de update

1. Rodar diagnostico de backup.
2. Gerar pacote completo recente.
3. Confirmar `manifest.json`.
4. Executar update.
5. Validar login, estoque, relatorios e uma movimentacao simples.

### Antes de migracao de saldo

1. Gerar backup completo.
2. Rodar backfill em staging.
3. Rodar reconciliacao.
4. Ativar cutover por lote pequeno.
5. Validar dashboards e relatorios.
6. Expandir por categoria ou por itens sem divergencia.

---

## Resumo executivo para implantacao

Se for levar essa arquitetura para outro sistema Python, leve estes blocos, nesta ordem:

1. `UnitConversionEngine`: sem conversao confiavel, saldo nasce errado.
2. `InventoryEngine`: sem motor transacional, cada tela vira uma regra diferente.
3. `StockMovement`: sem ledger fisico, nao ha auditoria.
4. `StockBalance`: sem read model, a leitura fica pesada.
5. `BalanceProvider`: sem resolvedor, a migracao quebra telas antigas.
6. `PriceNormalization`: sem preco base, relatorio financeiro infla.
7. `FinanceLedgerEntry`: sem ledger financeiro, NF e custo ficam sem rastreabilidade.
8. `LedgerBackfillService`: sem backfill, legado nao converge.
9. `LedgerReconciliationService`: sem reconciliacao, cutover e chute.
10. `BackupService`: sem backup testavel, migracao e restore viram risco operacional.
11. `ConversionEngine`: sem staging, importar/restaurar base externa e perigoso.

Essa e a espinha dorsal do GALINT: movimento fisico auditavel, saldo derivado, valor financeiro normalizado, restore governado e implantacao por etapas.