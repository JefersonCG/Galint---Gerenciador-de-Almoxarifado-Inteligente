# README - Arquitetura de Estoque com Ledger no GALINT

## Visão geral

Este documento descreve a arquitetura proposta para evoluir o controle de estoque do GALINT para um modelo robusto, transacional e rastreável, baseado em ledger.

O objetivo é eliminar inconsistências de saldo, centralizar regras de conversão e operação, e permitir crescimento futuro sem depender de novas correções espalhadas por views, rotas ou integrações paralelas.

Esta proposta foi desenhada para um sistema já em produção, com legado ativo, múltiplas integrações e necessidade de migração gradual sem quebra operacional.

---

## Objetivo da arquitetura

O novo núcleo de estoque deve garantir que:

- todo saldo seja derivado de movimentos imutáveis
- toda conversão de unidade aconteça em um único motor
- toda operação de entrada, saída, ajuste e devolução aconteça em um único engine
- web, mobile e Telegram usem a mesma regra de negócio
- a migração ocorra em fases, com dual write e reconciliação
- nenhuma alteração visual seja necessária

---

## Restrições obrigatórias

Esta evolução deve respeitar as seguintes regras:

- não alterar HTML
- não alterar CSS
- não alterar Bootstrap
- não alterar layout
- não alterar templates Jinja2
- não alterar templates Mako
- não alterar estrutura de telas existentes
- não alterar estrutura de formulários existentes
- não renomear campos já usados pela interface

Toda a implementação deve ocorrer apenas no backend, por meio de:

- novos models
- novos services
- novas migrations
- novos endpoints compatíveis com os fluxos atuais
- adaptação de services existentes para uso do novo núcleo

---

## Problema atual

O GALINT já possui regras de estoque, embalagem, fracionamento e rastreabilidade, mas a verdade do saldo ainda está distribuída.

Na prática, o sistema atual combina:

- cálculo legado por somatório de entradas, saídas e ajustes
- campos físicos de embalagem e unidades soltas no cadastro do item
- regras de conversão e saldo espalhadas entre services e views
- fluxos paralelos para web, mobile e Telegram

Esse modelo funciona, mas tende a gerar estes problemas:

- divergência entre saldo calculado e saldo físico
- duplicação de regra de estoque
- dificuldade para expandir unidades e conversões
- alto risco de regressão ao alterar apenas um fluxo
- reconciliação operacional trabalhosa

---

## Princípios da solução

O desenho proposto segue estes princípios:

1. Ledger como fonte única de verdade.
2. Saldo atual como projeção derivada, nunca como origem autoritativa.
3. Conversão feita antes de qualquer gravação de movimento.
4. Nenhuma operação de estoque fora do Inventory Engine.
5. Nenhuma conversão fora do Unit Conversion Engine.
6. Operações sempre transacionais no PostgreSQL.
7. Migração gradual com rollback operacional possível.

---

## Componentes da arquitetura

### 1. StockMovement

Representa cada movimento imutável de estoque.

Campos mínimos recomendados:

- id
- product_id
- movement_type
- quantity_base
- unit_base
- reference_type
- reference_id
- metadata_json
- created_at

Responsabilidade:

- armazenar o histórico autoritativo de estoque
- registrar a quantidade sempre na unidade base do produto
- permitir auditoria, reconciliação e rastreamento de origem

Regras:

- nunca editar ou sobrescrever um movimento existente
- qualquer correção deve ocorrer por novo movimento de ajuste

### 2. StockBalance

Representa a projeção atual do saldo do produto.

Campos mínimos:

- product_id
- quantity_base
- updated_at

Responsabilidade:

- servir como cache de leitura rápida
- reduzir custo de leitura operacional

Regras:

- não é fonte de verdade
- não pode ser editado manualmente como forma de corrigir estoque
- só pode ser atualizado dentro da mesma transação que grava o ledger

### 3. ProductDimension

Representa quais grandezas estão habilitadas para um produto.

Campos mínimos:

- product_id
- dimension
- enabled

Responsabilidade:

- indicar se massa, volume, comprimento ou outra grandeza está ativa para aquele item
- separar habilitação de grandeza da definição de conversão

### 4. ProductUnit

Representa as unidades disponíveis para um produto.

Campos sugeridos:

- id
- product_id
- unit_code
- unit_label
- dimension
- is_base
- active

Responsabilidade:

- declarar as unidades válidas do produto
- definir qual unidade é a base autoritativa

### 5. ProductUnitConversion

Representa as relações de conversão entre unidades do produto.

Campos sugeridos:

- id
- product_id
- from_unit
- to_unit
- factor
- metadata_json
- active

Responsabilidade:

- concentrar todas as regras de conversão estrutural
- permitir cadeia de conversão sem hardcode espalhado

Exemplos:

- caixa -> pacote = 24
- pacote -> unidade = 250
- rolo -> metro = 50

---

## Inventory Engine

O Inventory Engine deve ser a única porta de entrada para gravação de estoque.

Arquivo proposto:

- services/inventory_engine.py

Operações públicas esperadas:

- register_entry
- register_exit
- register_adjustment
- register_return

Fluxo obrigatório de qualquer operação:

1. receber payload normalizado
2. identificar produto e contexto da operação
3. chamar o Unit Conversion Engine
4. validar saldo e regras de negócio
5. gravar StockMovement
6. atualizar StockBalance
7. executar dual write no legado enquanto a migração estiver ativa
8. retornar resultado amigável para o consumidor

Regras obrigatórias:

- nunca permitir saldo negativo
- toda gravação deve ser transacional
- nenhum endpoint deve gravar estoque diretamente fora desse engine
- web, mobile e Telegram devem convergir para esse mesmo serviço

---

## Unit Conversion Engine

O motor de conversão deve ter responsabilidade única: converter qualquer entrada válida para a unidade base do produto.

Arquivo proposto:

- services/unit_conversion_engine.py

Função principal:

- convert_to_base(product_id, quantity, from_unit)

Saída esperada:

- quantity_base
- unit_base
- conversion_path
- factor_applied
- metadata

Responsabilidades:

- descobrir a unidade base do produto
- validar se a unidade informada é suportada
- resolver conversão direta ou em cadeia
- falhar de forma explícita quando não houver caminho válido

Regras obrigatórias:

- nenhuma regra hardcoded de conversão fora desse engine
- o engine não deve gravar saldo
- o engine não deve depender de web, mobile ou Telegram

---

## Unidades dinâmicas

As unidades dinâmicas devem se tornar o centro da configuração de conversões.

Isso significa que:

- o cadastro define quais unidades existem para o produto
- a unidade base é única e explícita
- as relações de conversão ficam persistidas no backend
- o modal ou ponto de configuração apenas habilita ou escolhe, mas não vira origem paralela de lógica

Exemplos de configuração:

- caixa -> 24 pacotes
- pacote -> 250 unidades
- rolo -> 50 metros
- balde -> 18 litros

Regra central:

- toda conversão deve nascer da configuração dinâmica, nunca de lógica duplicada espalhada em rota, template ou integração externa

---

## Balance Provider

Antes de migrar todas as leituras, é recomendável introduzir um provider central de saldo.

Arquivo sugerido:

- services/balance_provider.py

Responsabilidade:

- esconder de consumidores externos se o saldo vem do modelo legado ou do novo StockBalance

Comportamento esperado:

1. se o produto estiver habilitado para saldo novo, ler StockBalance
2. se ainda estiver em fase legada, ler pelo método de compatibilidade
3. expor uma interface única para web, mobile, Telegram, relatórios e services auxiliares

Essa camada é importante para evitar uma migração abrupta de leitura em dezenas de pontos espalhados pelo sistema.

---

## Dual write

Como o GALINT já está em produção, a substituição do legado não deve ser imediata.

Durante a transição, o Inventory Engine deve operar em modo dual write.

Modos sugeridos:

- legacy_only
- dual_write
- ledger_only

Estratégia recomendada:

1. começar com dual_write
2. validar reconciliação dos saldos
3. migrar leitura de forma gradual
4. somente depois ativar ledger_only

O dual write deve manter compatibilidade temporária com:

- Entrada
- Saida
- InventarioEvento
- fluxos específicos de custódia e integrações que ainda dependam de tabelas legadas

---

## Migração em fases

### Fase 1. Fundação

Objetivo:

- criar a infraestrutura nova sem alterar o comportamento externo

Entregas:

- models de ledger e saldo
- models de unidades e dimensões
- migrations iniciais
- unit_conversion_engine
- inventory_engine
- balance_provider
- flags de rollout

Critério de aceite:

- aplicação continua operando sem mudar interface
- novas tabelas criadas sem regressão

### Fase 2. Escrita centralizada

Objetivo:

- garantir que novas movimentações passem pelo Inventory Engine

Entregas:

- adaptação dos flows web
- adaptação dos flows mobile
- adaptação dos flows Telegram
- remoção de escrita direta de saldo fora do engine

Critério de aceite:

- toda nova entrada, saída, ajuste ou devolução gera movimento no ledger
- legado continua sendo atualizado enquanto dual write estiver ativo

### Fase 3. Backfill e reconciliação

Objetivo:

- carregar o histórico relevante para o ledger e comparar saldos

Entregas:

- script de backfill para tabelas legadas
- geração de StockMovement histórico
- reconstrução de StockBalance
- relatório de divergência por produto

Critério de aceite:

- produtos reconciliados podem migrar leitura
- divergências críticas ficam explicitadas e bloqueadas

### Fase 4. Migração gradual de leitura

Objetivo:

- passar a consultar StockBalance como saldo oficial

Entregas:

- ativação progressiva do balance_provider para leitura nova
- fallback controlado para saldo legado quando necessário

Critério de aceite:

- web, mobile, Telegram e relatórios passam a exibir saldo derivado do ledger para produtos habilitados

### Fase 5. Consolidação

Objetivo:

- reduzir dependência do legado e consolidar o novo núcleo

Entregas:

- desativação gradual do cálculo legado como verdade do estoque
- limpeza de caminhos paralelos de movimentação

Critério de aceite:

- o ledger é a fonte única de verdade operacional

---

## Backfill histórico

O backfill deve converter o histórico atual em movimentos do novo ledger.

Fontes previstas:

- Entrada
- Saida
- InventarioEvento

Cada linha migrada deve preservar referência de origem por meio de:

- reference_type
- reference_id

Exemplos:

- reference_type = entrada
- reference_type = saida
- reference_type = inventario_evento

Importância:

- auditoria
- rastreabilidade
- investigação de divergência
- reprocessamento futuro, se necessário

---

## Reconciliação

Reconciliação não é opcional. Ela é condição para migrar leitura em ambiente de produção.

O processo deve comparar, por produto:

- saldo legado calculado
- saldo físico derivado de embalagens, quando aplicável
- saldo novo calculado a partir do ledger

Resultado esperado por item:

- reconciliado
- reconciliado com ressalva
- divergente crítico

Somente produtos reconciliados devem ser habilitados para leitura oficial via StockBalance.

---

## Auditoria em SQLite

O SQLite deve ser usado apenas para auditoria leve das conversões.

Arquivo proposto:

- conversion_logs.db

Tabela sugerida:

- id
- timestamp
- product_id
- input_unit
- input_quantity
- output_quantity_base
- output_unit_base
- conversion_path
- factor_applied
- metadata_json
- source

Regras obrigatórias:

- não interfere na transação principal do estoque
- não bloqueia gravação do ledger se falhar
- serve apenas para rastreamento técnico e auditoria

---

## Formatação amigável para o usuário

O sistema deve separar armazenamento interno de exibição amigável.

Função proposta:

- format_movement_for_user()

Objetivo:

- converter uma quantidade interna em unidade base para uma apresentação adequada ao usuário

Exemplos:

- interno: 2500 unidades
- exibição: 10 pacotes

- interno: 514 unidades
- exibição: 2 pacotes e 14 unidades

Regra importante:

- essa função é apenas de apresentação, nunca de persistência ou cálculo autoritativo

---

## Regras críticas de negócio

Estas regras são obrigatórias em qualquer etapa da implementação:

- nunca permitir saldo negativo
- sempre converter antes de salvar movimento
- ledger é imutável
- StockBalance é apenas projeção derivada
- nenhuma lógica de estoque fora do Inventory Engine
- nenhuma lógica de conversão fora do Unit Conversion Engine
- tudo deve ser transacional no PostgreSQL
- nenhuma alteração visual deve ser necessária

---

## Testes mínimos obrigatórios

### Testes do Unit Conversion Engine

- conversão direta
- conversão em cadeia
- unidade inválida
- produto sem configuração
- caminho de conversão ausente

### Testes do Inventory Engine

- entrada simples
- saída simples
- ajuste positivo
- ajuste negativo
- devolução
- bloqueio de saldo negativo
- rollback transacional em falha intermediária

### Testes de reconciliação

- produto simples
- produto com embalagem
- produto com histórico legado inconsistente
- comparação entre saldo legado e saldo novo

### Testes de integração

- web usando Inventory Engine
- mobile usando Inventory Engine
- Telegram usando Inventory Engine
- formatação amigável do resultado

---

## Critérios de aceite globais

Esta arquitetura só pode ser considerada entregue quando:

- toda nova movimentação passa pelo Inventory Engine
- toda conversão passa pelo Unit Conversion Engine
- o ledger se torna a origem autoritativa do estoque
- StockBalance responde corretamente como projeção
- o rollout não quebra web, mobile ou Telegram
- a migração de leitura ocorre com reconciliação validada

---

## Resultado esperado

Ao final da migração, o GALINT deve ter um sistema de estoque:

- consistente
- previsível
- auditável
- transacional
- extensível
- fácil de manter

O ganho principal não é apenas técnico. O ganho real é operacional: saldo confiável, menos regra duplicada, menor risco de regressão e base sólida para crescimento futuro.
