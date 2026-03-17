# GALINT

GALINT é o Gerenciador de Almoxarifado Inteligente: uma plataforma de operação, rastreabilidade, auditoria e decisão para estoque, compras, documentos fiscais, custódia de ferramentas, automações e integração mobile.

Hoje o sistema reúne quatro frentes principais no mesmo produto:

- operação diária do almoxarifado com entradas, saídas, devoluções e saldo consolidado
- rastreabilidade de item, lote, validade, embalagem, documento fiscal e histórico financeiro
- governança operacional com relatórios, alertas, auditoria e painéis analíticos
- integrações auxiliares com Telegram, geração de PDFs/XLSX e aplicativo mobile

## O que o GALINT é hoje

O núcleo do sistema continua sendo Flask + PostgreSQL, mas o produto deixou de ser apenas um cadastro de estoque. Ele agora cobre o fluxo completo de abastecimento e controle:

- dashboard operacional com KPIs reais do almoxarifado, alertas de estoque, distribuição por categoria e feeds vivos
- cadastro e edição de itens com abas técnicas, laboratoriais, financeiras e rastreabilidade completa
- nova estrutura robusta para entradas por NF, cupom ou documento, preservando compatibilidade com dados legados
- cadastro mestre de fornecedores com consulta por CNPJ, pesquisa rápida e reutilização em múltiplos fluxos
- financeiro vinculado ao item, com fornecedor, documento, chave de acesso, datas de emissão e recebimento
- controle de custódia de ferramentas com distinção entre empréstimo temporário e custódia permanente
- alertas e notificações no Telegram para eventos operacionais e pendências
- relatórios exportáveis em PDF e XLSX para operação, auditoria e acompanhamento gerencial
- app mobile em galint-mobile para extensão do ecossistema GALINT

## Principais capacidades

### Estoque e operação

- cadastro de itens com marca, categoria, unidade, embalagem, foto e observações
- movimentações de entrada, saída e devolução
- cálculo operacional de saldo por embalagem e equivalente interno
- suporte a unidades dinâmicas como rolo, pacote, caixa e lata
- bloqueios e validações para evitar inconsistência em edição de item

### Documentos de entrada

- fluxo estruturado para registrar entradas por NF ou cupom sem corromper o histórico legado
- persistência de empresa, CNPJ, número do documento, chave de acesso, data de emissão e data de recebimento
- autocomplete por número de NF com preenchimento de dados da empresa
- itens da NF digitáveis com autocomplete e reaproveitamento de cadastros existentes

### Fornecedores e financeiro

- página moderna de fornecedores com formulário assistido por CNPJ
- botão Cadastrar fornecedor no menu Estoque
- modal inicial no cadastro de novo item para verificar se o fornecedor já existe
- pesquisa e seleção de fornecedor antes do cadastro do item
- preenchimento automático da aba Financeiro ao escolher fornecedor
- histórico financeiro sincronizado com metadados documentais do item

### Custódia, alertas e auditoria

- custódia permanente e empréstimo temporário de ferramentas
- alertas Telegram individuais e agrupados por funcionário
- relatórios separados por tipo de custódia
- feed de saídas recentes no dashboard
- painel de ferramentas em custódia com atualização em tempo real
- alertas visuais no dashboard para devolução pendente: atenção em amarelo a partir de 16h40 e alerta crítico em vermelho após 17h

### Experiência e interface

- identidade visual unificada como Gerenciador de Almoxarifado Inteligente
- páginas críticas com cards modernos, leitura rápida e foco operacional
- menu lateral reorganizado para refletir o fluxo real de uso
- formulários orientados por contexto, com menos retrabalho manual

## Arquitetura resumida

### Backend

- Flask
- SQLAlchemy
- Alembic / Flask-Migrate
- PostgreSQL

### Frontend

- Jinja2
- Bootstrap
- JavaScript vanilla

### Integrações e apoio

- Telegram
- geração de PDF e XLSX
- build mobile em galint-mobile

## Estruturas importantes do domínio

Alguns blocos passaram a ser centrais na arquitetura atual:

- Item
- FinanceLedgerEntry
- FinanceSupplier
- FinanceSupplierPreference
- DocumentoEntradaEstoque
- DocumentoEntradaEstoqueItem

Essas estruturas permitem coexistência entre legado e modelo novo, mantendo o sistema utilizável durante a evolução do banco e dos fluxos.

## Fluxos mais importantes do produto

### 1. Cadastro de novo item

- o usuário inicia o item
- o sistema pergunta primeiro se já existe fornecedor cadastrado
- se existir, a aba Financeiro já nasce parcialmente preenchida
- o item pode guardar documento, chave de acesso e datas relevantes

### 2. Entrada por NF ou cupom

- o usuário informa a NF
- o sistema tenta autocomplete dos dados da empresa
- os itens podem ser vinculados ao catálogo atual
- o documento fica rastreável no item e no histórico financeiro

### 3. Operação diária do estoque

- entradas, saídas e devoluções atualizam saldo
- o dashboard expõe quantidade operacional, alertas e distribuição por categoria
- relatórios podem ser gerados para acompanhamento e auditoria

### 4. Ferramentas em custódia

- a retirada pode ser temporária ou permanente
- empréstimos temporários entram em monitoramento
- alertas e relatórios são disparados conforme regra operacional
- no dashboard, cards de custódia já atrasados pulsam em vermelho; antes disso, a interface sobe o nível de atenção por horário de fechamento operacional

## Arquivos e áreas relevantes

- galint_flask/templates/dashboard/index.html: dashboard principal
- galint_flask/templates/inventory/form.html: cadastro e edição de item
- galint_flask/templates/inventory/list.html: listagem de itens e cards de categoria
- galint_flask/templates/config/fornecedores.html: cadastro mestre de fornecedores
- galint_flask/views/inventory.py: rotas do fluxo de item e integração com financeiro
- galint_flask/services/inventory.py: regras principais do estoque
- galint_flask/services/finance_service.py: histórico e integração financeira
- galint_flask/models.py: modelos persistentes
- migrations/versions: evolução do schema
- galint-mobile: aplicação mobile do ecossistema

## Banco e migrations

O projeto usa Alembic para evolução do schema. As mudanças recentes reforçaram a persistência documental no item e no histórico financeiro, incluindo:

- chave de acesso
- data de emissão do documento
- data de recebimento do documento

Essa linha evolutiva foi desenhada para ser segura em ambiente com dados legados e múltiplas iterações de banco.

## Execução local

### Pré-requisitos

- Python 3.x
- PostgreSQL configurado
- ambiente virtual criado em .venv

### Subida da aplicação

No workspace atual, o projeto já possui task para iniciar o servidor Flask com as variáveis de ambiente esperadas. Também é possível executar diretamente o app pela venv.

Exemplo:

```powershell
.\.venv\Scripts\python.exe app.py
```

## Documentação complementar

- [README_PERCENTUAL_MOVIMENTOS.md](README_PERCENTUAL_MOVIMENTOS.md): detalhamento do relatório Percentual Movimentos
- [BUILD_APK_v1.3.0_INSTRUCOES.md](BUILD_APK_v1.3.0_INSTRUCOES.md): instruções de build do app
- [DB_MIGRATION.md](DB_MIGRATION.md): notas de migração de banco

## Direção atual do produto

GALINT hoje é uma plataforma operacional de almoxarifado com rastreabilidade real de entrada, fornecedor, documento e custódia. O foco deixou de ser apenas cadastrar saldo e passou a ser manter contexto, prova operacional e continuidade entre estoque, financeiro, auditoria e mobile.


