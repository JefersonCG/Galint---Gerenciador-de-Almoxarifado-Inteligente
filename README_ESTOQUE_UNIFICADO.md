# README - Estoque Unificado

## Objetivo

Este e o README canonico sobre o tema saldo de estoque no GALINT.

Ele consolida em um unico lugar:

- a situacao atual do saldo
- por onde os dados passam hoje
- onde nascem as inconsistencias
- por que os saldos podem explodir
- qual e a arquitetura alvo
- como sair do modelo atual para um sistema unico de estoque

Este documento substitui a leitura fragmentada entre diagnostico, ledger, conversao, embalagem e tela. A partir daqui, o assunto deve ser pensado como um unico problema arquitetural.

---

## Resumo executivo

Hoje o GALINT nao tem uma unica representacao de saldo. Ele tem varias representacoes coexistindo:

- saldo legado por Entrada, Saida e InventarioEvento
- saldo canonico em StockMovement
- cache de leitura em StockBalance
- projecao fisica de embalagem em Item.estoque_embalagens e Item.estoque_unidades_soltas
- exibicao final em saldo_display, APIs, views web, mobile e notificacoes

O efeito pratico e que o sistema ainda permite que o mesmo produto seja interpretado sob semanticas diferentes ao longo do fluxo.

Quando isso acontece:

- o saldo canonico pode ser reinterpretado como quantidade de embalagens
- a unidade de embalagem pode ser tratada como unidade base real
- o read model fisico pode ser recalculado a partir de uma unidade errada
- o valor financeiro pode ser calculado sobre um saldo inflado

Em resumo: o problema nao e um bug isolado. O problema e excesso de fluxos, excesso de camadas e excesso de lugares decidindo o que significa saldo.

---

## Principio central

O sistema precisa convergir para esta regra:

- o unico saldo autoritativo deve ser a soma de StockMovement.quantity_base na unidade canonica do item

Todo o resto deve ser derivado disso:

- StockBalance como cache
- estoque_embalagens e estoque_unidades_soltas como projecao fisica
- saldo_display como formatacao
- valor financeiro como leitura sobre saldo reconciliado

---

## Mapa do fluxo atual

Hoje o saldo de um item pode passar pelas camadas abaixo.

### 1. Entrada operacional do usuario

O fluxo pode nascer em:

- web
- mobile
- Telegram
- documento fiscal
- ajuste administrativo
- backfill ou reconciliacao

Aqui entram quantidade e unidade operacional, por exemplo:

- 1 lata
- 3 pacotes
- 4 litros
- 18 unidades

### 2. Resolucao de unidade e fator

Antes de escrever saldo, o sistema tenta resolver:

- qual e a unidade canonica do item
- qual e o fator da embalagem
- se o item trabalha em kg, l, m ou un
- se a unidade informada e operacional ou ja e canonica

Arquivos principais:

- galint_flask/services/legacy_stock_normalizer.py
- galint_flask/services/unit_conversion_engine.py
- galint_flask/services/embalagem_service.py

### 3. Conversao para unidade base

O UnitConversionEngine transforma a quantidade operacional em quantidade_base + unit_base.

Exemplo esperado:

- 1 lata de massa corrida 25 kg -> 25 kg
- 1 rolo de 50 m -> 50 m
- 1 pacote com 1000 unidades -> 1000 un

Se o motor escolher a unidade errada como base, todo o saldo posterior nasce contaminado.

### 4. Gravacao do movimento

O InventoryEngine grava StockMovement.

Esse deveria ser o momento autoritativo do saldo.

Arquivos principais:

- galint_flask/services/inventory_engine.py
- galint_flask/models.py

### 5. Atualizacao do cache de saldo

Depois do movimento, o sistema atualiza StockBalance.

Esse valor deve ser apenas cache do ledger, nunca fonte independente de verdade.

### 6. Dual-write e compatibilidade com legado

Em varios fluxos, o sistema ainda espelha ou reconcilia com o legado:

- Entrada
- Saida
- InventarioEvento

Arquivos principais:

- galint_flask/services/inventory.py
- galint_flask/services/ledger_backfill.py
- galint_flask/services/ledger_backfill_normalized.py

### 7. Reconstrucao do read model fisico

Para itens com embalagem, o sistema tenta decompor o saldo canonico em:

- embalagens fechadas
- fracionado ou unidades soltas

Exemplo:

- 119,922 kg -> 4 latas + 19,922 kg

Arquivos principais:

- galint_flask/services/inventory_engine.py
- galint_flask/services/embalagem_service.py
- galint_flask/models.py

### 8. Leitura do saldo para interface e API

Na leitura, entram:

- BalanceProvider
- Item.to_dict
- get_saldo_fisico_display
- views
- templates
- APIs mobile

Arquivos principais:

- galint_flask/services/balance_provider.py
- galint_flask/models.py
- galint_flask/views/inventory.py
- galint_flask/templates/inventory/list.html
- galint_flask/views/api_mobile.py

---

## Fontes de saldo que coexistem hoje

### 1. Saldo legado

Vem de:

- Entrada
- Saida
- InventarioEvento

Esse saldo ainda importa porque:

- ha historico antigo dependente dele
- ainda existe dual-write em alguns pontos
- certos ajustes administrativos precisam alinhar legado e ledger separadamente

### 2. Saldo canonico em ledger

Vem da soma de:

- StockMovement.quantity_base

Esse precisa ser a fonte final de verdade.

### 3. Saldo em cache

Vem de:

- StockBalance.quantity_base

Esse valor precisa ser sempre derivado do ledger.

### 4. Saldo fisico de embalagem

Vem de:

- Item.estoque_embalagens
- Item.estoque_unidades_soltas

Esse valor nao pode ser autoritativo. Ele deve ser apenas leitura operacional amigavel.

### 5. Saldo exibido

Vem de:

- saldo
- saldo_display
- combinacoes em views e templates

Esse e apenas formato de leitura. Se ele estiver "corrigindo" o backend, a arquitetura ja esta errada.

---

## Onde o sistema se perde hoje

### 1. Multiplas fontes de verdade

O mesmo produto pode ter, ao mesmo tempo:

- saldo legado
- saldo em stock_movements
- saldo em stock_balances
- saldo fisico de embalagem

Se essas camadas nao estiverem semanticamente alinhadas, a divergencia nasce.

### 2. Unidade de embalagem tratada como unidade base

Esse foi um dos gatilhos principais dos saldos astronomicos.

Exemplo:

- produto: MASSA CORRIDA 25KG
- saldo canonico correto: 168,921876 kg
- erro: tratar esse valor como 168,921876 latas

A decomposicao errada fica:

$$
168{,}921876 \Rightarrow 168 \text{ latas} + (0{,}921876 \times 25) = 23{,}047 \text{ kg}
$$

E o total exibido vira:

$$
168 \times 25 + 23{,}047 = 4223{,}047
$$

Ou seja: o saldo nao apenas apareceu errado. Ele foi matematicamente reinterpretado sob uma unidade errada.

### 3. Read model fisico recalculado a partir de unit_base errada

O read model fisico depende de:

- quantity_base
- unit_base
- fator da embalagem

Se quantity_base estiver certa, mas unit_base vier como lata, balde, pacote ou rolo quando deveria ser kg, l, un ou m, o sistema reconstrui o estoque fisico inteiro de forma errada.

### 4. Conversor, provider e writer nao nasceram totalmente sob a mesma regra

Historicamente, havia caminhos em que:

- o conversor escolhia unidade base a partir da configuracao do produto
- o provider escolhia outra semantica de leitura
- o read model fisico se reconstruia com outra referencia
- o legado ainda influenciava parte do resultado

Isso gerou comportamento em que um conserto pontual resolvia uma tela e reabria o problema em outro fluxo.

### 5. Dual-write e cutover parcial

Hoje o sistema ainda atravessa uma migracao.

Isso significa que alguns fluxos:

- gravam no ledger
- espelham no legado
- leem do ledger em alguns cenarios
- leem do legado em outros
- dependem de flags como read_model_ready

Enquanto essa convivencia existir, o sistema permanece sensivel a regressao semantica.

### 6. Correcoes historicas por varios caminhos

Ja houve correcao de saldo por:

- edicao de item
- ajuste administrativo
- manual correction
- backfill
- reconciliacao absoluta
- espelhamento de documento fiscal

Se todos esses caminhos nao obedecerem exatamente a mesma regra de unidade e de fonte de verdade, o passivo historico aumenta.

---

## O papel de cada componente no desenho alvo

### StockMovement

Deve ser:

- historico imutavel
- fonte unica de verdade
- sempre gravado em unidade canonica

Nunca deve:

- receber unit_base de embalagem como unidade autoritativa
- ser editado para "consertar" saldo; o conserto deve ser novo movimento

### StockBalance

Deve ser:

- cache derivado de StockMovement

Nunca deve:

- servir como fonte independente de verdade
- ser corrigido manualmente sem reconciliar o ledger

### UnitConversionEngine

Deve ser:

- o unico motor de conversao
- responsavel por transformar unidade operacional em unidade canonica

Nunca deve:

- escolher unidade base de embalagem como unidade canonica de saldo
- espalhar regra de conversao para fora do engine

### InventoryEngine

Deve ser:

- o unico writer de estoque
- o unico lugar autorizado a gravar StockMovement e atualizar StockBalance

Nunca deve:

- ser bypassado por endpoint, service ou integracao

### BalanceProvider

Deve ser:

- o unico provider de leitura operacional do saldo canonico

Nunca deve:

- reinterpretar o saldo a partir da ultima unit_base errada
- escolher uma semantica diferente da usada pelo writer

### EmbalagemService e read model fisico

Devem ser:

- camada de projecao e formatacao
- tradutor do saldo canonico para forma operacional amigavel

Nunca devem:

- decidir a fonte real do saldo
- reescrever a semantica do saldo autoritativo

---

## Estado desejado

Precisamos chegar a um unico sistema de estoque com estas propriedades.

### 1. Uma unica fonte de verdade

- saldo autoritativo = soma de StockMovement.quantity_base

### 2. Uma unica unidade canonica por item

Cada item deve ter uma unidade canonica unica e clara:

- kg
- l
- m
- un

Lata, balde, bombona, pacote, caixa, fardo, saco e rolo nao sao unidade canonica. Sao unidade operacional ou tipo de embalagem.

### 3. Um unico writer

Toda entrada, saida, devolucao e ajuste deve passar por um unico engine.

### 4. Um unico conversor

Toda conversao deve acontecer antes da gravacao do movimento e sempre produzir quantity_base e unit_base canonicos.

### 5. Projecoes derivadas

Tudo o que e visual ou operacional deve derivar do saldo canonico:

- saldo_display
- embalagens fechadas
- unidades soltas
- valor financeiro
- indicadores e alertas

### 6. Legado como compatibilidade temporaria

Enquanto houver legado, ele deve existir apenas como camada de transicao e auditoria, nao como centro decisor do saldo novo.

---

## Regras inegociaveis

1. Nenhum StockMovement novo pode ser gravado com unit_base de embalagem.
2. Nenhum calculo financeiro pode usar saldo nao reconciliado.
3. Nenhuma tela deve remontar saldo fisico fora do backend.
4. Nenhum ajuste pode alinhar apenas uma camada deixando as outras defasadas.
5. Nenhum item embalado deve aceitar operacao sem unidade canonica resolvida.
6. Nenhum fluxo paralelo deve gravar estoque fora do InventoryEngine.

---

## Plano de simplificacao

### Fase 1 - Conter reintroducao

- impedir unit_base de embalagem em novas gravacoes
- centralizar resolucao de unidade canonica
- garantir que a reconstrucao fisica use sempre a unidade canonica
- fazer a UI consumir apenas saldo_display pronto do backend

### Fase 2 - Consolidar leitura

- BalanceProvider virar a leitura unica do saldo operacional
- valor financeiro ler apenas saldo reconciliado
- parar de deixar views escolherem qual saldo usar

### Fase 3 - Reconciliar backlog historico

- auditar todos os itens embalados
- localizar divergencias entre ledger, cache e read model
- corrigir itens contaminados com ajuste absoluto seguro
- manter trilha de auditoria das correcoes

### Fase 4 - Reduzir o legado a adaptador temporario

- manter dual-write apenas onde ele ainda e obrigatorio
- eliminar caminhos de reparo paralelos
- remover dependencia operacional do legado conforme o cutover avancar

### Fase 5 - Operar de fato em estoque unificado

- StockMovement como verdade unica
- StockBalance como cache
- Item.estoque_embalagens e Item.estoque_unidades_soltas como projecao
- APIs, telas e financeiro lendo a mesma semantica de saldo

---

## Observabilidade obrigatoria

Ja existe base para controle de regressao:

- check_stock_unit_integrity.py
- audit/stock_unit_integrity_baseline.json

Essa auditoria precisa virar rotina obrigatoria para qualquer alteracao em:

- estoque
- conversao de unidades
- ledger
- provider de saldo
- read model de embalagem
- processamento documental

Objetivo:

- impedir regressao silenciosa
- separar backlog historico de erro novo
- garantir que novos fluxos nascam sob a regra certa

---

## O que este README consolida

Este documento consolida o tema que antes estava espalhado principalmente entre:

- README_DIAGNOSTICO_SALDOS_ESTOQUE.md
- README_LEDGER_ESTOQUE.md

Esses documentos podem continuar existindo como historico de evolucao, mas a referencia canonica para este assunto passa a ser este arquivo.

---

## Conclusao

O problema de saldo do GALINT nao e simplesmente erro de tela, erro de calculo ou erro de cadastro. O problema e arquitetural.

Enquanto o saldo puder:

- nascer em um fluxo
- ser convertido em outro
- ser espelhado em outro
- ser reconstruido em outro
- ser exibido por outra semantica

as inconsistencias vao continuar aparecendo.

A saida e unica:

- um unico writer
- uma unica unidade canonica
- uma unica fonte de verdade
- projecoes derivadas para exibicao
- legado tratado como transicao e nao como origem concorrente

Este e o criterio para sair do modelo atual e chegar a um estoque realmente unificado.