# Financeiro (antigo “Valor de Estoque”) — Guia de replicação

Este documento descreve como recriar, em outro sistema/instância do GALINT, a funcionalidade anteriormente chamada de **Valor de Estoque**, agora exibida no menu como **Financeiro**.

A ideia central é separar:

- **Valor atual do estoque** (foto do saldo atual × valores do item)
- **Prestação de contas do exercício** (histórico de compras/lancamentos + consumo do período)
- **Rastreabilidade de fracionáveis por local** (litros/kg consumidos por obra/local, com custo interno derivado do preço da embalagem)

## 1) Dependências

- Backend: Flask + SQLAlchemy + Flask-Login
- PDF: `reportlab`
- Consulta CNPJ: `requests`

Se o outro sistema não tiver, instalar:

- `pip install reportlab requests`

## 2) Estrutura de banco (tabelas novas)

As tabelas financeiras ficam no arquivo [galint_flask/models.py](galint_flask/models.py) e são criadas automaticamente quando o app inicia (há `db.create_all()` em [galint_flask/extensions.py](galint_flask/extensions.py)).

Se o outro sistema **não** usa `create_all()` (ou usa migrações), você precisa criar as tabelas abaixo via migração/DDL.

### 2.1 `finance_config`

Tabela de configuração do fechamento do exercício:

- `dia_fechamento` (default 10)
- `mes_fechamento` (default 2)
- `destacar_sem_comprovacao`
- `permitir_fechamento_manual`
- `titulo_relatorio_anual`

Regra: o exercício é definido pelo “fechamento” (ex.: 10/02). Exemplo: exercício `2025/2026` vai de **11/02/2025** até **10/02/2026**.

### 2.2 `finance_fornecedores`

Cadastro mestre de fornecedores/lojas usados nos lançamentos:

- Campos básicos (razão social, fantasia, CNPJ)
- Endereço/contato
- `ativo`
- Metadados de consulta do CNPJ (`api_origem`, `data_consulta_cnpj`)

### 2.3 `finance_fornecedor_item_preferencias`

Relaciona 1 item → 1 fornecedor preferido (para autocomplete e consistência de lançamentos):

- `codigo_item` (único)
- `fornecedor_id`
- `ultima_origem`, `atualizado_por`, `atualizado_em`

### 2.4 `finance_lancamentos`

Livro-razão das entradas financeiras do almoxarifado (cada lançamento representa uma compra/entrada incorporada):

- `codigo_item` (FK item)
- `entrada_id` (FK opcional para entrada)
- `fornecedor_id` (FK opcional)
- `categoria_nome`
- `data_lancamento`
- `quantidade`
- `valor_unitario` e `valor_total`
- `origem_valor` (ex.: inventário inicial, compra com NF, doação)
- `tipo_documento`, `numero_documento`
- `comprovacao_status` (comprovado/parcial/sem_comprovacao)
- `observacao`

## 3) Campos necessários para fracionáveis (rastreabilidade)

A rastreabilidade por local usa os campos já existentes em `Saida` (tabela `saidas`), ver [galint_flask/models.py](galint_flask/models.py):

- `local_servico` (texto)
- `quantidade_retirada_em_litros` (float)
- `quantidade_retirada_em_quilos` (float)
- `quantidade_total_embalagem` (float) — capacidade interna da embalagem naquele momento (fallbacks existem)

Regras importantes:

- Não há conversão L↔Kg.
- O custo interno é derivado do preço da embalagem dividido pela capacidade:

  - Se for em litros: `custo_por_litro = preco_embalagem / litros_por_embalagem`
  - Se for em quilos: `custo_por_kg = preco_embalagem / kg_por_embalagem`

Capacidade:

- Primeiro tenta `Saida.quantidade_total_embalagem`.
- Se não houver, usa:
  - `Item.litros_por_embalagem` (quando consumo é em litros)
  - `Item.grandeza_referencia` (quando consumo é em quilos)

## 4) Backend (serviços)

### 4.1 Serviço financeiro

Arquivo: [galint_flask/services/finance_service.py](galint_flask/services/finance_service.py)

Responsabilidades:

- Config do exercício: `get_config()`, `update_config()`, `resolve_exercise()`
- Fornecedores: CRUD + autocomplete + consulta por CNPJ
- Livro-razão: `register_financial_entry()`
- Relatório: `get_stock_value_report()`
- PDF: `build_stock_value_pdf()`

Pontos críticos do relatório:

- `total_investido_exercicio`: soma do `finance_lancamentos` no período.
- `total_consumido_exercicio`: consumo do período (saídas) valorizado por `avg_unit` do exercício quando existir, senão usa `preco_compra_unitario` do item.
- `consumo_fracionado_por_local`: agregação por `Saida.local_servico` para saídas com litros/kg.

### 4.2 “Exercícios disponíveis”

O `get_available_exercises()` considera a janela temporal combinada de:

- `finance_lancamentos.data_lancamento`
- `saidas.data_saida`

Isso evita “sumir” exercício quando só há saídas (ou só há lançamentos).

## 5) Rotas (endpoints)

### 5.1 Estoque → Financeiro

Blueprint: [galint_flask/views/inventory.py](galint_flask/views/inventory.py)

- `GET /itens/valor-estoque` → tela Financeiro (admin)
- `GET /itens/valor-estoque/pdf` → exportação PDF (admin)

### 5.2 Configurações → Fornecedores

Blueprint: [galint_flask/views/config.py](galint_flask/views/config.py)

- `GET/POST /config/fornecedores`
- `GET /config/api/fornecedores/autocomplete`
- `GET /config/api/fornecedores/cnpj/<cnpj>`

## 6) Frontend (templates)

Arquivos principais:

- Tela Financeiro: [galint_flask/templates/inventory/stock_value.html](galint_flask/templates/inventory/stock_value.html)
  - Cards por categoria (expansíveis)
  - KPIs do exercício
  - Seção “Consumo fracionado por local”
  - Botão PDF

- Item (aba Financeiro): [galint_flask/templates/inventory/form.html](galint_flask/templates/inventory/form.html)
  - Seleção/autocomplete de fornecedor
  - Origem do valor, tipo de documento, comprovação

- Cadastro de fornecedores: [galint_flask/templates/config/fornecedores.html](galint_flask/templates/config/fornecedores.html)

- Robustez de JSON em fetch: [galint_flask/templates/inventory/list.html](galint_flask/templates/inventory/list.html)
  - Helper `readJsonResponse()` para tratar redirecionamento/401/403 e respostas não-JSON.

## 7) Menu (nomenclatura solicitada)

Arquivo: [galint_flask/templates/sidebar_layout.html](galint_flask/templates/sidebar_layout.html)

- Grupo retrátil continua: **Estoque**
- Submenu “Estoque” vira: **Itens Cadastrados**
- Submenu “Valor de Estoque” vira: **Financeiro**

Rotas permanecem as mesmas (`/itens` e `/itens/valor-estoque`).

## 8) Checklist de validação (no sistema alvo)

1. Subir o sistema e validar que as tabelas financeiras existem (`finance_*`).
2. Acessar **Configurações → Fornecedores** e:
   - cadastrar manualmente
   - testar busca por CNPJ
   - testar autocomplete
3. Criar/editar um item e preencher a aba **Financeiro**.
4. Registrar entradas (via item e/ou NF) e confirmar que geram lançamentos em `finance_lancamentos`.
5. Abrir **Estoque → Financeiro**:
   - mudar exercício no seletor
   - exportar PDF
6. Criar uma **Saída fracionada** com `local_servico` + litros/kg e conferir:
   - seção “Consumo fracionado por local”
   - total por local e totais gerais

## 9) Observações importantes

- Se não houver `reportlab`, o PDF falha com mensagem explícita.
- O consumo fracionado por local só aparece quando existirem saídas com litros/kg no exercício.
- Diferenças pequenas por arredondamento são esperadas (valores são arredondados para centavos na agregação).
