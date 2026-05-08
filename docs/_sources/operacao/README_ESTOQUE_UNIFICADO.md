# README - Estoque Unificado

## Objetivo

Este é o README canônico sobre o tema saldo de estoque no GALINT.

Ele consolida em um único lugar:

- a situação atual do saldo
- por onde os dados passam hoje
- onde nascem as inconsistências
- por que os saldos podem explodir
- qual é a arquitetura alvo
- como sair do modelo atual para um sistema único de estoque

Este documento substitui a leitura fragmentada entre diagnóstico, ledger, conversão, embalagem e tela. A partir daqui, o assunto deve ser pensado como um único problema arquitetural.

---

## Resumo executivo

Hoje o GALINT não tem uma única representação de saldo. Ele tem várias representações coexistindo:

- saldo legado por Entrada, Saída e InventarioEvento
- saldo canônico em StockMovement
- cache de leitura em StockBalance
- projeção física de embalagem em Item.estoque_embalagens e Item.estoque_unidades_soltas
- exibição final em saldo_display, APIs, views web, mobile e notificações

O efeito prático é que o sistema ainda permite que o mesmo produto seja interpretado sob semânticas diferentes ao longo do fluxo.

Quando isso acontece:

- o saldo canônico pode ser reinterpretado como quantidade de embalagens
- a unidade de embalagem pode ser tratada como unidade base real
- o read model físico pode ser recalculado a partir de uma unidade errada
- o valor financeiro pode ser calculado sobre um saldo inflado

Em resumo: o problema não é um bug isolado. O problema é excesso de fluxos, excesso de camadas e excesso de lugares decidindo o que significa saldo.

---

## Princípio central

O sistema precisa convergir para esta regra:

- o único saldo autoritativo deve ser a soma de StockMovement.quantity_base na unidade canônica do item

Todo o resto deve ser derivado disso:

- StockBalance como cache
- estoque_embalagens e estoque_unidades_soltas como projeção física
- saldo_display como formatação
- valor financeiro como leitura sobre saldo reconciliado

---

## Mapa do fluxo atual

Hoje o saldo de um item pode passar pelas camadas abaixo.

### 1. Entrada operacional do usuário

O fluxo pode nascer em:

- web
- mobile
- Telegram
- documento fiscal
- ajuste administrativo
- backfill ou reconciliação

Aqui entram quantidade e unidade operacional, por exemplo:

- 1 lata
- 3 pacotes
- 4 litros
- 18 unidades

### 2. Resolução de unidade e fator

Antes de escrever saldo, o sistema tenta resolver:

- qual é a unidade canônica do item
- qual é o fator da embalagem
- se o item trabalha em kg, l, m ou un
- se a unidade informada é operacional ou já é canônica

Arquivos principais:

- galint_flask/services/legacy_stock_normalizer.py
- galint_flask/services/unit_conversion_engine.py
- galint_flask/services/embalagem_service.py

### 3. Conversão para unidade base

O UnitConversionEngine transforma a quantidade operacional em quantidade_base + unit_base.

Exemplo esperado:

- 1 lata de massa corrida 25 kg -> 25 kg
- 1 rolo de 50 m -> 50 m
- 1 pacote com 1000 unidades -> 1000 un

Se o motor escolher a unidade errada como base, todo o saldo posterior nasce contaminado.

### 4. Gravação do movimento

O InventoryEngine grava StockMovement.

Esse deveria ser o momento autoritativo do saldo.

Arquivos principais:

- galint_flask/services/inventory_engine.py
- galint_flask/models.py

### 5. Atualização do cache de saldo

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

### 7. Reconstrução do read model físico

Para itens com embalagem, o sistema tenta decompor o saldo canônico em:

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

- há histórico antigo dependente dele
- ainda existe dual-write em alguns pontos
- certos ajustes administrativos precisam alinhar legado e ledger separadamente

### 2. Saldo canônico em ledger

Vem da soma de:

- StockMovement.quantity_base

Esse precisa ser a fonte final de verdade.

### 3. Saldo em cache

Vem de:

- StockBalance.quantity_base

Esse valor precisa ser sempre derivado do ledger.

### 4. Saldo físico de embalagem

Vem de:

- Item.estoque_embalagens
- Item.estoque_unidades_soltas

Esse valor não pode ser autoritativo. Ele deve ser apenas leitura operacional amigável.

### 5. Saldo exibido

Vem de:

- saldo
- saldo_display
- combinações em views e templates

Esse é apenas formato de leitura. Se ele estiver "corrigindo" o backend, a arquitetura já está errada.

---

## Onde o sistema se perde hoje

### 1. Múltiplas fontes de verdade

O mesmo produto pode ter, ao mesmo tempo:

- saldo legado
- saldo em stock_movements
- saldo em stock_balances
- saldo físico de embalagem

Se essas camadas não estiverem semanticamente alinhadas, a divergência nasce.

### 2. Unidade de embalagem tratada como unidade base

Esse foi um dos gatilhos principais dos saldos astronômicos.

Exemplo:

- produto: MASSA CORRIDA 25KG
- saldo canônico correto: 168,921876 kg
- erro: tratar esse valor como 168,921876 latas

A decomposição errada fica:

$$
168{,}921876 \Rightarrow 168 \text{ latas} + (0{,}921876 \times 25) = 23{,}047 \text{ kg}
$$

E o total exibido vira:

$$
168 \times 25 + 23{,}047 = 4223{,}047
$$

Ou seja: o saldo não apenas apareceu errado. Ele foi matematicamente reinterpretado sob uma unidade errada.

### 3. Read model físico recalculado a partir de unit_base errada

O read model físico depende de:

- quantity_base
- unit_base
- fator da embalagem

Se quantity_base estiver certa, mas unit_base vier como lata, balde, pacote ou rolo quando deveria ser kg, l, un ou m, o sistema reconstrói o estoque físico inteiro de forma errada.

### 4. Conversor, provider e writer não nasceram totalmente sob a mesma regra

Historicamente, havia caminhos em que:

- o conversor escolhia unidade base a partir da configuração do produto
- o provider escolhia outra semântica de leitura
- o read model físico se reconstruía com outra referência
- o legado ainda influenciava parte do resultado

Isso gerou comportamento em que um conserto pontual resolvia uma tela e reabria o problema em outro fluxo.

### 5. Dual-write e cutover parcial

Hoje o sistema ainda atravessa uma migração.

Isso significa que alguns fluxos:

- gravam no ledger
- espelham no legado
- leem do ledger em alguns cenários
- leem do legado em outros
- dependem de flags como read_model_ready

Enquanto essa convivência existir, o sistema permanece sensível à regressão semântica.

### 6. Correções históricas por vários caminhos

Já houve correção de saldo por:

- edição de item
- ajuste administrativo
- manual correction
- backfill
- reconciliação absoluta
- espelhamento de documento fiscal

Se todos esses caminhos não obedecerem exatamente à mesma regra de unidade e de fonte de verdade, o passivo histórico aumenta.

---

## O papel de cada componente no desenho alvo

### StockMovement

Deve ser:

- historico imutavel
- histórico imutável
- fonte única de verdade
- sempre gravado em unidade canônica

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

- o único motor de conversão
- responsável por transformar unidade operacional em unidade canônica

Nunca deve:

- escolher unidade base de embalagem como unidade canônica de saldo
- espalhar regra de conversão para fora do engine

### InventoryEngine

Deve ser:

- o único writer de estoque
- o único lugar autorizado a gravar StockMovement e atualizar StockBalance

Nunca deve:

- ser bypassado por endpoint, service ou integracao
- ser bypassado por endpoint, service ou integração

### BalanceProvider

Deve ser:

- o único provider de leitura operacional do saldo canônico

Nunca deve:

- reinterpretar o saldo a partir da última unit_base errada
- escolher uma semântica diferente da usada pelo writer

### EmbalagemService e read model fisico

Devem ser:

- camada de projeção e formatação
- tradutor do saldo canônico para forma operacional amigável

Nunca devem:

- decidir a fonte real do saldo
- reescrever a semântica do saldo autoritativo

---

## Estado desejado

Precisamos chegar a um único sistema de estoque com estas propriedades.

### 1. Uma única fonte de verdade

- saldo autoritativo = soma de StockMovement.quantity_base

### 2. Uma única unidade canônica por item

Cada item deve ter uma unidade canônica única e clara:

- kg
- l
- m
- un

Lata, balde, bombona, pacote, caixa, fardo, saco e rolo não são unidade canônica. São unidade operacional ou tipo de embalagem.

### 3. Um único writer

Toda entrada, saída, devolução e ajuste deve passar por um único engine.

### 4. Um único conversor

Toda conversão deve acontecer antes da gravação do movimento e sempre produzir quantity_base e unit_base canônicos.

### 5. Projeções derivadas

Tudo o que é visual ou operacional deve derivar do saldo canônico:

- saldo_display
- embalagens fechadas
- unidades soltas
- valor financeiro
- indicadores e alertas

### 6. Legado como compatibilidade temporária

Enquanto houver legado, ele deve existir apenas como camada de transição e auditoria, não como centro decisor do saldo novo.

---

## Regras inegociáveis

1. Nenhum StockMovement novo pode ser gravado com unit_base de embalagem.
2. Nenhum cálculo financeiro pode usar saldo não reconciliado.
3. Nenhuma tela deve remontar saldo fisico fora do backend.
4. Nenhum ajuste pode alinhar apenas uma camada deixando as outras defasadas.
5. Nenhum item embalado deve aceitar operação sem unidade canônica resolvida.
6. Nenhum fluxo paralelo deve gravar estoque fora do InventoryEngine.

---

## Plano de simplificação

### Fase 1 - Conter reintrodução

- impedir unit_base de embalagem em novas gravações
- centralizar resolução de unidade canônica
- garantir que a reconstrução física use sempre a unidade canônica
- fazer a UI consumir apenas saldo_display pronto do backend

### Fase 2 - Consolidar leitura

- BalanceProvider virar a leitura única do saldo operacional
- valor financeiro ler apenas saldo reconciliado
- parar de deixar views escolherem qual saldo usar

### Fase 3 - Reconciliar backlog histórico

- auditar todos os itens embalados
- localizar divergências entre ledger, cache e read model
- corrigir itens contaminados com ajuste absoluto seguro
- manter trilha de auditoria das correções

### Fase 4 - Reduzir o legado a adaptador temporário

- manter dual-write apenas onde ele ainda é obrigatório
- eliminar caminhos de reparo paralelos
- remover dependência operacional do legado conforme o cutover avançar

### Fase 5 - Operar de fato em estoque unificado

- StockMovement como verdade única
- StockBalance como cache
- Item.estoque_embalagens e Item.estoque_unidades_soltas como projeção
- APIs, telas e financeiro lendo a mesma semântica de saldo

---

## Observabilidade obrigatória

Já existe base para controle de regressão:

- check_stock_unit_integrity.py
- audit/stock_unit_integrity_baseline.json

Essa auditoria precisa virar rotina obrigatória para qualquer alteração em:

- estoque
- conversão de unidades
- ledger
- provider de saldo
- read model de embalagem
- processamento documental

Objetivo:

- impedir regressão silenciosa
- separar backlog historico de erro novo
- garantir que novos fluxos nasçam sob a regra certa

---

## O que este README consolida

Este documento consolida o tema que antes estava espalhado principalmente entre:

- README_DIAGNOSTICO_SALDOS_ESTOQUE.md
- README_LEDGER_ESTOQUE.md

Esses documentos podem continuar existindo como histórico de evolução, mas a referência canônica para este assunto passa a ser este arquivo.

---

## Conclusao

O problema de saldo do GALINT não é simplesmente erro de tela, erro de cálculo ou erro de cadastro. O problema é arquitetural.

Enquanto o saldo puder:

- nascer em um fluxo
- ser convertido em outro
- ser espelhado em outro
- ser reconstruido em outro
- ser exibido por outra semântica

as inconsistências vão continuar aparecendo.

A saída é única:

- um unico writer
- uma única unidade canônica
- uma única fonte de verdade
- projeções derivadas para exibição
- legado tratado como transição e não como origem concorrente

Este é o critério para sair do modelo atual e chegar a um estoque realmente unificado.