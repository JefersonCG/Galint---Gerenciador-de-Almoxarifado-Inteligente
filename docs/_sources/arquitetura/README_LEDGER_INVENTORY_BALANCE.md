# README - Ledger, Inventory Balance e leitura de saldo

Este README descreve a logica real do saldo de estoque no GALINT, com base na implementacao atual do codigo.

Arquivos principais:

- `galint_flask/models.py`
- `galint_flask/services/inventory_engine.py`
- `galint_flask/services/inventory.py`
- `galint_flask/services/balance_provider.py`
- `galint_flask/services/legacy_stock_normalizer.py`
- `galint_flask/services/ledger_backfill_normalized.py`
- `galint_flask/services/ledger_reconciliation.py`
- `scripts/backfill_ledger_inventory.py`
- `scripts/reconcile_ledger_inventory.py`
- `migrations/versions/3c5b8d9e7f10_add_ledger_inventory_core.py`

## Ideia central

O GALINT usa duas camadas para saldo:

1. `stock_movements`: ledger de movimentos.
2. `stock_balances`: read model/cache de saldo atual por item.

O ledger e a fonte historica moderna. Cada entrada, saida, devolucao ou ajuste vira um movimento com quantidade ja convertida para a unidade base canonica do item.

O balance e uma materializacao rapida: guarda o saldo atual calculado a partir dos movimentos. Ele existe para leitura eficiente em telas, listagens e APIs.

Durante a migracao, o sistema ainda convive com tabelas legadas (`entradas`, `saidas`, `inventario_eventos`). Por isso existe uma terceira peca:

3. `balance_provider`: decide se a leitura deve vir do `stock_balances` ou do legado normalizado.

## Tabelas principais

### stock_movements

Model: `StockMovement`.

Campos centrais:

- `product_id`: item (`itens.codigo_item`).
- `movement_type`: tipo do movimento.
- `quantity_base`: delta do movimento ja na unidade base.
- `unit_base`: unidade base canonica usada no movimento.
- `reference_type`: origem do movimento.
- `reference_id`: id da linha de origem quando existir.
- `metadata_json`: contexto operacional, conversao, usuario, canal e dados auxiliares.
- `created_at`: data do movimento.

Tipos normalizados em `LedgerMovementType`:

- entrada
- saida
- devolucao
- ajuste
- inicial

Observacao importante: `quantity_base` e delta, nao quantidade bruta positiva sempre.

Exemplos:

- entrada de 10 unidades: `quantity_base = +10`
- saida de 3 unidades: `quantity_base = -3`
- devolucao de 2 unidades: `quantity_base = +2`
- ajuste para reduzir saldo em 5: `quantity_base = -5`

### stock_balances

Model: `StockBalance`.

Campos centrais:

- `product_id`: chave primaria e item.
- `quantity_base`: saldo atual materializado.
- `read_model_ready`: indica se o read model esta autorizado para leitura direta.
- `updated_at`: atualizacao automatica.

Regra:

```text
stock_balances.quantity_base = soma(stock_movements.quantity_base) para o item
```

Mas esta regra so deve ser usada diretamente para leitura quando o item ja foi considerado migrado/seguro (`read_model_ready = true`) ou quando regras especificas permitem preferir o cache.

## Unidade base canonica

A unidade base e resolvida em `legacy_stock_normalizer.resolve_canonical_unit`.

Prioridade:

1. `product_units` com `is_base = true` e `active = true`.
2. medida inferida por embalagem (`infer_packaging_measure`).
3. campos antigos de embalagem:
   - `litros_por_embalagem`
   - `grandeza_referencia`
   - `unidades_por_embalagem`
   - `tipo_embalagem_novo`
4. unidade simples do item (`item.unidade`).
5. fallback para `un`.

Unidades canonicas esperadas:

- `un`
- `par`
- `m`
- `kg`
- `l`

Regra de seguranca: movimento moderno nao deve gravar `unit_base` como embalagem operacional (`rolo`, `caixa`, `pacote`, `saco`, `lata`, etc.). Embalagem e unidade de entrada/operacao; o ledger guarda o equivalente na base canonica.

## Como uma operacao nova grava saldo

Servico: `InventoryEngine`.

Entradas publicas:

- `register_entry`
- `register_exit`
- `register_return`
- `register_adjustment`

Fluxo real de `_register_movement`:

1. Normaliza `product_id`.
2. Carrega o item.
3. Bloqueia saida se o item esta com `pre_cadastro_pendente`.
4. Converte a quantidade de entrada para base canonica:

```python
conversion = unit_conversion_engine.convert_item_to_base(item, quantity, from_unit)
```

5. Valida que a unidade convertida nao e embalagem e bate com a canonica do item:

```python
_ensure_canonical_movement_unit(item=item, unit_base=conversion.unit_base)
```

6. Le saldo anterior pelo `balance_provider`:

```python
balance_before = balance_provider.get_balance(product_id).quantity_base
```

7. Calcula o delta:

```text
quantity_delta = conversion.quantity_base * sinal
```

Sinais:

- entrada: `+1`
- saida: `-1`
- devolucao: `+1`
- ajuste positivo: `+1`
- ajuste negativo: `-1`

8. Calcula saldo depois:

```text
balance_after = balance_before + quantity_delta
```

9. Bloqueia se `balance_after < 0`.
10. Cria `StockMovement` com `quantity_base = quantity_delta`.
11. Cria ou atualiza `StockBalance` com `quantity_base = balance_after`.
12. Cria `OperationLog` de sucesso.
13. Faz `flush`/`commit` conforme parametro.
14. Grava auditoria de conversao em SQLite (`instance/conversion_logs.db`) quando `write_audit = true`.

## Como o balance e atualizado

Em operacao moderna:

```text
stock_balances.quantity_base = balance_after
```

O balance nao recalcula tudo a cada movimento normal. Ele recebe o saldo final da transacao.

Em backfill/rebuild:

```text
stock_balances.quantity_base = SUM(stock_movements.quantity_base)
```

Esse rebuild fica em `LedgerBackfillService.rebuild_balances` e `rebuild_balances_for_products`.

## Como o saldo e lido

Servico: `BalanceProvider`.

Metodo principal:

```python
balance_provider.get_balance(product_id, item=item)
```

Retorna `BalanceSnapshot`:

- `product_id`
- `quantity_base`
- `unit_base`
- `source`
- `migrated`

### Regra de decisao

1. Se o produto tem `StockBalance.read_model_ready = true`, usa `stock_balances`.

Resultado:

```text
source = stock_balance
migrated = true
```

2. Se o item veio de NF e a regra `_should_prefer_stock_balance_for_nf_origin` permitir, tambem usa `stock_balances`.

Resultado:

```text
source = stock_balance_nf_origin
migrated = false
```

3. Se o item ainda tem historico legado e nao esta migrado, calcula o saldo pelo legado normalizado.

Resultado:

```text
source = legacy
migrated = false
```

4. Se nao ha historico legado, mas existe `StockBalance`, usa o cache como pendente de corte.

Resultado:

```text
source = stock_balance_pending_cutover
migrated = false
```

5. Se nada existe, retorna zero.

Resultado:

```text
source = legacy
quantity_base = 0
migrated = false
```

## Por que ainda existe leitura pelo legado

O GALINT nasceu com tabelas operacionais antigas:

- `entradas`
- `saidas`
- `inventario_eventos`

Essas tabelas continuam sendo verdade para itens ainda nao migrados. Para evitar erro de saldo em itens com embalagem, rolo, litro, kg, metro ou fator menor que 1, o saldo legado nao e mais soma crua. Ele passa por:

```python
build_normalized_legacy_movements(item)
```

Esse normalizador transforma linhas antigas em movimentos canonicos comparaveis ao ledger.

## Normalizacao do legado

Servico: `legacy_stock_normalizer`.

Funcao principal:

```python
build_normalized_legacy_movements(item)
```

Ela le:

- entradas do item;
- saidas do item;
- eventos de inventario do item.

Depois ordena por data, tipo e id, e gera `NormalizedLegacyMovement`.

### Entrada legada

Vira:

```text
movement_type = entrada
reference_type = entrada
quantity_base = quantidade normalizada positiva
```

### Saida legada

Vira:

```text
movement_type = saida
reference_type = saida
quantity_base = quantidade normalizada negativa
```

### Evento de inventario

Vira movimento conforme tipo do evento:

- ajuste positivo
- ajuste negativo
- ajuste absoluto calculado contra `running_before`

O normalizador mantem `running_before` para eventos que representam ajuste de estoque fisico e nao apenas delta simples.

### Embalagem legada

Quando `uses_packaging_legacy_normalization(item)` retorna true, a quantidade antiga e multiplicada pelo fator da embalagem e convertida para a unidade canonica.

Exemplo conceitual:

```text
1 rolo de cabo de 305 m -> 305 m no ledger
3 rolos + 304 m -> saldo canonico em metros
1 saco de 20 kg -> 20 kg no ledger
1 unidade de pastilha 200 g -> 0,2 kg no ledger
```

## Espelhamento do legado para o ledger

Nem todo fluxo ainda nasceu diretamente no `InventoryEngine`. Alguns fluxos ainda gravam nas tabelas antigas e espelham no ledger.

Servico: `InventoryService.mirror_legacy_movement`.

Fluxo:

1. Carrega item.
2. Monta ou recebe `MovimentoPayload`.
3. Resolve quantidade/unidade adequada para o ledger:
   - unidade fracionada;
   - embalagem;
   - unidade inferida do item.
4. Chama `_mirror_payload_to_ledger`.
5. `_mirror_payload_to_ledger` chama o `InventoryEngine` com `commit=False` e `write_audit=False`.
6. Metadata recebe:

```text
dual_write_active = true
mirrored_from_legacy = true
legacy_payload = {...}
```

7. Depois que a linha legada recebe o id definitivo, `finalize_ledger_mirror` atualiza `reference_id` e `reference_type` no `StockMovement`.
8. `finalize_ledger_mirror` tambem chama `sync_packaging_read_model` para manter campos de embalagem do item alinhados.

## Campos de embalagem do item

Alguns itens possuem campos de leitura operacional:

- `estoque_embalagens`
- `estoque_unidades_soltas`
- `tipo_embalagem_novo`
- `unidades_por_embalagem`
- `litros_por_embalagem`
- `grandeza_referencia`

O ledger continua guardando saldo canonico em `quantity_base`.

Para manter a tela amigavel, o `InventoryEngine` sincroniza o read model de embalagem:

```python
sync_packaging_read_model(product_id=...)
```

E internamente:

```python
_sync_packaging_state_to_balance(item, quantity_base, unit_base)
```

Isso decompõe o saldo canonico em:

```text
embalagens inteiras + unidades soltas
```

Exemplo:

```text
saldo canonico = 1219 m
fator do rolo = 305 m
exibicao operacional = 3 rolos + 304 metros
```

## Ajuste administrativo absoluto

Servico: `InventoryService.set_admin_absolute_balance`.

Esse fluxo nao registra uma entrada ou saida comum. Ele alinha o saldo para um valor alvo.

Passos:

1. Valida item, saldo alvo, motivo e usuario.
2. Bloqueia item com pre-cadastro pendente.
3. Calcula snapshot atual:
   - saldo exibido;
   - saldo legado;
   - saldo ledger;
   - saldo cache.
4. Calcula deltas:

```text
legacy_delta = target_balance - legacy_before
ledger_delta = target_balance - ledger_before
cache_needs_sync = stock_before != target_balance
```

5. Se o legado precisa mudar, cria `InventarioEvento` do tipo de ajuste administrativo.
6. Se o ledger precisa mudar, cria `StockMovement` com:

```text
movement_type = ajuste
reference_type = admin_balance_override
quantity_base = ledger_delta
```

7. Atualiza ou cria `StockBalance` com `quantity_base = target_balance`.
8. Sincroniza estado de embalagem do item.
9. Ajusta `estoque_minimo` conforme regra administrativa.
10. Faz commit.
11. Notifica quando habilitado.
12. Registra auditoria em SQLite de ajuste administrativo.

## Backfill do ledger

Script:

```powershell
.\.venv\Scripts\python.exe scripts\backfill_ledger_inventory.py
```

Servico:

```python
ledger_backfill_service.backfill()
```

O backfill:

1. Agrupa linhas legadas por produto.
2. Usa `build_normalized_legacy_movements` para converter legado em movimentos canonicos.
3. Cria `StockMovement` se ainda nao existir movimento com mesmo:

```text
product_id + reference_type + reference_id
```

4. Ignora movimentos de quantidade zero.
5. Reconstrui `StockBalance` pela soma dos movimentos.
6. Tenta preservar `read_model_ready` de produtos que continuam com reconciliacao aceitavel.
7. Faz commit.
8. Roda reconciliacao e grava relatorio em `instance/reports`.

Tipos de referencia que podem ser limpos/reconstruidos em rebuild legado:

- `entrada`
- `saida`
- `inventario_evento`
- `legacy_movimento`
- `movements_saida_multipla`

## Reconciliacao

Script:

```powershell
.\.venv\Scripts\python.exe scripts\reconcile_ledger_inventory.py
```

Servico:

```python
ledger_reconciliation_service.reconcile_product(product_id)
```

Compara tres numeros:

1. `legacy_balance`: soma do legado normalizado.
2. `ledger_balance`: soma de `stock_movements.quantity_base`.
3. `stock_balance`: valor em `stock_balances.quantity_base`.

Tambem calcula `document_only_balance`, que e a soma de movimentos `reference_type = entrada_documento_item`.

Divergencias:

```text
divergence_legacy_vs_ledger = ledger_balance - legacy_balance
divergence_ledger_vs_cache = stock_balance - ledger_balance
```

Classificacoes:

### divergencia_zero

Quando:

```text
legacy == ledger == cache
```

dentro da tolerancia `1e-6`.

### divergencia_explicavel

Quando o cache bate com o ledger e a diferenca entre legado e ledger e explicada por documentos que existem apenas no ledger:

```text
divergence_ledger_vs_cache ~= 0
(divergence_legacy_vs_ledger - document_only_balance) ~= 0
```

Tambem e explicavel quando as divergencias sao pequenas, ate 1 unidade.

### divergencia_critica

Qualquer caso fora das regras acima.

## O que significa read_model_ready

`read_model_ready` e a chave de corte por produto.

- `true`: o sistema pode ler `stock_balances` como saldo principal.
- `false`: o sistema ainda deve preferir legado normalizado, salvo excecoes.

O backfill tenta preservar essa flag quando a reconciliacao fica como:

- `divergencia_zero`
- `divergencia_explicavel`

Se a reconciliacao vira critica, o produto perde a confianca do read model.

## Fontes de saldo exibidas na tela administrativa

`get_admin_balance_snapshot` mostra:

- `saldo_exibido`: saldo que o sistema realmente esta usando via `balance_provider`.
- `saldo_fisico`: saldo calculado por metodos de exibicao do item.
- `legacy_balance`: legado normalizado.
- `ledger_balance`: soma do ledger.
- `stock_balance`: cache materializado.
- `source`: origem usada pelo `balance_provider`.
- `migrated`: se o produto esta em leitura migrada.
- divergencias e classificacao.

Isso permite saber por que a tela mostra um saldo e se ele veio de cache, ledger migrado ou legado.

## Regras praticas para manutencao

### Para registrar movimento novo

Use `InventoryEngine` ou um service que passe por ele.

Nao atualize `stock_balances` diretamente sem criar `StockMovement`, exceto em rotinas de rebuild/correcao administrativa controlada.

### Para fluxos legados

Se a rotina ainda grava `Entrada`, `Saida` ou `InventarioEvento`, ela deve espelhar no ledger com `mirror_legacy_movement` e finalizar com `finalize_ledger_mirror` quando o id legado estiver disponivel.

### Para corrigir saldo manualmente

Use `set_admin_absolute_balance`.

Ele ajusta legado, ledger, cache, embalagem e auditoria juntos.

### Para recalcular cache

Use `ledger_backfill_service.rebuild_balances` ou `rebuild_balances_for_products`.

### Para decidir se um item pode ler pelo cache

Use `balance_provider`, nunca leia `StockBalance` diretamente em tela/regra operacional.

### Para diagnosticar divergencia

Use `ledger_reconciliation_service` ou o script `scripts/reconcile_ledger_inventory.py`.

## Fluxo resumido

```text
Operacao nova
  -> InventoryEngine
  -> converte para unidade base
  -> cria StockMovement
  -> atualiza StockBalance
  -> cria OperationLog
  -> sincroniza embalagem quando aplicavel

Fluxo legado
  -> grava Entrada/Saida/InventarioEvento
  -> mirror_legacy_movement
  -> InventoryEngine com mirrored_from_legacy
  -> finalize_ledger_mirror

Leitura de saldo
  -> balance_provider
  -> se read_model_ready: StockBalance
  -> senao: legado normalizado
  -> fallback: StockBalance pendente ou zero

Backfill
  -> le legado
  -> normaliza movimentos
  -> cria StockMovement idempotente
  -> rebuild StockBalance
  -> reconciliacao
```

## Invariantes que nao devem ser quebradas

1. `StockMovement.quantity_base` sempre e delta canonico.
2. `StockBalance.quantity_base` deve representar o saldo atual materializado.
3. Telas e APIs devem ler saldo pelo `balance_provider`.
4. Embalagem nao deve virar `unit_base` de movimento moderno.
5. Movimento legado reconstruido precisa manter `reference_type` e `reference_id` estaveis para idempotencia.
6. Ajuste administrativo deve alinhar legado, ledger e cache, nao apenas um deles.
7. Rebuild de balance deve ser soma de `stock_movements`.
8. Divergencia critica deve impedir confiar cegamente no read model.
9. Itens com pre-cadastro pendente nao podem sofrer saida.
10. Conversao e fator aplicado devem ficar em `metadata_json` e `OperationLog`.
