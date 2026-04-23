# GALINT

GALINT é o Gerenciador de Almoxarifado Inteligente: uma plataforma de operação, rastreabilidade, auditoria e decisão para estoque, compras, documentos fiscais, custódia de ferramentas, automações e integração mobile.

Hoje o sistema reúne quatro frentes principais no mesmo produto:

- operação diária do almoxarifado com entradas, saídas, devoluções e saldo consolidado
- rastreabilidade de item, lote, validade, embalagem, documento fiscal e histórico financeiro
- governança operacional com relatórios, alertas, auditoria e painéis analíticos
- integrações auxiliares com Telegram, geração de PDFs/XLSX e aplicativo mobile

## Mapa detalhado do produto

O repositório principal já não representa apenas uma aplicação web simples. Ele concentra um ecossistema com múltiplos módulos, páginas especializadas e dois aplicativos satélites separados.

### Aplicação web principal

A aplicação Flask é o núcleo do GALINT e cobre as áreas abaixo.

#### Dashboard

- consolida KPIs do almoxarifado
- mostra alertas operacionais e leituras rápidas de saúde do estoque
- funciona como centro de navegação da operação

Arquivos principais:

- `galint_flask/templates/dashboard/index.html`
- `galint_flask/views/dashboard.py`

#### Lançamentos

- entrada de materiais
- saída operacional
- devoluções e cenários correlatos
- validações de quantidade, unidade e integridade da movimentação

Arquivos principais:

- `galint_flask/templates/movements/index.html`
- `galint_flask/templates/movements/entrada.html`
- `galint_flask/templates/movements/saida.html`
- `galint_flask/views/movements.py`

#### Estoque e itens cadastrados

- cadastro e edição completa de itens
- formulário com abas técnicas, financeiras e documentais
- listagem por categoria com cards operacionais
- assistente rápido de imagem direto no card do item
- modal de apoio para foto via URL, upload e pré-visualização
- cálculo e visão de valor de estoque

Arquivos principais:

- `galint_flask/templates/inventory/list.html`
- `galint_flask/templates/inventory/form.html`
- `galint_flask/templates/inventory/form_tabs.html`
- `galint_flask/templates/inventory/stock_value.html`
- `galint_flask/views/inventory.py`

#### Documentos fiscais

- registro e consulta de NFs, cupons e documentos relacionados
- ajuda contextual por campo e por ação
- inclusão assistida de item em NF
- filtro por período, fornecedor e tipo documental
- fechamento operacional de compras por janela temporal

Arquivos principais:

- `galint_flask/templates/nf/index.html`
- `galint_flask/views/nf.py`

#### Laboratório de lojas

- análise comparativa de compras
- apoio à leitura de fornecedores, preços e documentos
- espaço operacional de inspeção e cruzamento de dados de aquisição

Arquivos principais:

- `galint_flask/templates/inventory/suppliers_lab.html`
- `galint_flask/views/inventory.py`

#### Fornecedores e financeiro

- cadastro mestre de fornecedores
- apoio por CNPJ
- vínculo de fornecedor, documento, chave de acesso e datas ao item
- sincronização com histórico financeiro
- visão de compra e reposição no estoque

Arquivos principais:

- `galint_flask/templates/config/fornecedores.html`
- `galint_flask/services/finance_service.py`
- `galint_flask/views/inventory.py`

#### Ferramentas, custódia e reparos

- custódia temporária e permanente
- relatórios por tipo de custódia
- detalhe do responsável e histórico da ferramenta
- baixa em lote por múltipla seleção no dashboard e na ficha do colaborador
- reaproveitamento de foto por matrícula para leitura operacional
- acompanhamento de itens em reparo

Arquivos principais:

- `galint_flask/templates/tool_custody/index.html`
- `galint_flask/templates/tool_custody/detail.html`
- `galint_flask/templates/tool_custody/reports.html`
- `galint_flask/templates/reparo/list.html`
- `galint_flask/templates/reparo/detalhes.html`
- `galint_flask/views/tool_custody.py`
- `galint_flask/views/reparo.py`

#### Inventário de materiais

- área específica para leitura e operação de materiais
- fluxo dedicado para itens avariados

Arquivos principais:

- `galint_flask/templates/inventario_materiais/index.html`
- `galint_flask/templates/inventario_materiais/avariados.html`
- `galint_flask/views/inventario_materiais.py`

#### Relatórios e auditoria

- relatórios gerais e por item
- percentual de movimentos
- PDFs e XLSX para operação, auditoria e prestação de contas

Arquivos principais:

- `galint_flask/templates/reports/index.html`
- `galint_flask/templates/reports/by_item.html`
- `galint_flask/templates/reports/percentual_movimentos.html`
- `galint_flask/views/reports.py`

#### Usuários

- cadastro de usuários
- histórico e permissões
- foto do usuário vinculada à matrícula, com reaproveitamento no login
- apoio à rastreabilidade operacional por colaborador

Arquivos principais:

- `galint_flask/templates/users/list.html`
- `galint_flask/templates/users/form.html`
- `galint_flask/templates/users/history.html`
- `galint_flask/views/users.py`

#### Telegram, notificações e preferências

- configuração de integração Telegram
- histórico de notificação
- preferências de recebimento
- apoio à operação de alertas agrupados e notificações auditáveis

Arquivos principais:

- `galint_flask/templates/telegram/config.html`
- `galint_flask/templates/telegram/historico.html`
- `galint_flask/templates/telegram/notification_preferences.html`
- `galint_flask/views/telegram_config.py`

#### Painel web mobile

- governança dos usuários e dispositivos Android
- heartbeat, versões APK, score de operabilidade e auditoria
- bloqueio, desbloqueio e logout forçado de usuários mobile
- administração de recursos e rollout operacional

Arquivos principais:

- `galint_flask/templates/mobile_panel/dashboard.html`
- `galint_flask/templates/mobile_panel/devices.html`
- `galint_flask/templates/mobile_panel/features.html`
- `galint_flask/templates/mobile_panel/versions.html`
- `galint_flask/templates/mobile_panel/audit.html`
- `galint_flask/views/mobile_panel.py`

#### Configurações administrativas

- backup
- rede
- empresa
- branding do login com imagem de fundo e imagem do card
- relatórios administrativos
- notificações
- mecanismo de conversão
- páginas de atualização e apoio técnico

Arquivos principais:

- `galint_flask/templates/config.html`
- `galint_flask/templates/config_backup.html`
- `galint_flask/templates/config_rede.html`
- `galint_flask/templates/config_notifications.html`
- `galint_flask/templates/config_conversionengine.html`
- `galint_flask/templates/config/empresa.html`
- `galint_flask/templates/config/relatorios.html`
- `galint_flask/templates/updates/index.html`
- `galint_flask/views/config.py`
- `galint_flask/views/pages.py`
- `galint_flask/views/updates.py`

### GALINT Mobile

Pasta:

- `galint-mobile`

Papel no ecossistema:

- levar operação do almoxarifado para o campo
- permitir uso em celular para retirada, devolução, consulta e rotinas operacionais conforme permissão
- gerar e compartilhar relatórios mobile
- integrar-se ao backend Flask por API REST

Capacidades centrais já documentadas no projeto:

- login e autenticação contra o backend
- estoque com filtros por categoria
- retirada e devolução em campo
- relatórios diários e mensais em PDF e XLSX
- compartilhamento nativo
- integração com o painel web mobile para governança do parque instalado

Documentos úteis:

- `galint-mobile/README.md`
- `PAINEL_WEB_MOBILE.md`
- `BUILD_APK_v1.3.0_INSTRUCOES.md`
- `GUIA_REPLICACAO_APK.md`

### GALINT Notify

Pasta:

- `galint-notify`

Papel no ecossistema:

- funcionar como app separado de notificações, inbox, consulta e relatórios
- manter um fluxo informacional separado do app operacional principal

Capacidades centrais:

- login em endpoints próprios de notify
- registro de push token
- inbox persistente no backend
- marcação de leitura
- download e compartilhamento de relatórios
- apoio à consulta sem misturar esse app com cadastros e lançamentos operacionais

Documentos úteis:

- `galint-notify/README.md`
- `GALINT_NOTIFICATION_APP_VIABILIDADE.md`

### ConversionEngine

O mecanismo de conversão é um módulo técnico central do projeto atual.

Responsabilidades:

- analisar dumps SQL, ZIPs e bases SQLite
- calcular compatibilidade com o schema-alvo do GALINT
- gerar pacote técnico para homologação e auditoria
- liberar implantação direta apenas em cenários seguros para PostgreSQL

Arquivos e docs principais:

- `galint_flask/templates/config_conversionengine.html`
- `galint_flask/views/pages.py`
- `CONVERSIONENGINE.md`

### Estrutura documental já existente no workspace

Além deste README, o projeto já possui documentação complementar importante:

- `CONVERSIONENGINE.md`
- `PAINEL_WEB_MOBILE.md`
- `GALINT_NOTIFICATION_APP_VIABILIDADE.md`
- `README_PLANO_EVOLUCAO_GALINT.md`
- `PLANO_IMPLANTACAO_BACKUP_GALINT.md`
- `README_BACKUP_COMPLETO_CONVERSIONENGINE.md`
- `SISTEMA_REPAROS_README.md`
- `README_PERCENTUAL_MOVIMENTOS.md`
- `FINANCEIRO_VALOR_DE_ESTOQUE.md`
- `RASTREABILIDADE_IMPLEMENTACAO.md`
- `APLICACAO_EM_OUTRA_MAQUINA.md`

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
- seleção múltipla e baixa em lote no feed do dashboard
- seleção múltipla e baixa em lote na tela detalhada do funcionário
- alertas visuais no dashboard para devolução pendente: atenção em amarelo a partir de 16h40 e alerta crítico em vermelho após 17h

### Atualizações recentes do ciclo atual

- tela de Documentos Fiscais ampliada com ajuda contextual por campo, visual mais guiado para operação e suporte a leitura rápida dos botões principais
- controle por período nas compras, com janela filtrável, indicadores por fornecedor e fechamento operacional do ciclo documental
- inclusão assistida de item em NF para reduzir retrabalho durante o vínculo entre documento fiscal e catálogo já existente
- cards de categoria do estoque com assistente rápido de imagem, permitindo buscar, pré-visualizar e aplicar foto do item sem abrir a tela completa de edição
- modal de apoio para foto do item reduzido e adaptado para fluxo operacional mais curto dentro da listagem
- README principal consolidado com regras canônicas de entrada, conversão, saldo, embalagem, custódia, branding e ambiente para evitar regressão semântica
- login dark hero consolidado com branding configurável, imagem do card redonda e troca automática para foto do usuário quando a matrícula possuir imagem vinculada
- tela de usuários ampliada com upload e remoção de foto por matrícula, sem criar uma segunda fonte paralela de avatar
- feed de custódia do dashboard revisado para suportar múltipla seleção, botão Selecionar todas/Limpar seleção, baixa em lote e contenção de textos longos dentro dos cards
- tela detalhada da custódia revisada com múltipla seleção para ferramentas temporárias, confirmação única de baixa em lote e preview dos itens selecionados no modal

## Regras canônicas para entrada, cálculo, conversão e processamento

Esta seção existe para evitar que o sistema volte a errar semântica de entrada, saldo, embalagem, valor financeiro ou projeção física.

Se houver dúvida entre uma leitura antiga, um comportamento legado e o que o sistema deve fazer hoje, esta é a ordem correta de interpretação:

1. o saldo autoritativo nasce no ledger
2. a unidade autoritativa é a unidade canônica do item
3. embalagem é forma operacional de entrada e leitura, não fonte independente de verdade
4. valor financeiro só pode ler saldo reconciliado
5. telas, APIs e relatórios devem consumir projeções do backend, não recalcular saldo no frontend

### Fonte de verdade do estoque

Regra central:

- o único saldo autoritativo deve ser a soma de `StockMovement.quantity_base` na unidade canônica do item

Tudo o que aparece na interface deve derivar dessa base:

- `StockBalance` como cache
- `estoque_embalagens` e `estoque_unidades_soltas` como projeção física operacional
- `saldo_display` como formatação de leitura
- valor financeiro como leitura sobre saldo reconciliado

### Fluxo canônico de uma entrada de item

Toda entrada correta precisa passar mentalmente por esta sequência:

1. o operador informa quantidade e unidade operacional de entrada
2. o sistema resolve a unidade canônica do item
3. o motor de conversão transforma a quantidade operacional em `quantity_base`
4. o movimento é gravado no ledger
5. o cache de saldo é atualizado a partir do ledger
6. a projeção física de embalagem é recalculada a partir do saldo canônico
7. a interface recebe apenas a leitura já reconciliada no backend

Exemplos corretos:

- 1 lata de massa corrida 25 kg entra como 25 kg na base
- 1 rolo de 50 m entra como 50 m na base
- 1 pacote com 1000 unidades entra como 1000 un na base

O erro histórico que o projeto não pode repetir é tratar lata, pacote, caixa, balde, saco, fardo, bombona ou rolo como unidade autoritativa do saldo quando eles são apenas embalagem ou unidade operacional.

### Semântica oficial dos campos de embalagem

Os campos abaixo não podem mais ser reinterpretados de forma livre:

- `unidades_por_embalagem`: quantidade interna contida em uma embalagem fechada
- `estoque_embalagens`: quantidade de embalagens fechadas
- `estoque_unidades_soltas`: resto fracionado de uma embalagem já aberta

Isso significa:

- o saldo base não deve ser promovido diretamente para `estoque_embalagens`
- a decomposição correta sempre parte do saldo canônico em unidade base
- a UI deve explicar embalagem como conteúdo e contagem física, não como fonte paralela de saldo

### Regras especiais para jogos, kits e conjuntos

Itens com descrição e semântica de `JOGO`, `KIT` ou `CONJUNTO` não devem reutilizar a lógica de embalagem como se fossem estoque fracionável comum.

Regra operacional consolidada:

- para jogos, kits e conjuntos de ferramentas, `unidades_por_embalagem` representa composição interna, não unidade de saldo
- esses itens devem convergir para `Unidade` como semântica de estoque
- metadata de embalagem não deve inflar o saldo desses itens durante backfill, dual-write ou leitura

### Como o valor financeiro deve ser calculado

Regra consolidada:

- `valor_estoque_*_total = saldo_fisico_total × preco_*_unitario`

E atenção:

- `preco_*_unitario` é o preço da unidade interna do item
- não é preço por pacote, caixa, lata, saco ou outra embalagem operacional
- se o saldo estiver semanticamente errado, o valor financeiro também ficará errado

### Regras inegociáveis para nunca mais errarmos nisso

Estas regras são obrigatórias em qualquer correção futura:

- nenhum `StockMovement` novo pode ser gravado com unidade base de embalagem
- nenhum cálculo financeiro pode usar saldo não reconciliado
- nenhuma tela deve remontar saldo físico por conta própria no frontend
- nenhum ajuste pode alinhar apenas uma camada deixando ledger, cache e projeção física divergentes
- nenhum item embalado deve aceitar operação sem unidade canônica resolvida
- nenhum fluxo paralelo deve gravar estoque fora do writer central

### Arquivos que concentram essa lógica

- `galint_flask/services/inventory.py`
- `galint_flask/services/inventory_engine.py`
- `galint_flask/services/balance_provider.py`
- `galint_flask/services/embalagem_service.py`
- `galint_flask/services/unit_conversion_engine.py`
- `galint_flask/services/legacy_stock_normalizer.py`
- `galint_flask/models.py`

Para o desenho arquitetural completo do tema, a referência canônica detalhada é [README_ESTOQUE_UNIFICADO.md](README_ESTOQUE_UNIFICADO.md).

## O que foi corrigido para impedir regressão semântica

As correções recentes consolidaram alguns pontos que antes ficavam espalhados entre tela, legado, cache e heurística.

### Embalagem e saldo físico

- itens embalados deixaram de promover saldo base diretamente para contagem de embalagens
- a decomposição do saldo em embalagens fechadas e unidades soltas precisa sempre usar o fator correto de embalagem
- a recomposição operacional deve partir do saldo reconciliado do ledger

### Cutover, dual-write e cache

- o cutover deve gravar `result.ledger_balance` em `StockBalance.quantity_base`
- reutilizar cache antigo sem reconstrução pode preservar saldo físico corrompido
- quando necessário, a reconstrução segura deve partir da soma dos movimentos, não do read-model físico já inflado

### Documentos de entrada, NF e vínculo com item

- o fluxo de entrada documental foi estabilizado para manter fornecedor, número do documento, chave de acesso, datas de emissão e recebimento vinculados ao item e ao histórico financeiro
- a inclusão assistida de item em NF existe para reduzir retrabalho e diminuir divergência entre catálogo, documento e lançamento operacional
- o objetivo da entrada não é apenas somar saldo; é preservar rastreabilidade documental e semântica correta de unidade

## Custódia de ferramentas: estado atual consolidado

O módulo de custódia passou a trabalhar com leitura operacional mais forte e menos dependente de ação unitária isolada.

### O que mudou no dashboard

- o feed por colaborador agora aceita múltipla seleção na custódia diária
- cada clique alterna seleção da ferramenta
- existe atalho de `Selecionar todas` e `Limpar seleção`
- o botão principal executa baixa em lote de forma sequencial
- se parte da operação falhar, apenas as falhas permanecem selecionadas para nova tentativa
- os cards receberam reforço de `min-width` e `overflow-wrap` para impedir vazamento de textos longos

### O que mudou na tela detalhada do colaborador

- a coluna de custódia temporária agora permite selecionar vários cards
- a baixa em lote abre um modal único com preview do conjunto selecionado
- as ações unitárias continuam existindo, mas o fluxo de lote passou a ser o padrão mais rápido para operação diária

### Arquivos principais da custódia recente

- `galint_flask/templates/dashboard/index.html`
- `galint_flask/templates/tool_custody/detail.html`
- `galint_flask/views/tool_custody.py`
- `galint_flask/services/tool_custody_service.py`

## Login, branding e foto de usuário

O login deixou de ser apenas uma tela estática e passou a ter dois níveis de personalização.

### Branding global do login

Hoje o sistema já suporta:

- fundo configurável da página de login
- imagem configurável do card do login
- persistência de branding via configuração administrativa da empresa

### Foto de usuário vinculada à matrícula

Além do branding global, o sistema agora suporta:

- upload de foto no cadastro de usuários
- remoção da foto atual sem criar outro cadastro paralelo de avatar
- reaproveitamento da mesma foto por matrícula no login
- fallback automático para a imagem global do card quando a matrícula não tiver foto
- imagem do card do login em formato redondo para acomodar tanto branding quanto foto de pessoa

Decisão importante de arquitetura:

- a foto do usuário não criou uma nova coluna obrigatória no banco
- o sistema reaproveita o armazenamento por matrícula já usado em contexto operacional
- isso evita duas fontes de verdade para a imagem da mesma pessoa

Arquivos principais:

- `galint_flask/templates/auth/login.html`
- `galint_flask/templates/users/form.html`
- `galint_flask/views/auth.py`
- `galint_flask/views/users.py`
- `galint_flask/services/users.py`
- `galint_flask/services/tool_custody_service.py`

## Ambiente, execução local e armadilhas conhecidas

Estas observações precisam ficar no README principal porque já causaram erro real em runtime.

### Flask sem reloader automático

- `app.py` sobe o servidor com `use_reloader=False`
- mudança em rota Python, blueprint, guard global ou lógica de serviço não entra sozinha no processo já em execução
- se uma rota nova parecer inexistente ou se um comportamento antigo persistir, reinicie manualmente o `python.exe app.py`

### Hierarquia de `.env`

- o projeto carrega `.env` e `.env.local` com prioridade para a raiz do projeto
- use `.env.local` para credenciais específicas por máquina
- isso evita herdar configuração errada de pastas acima no Windows

### Background services em diagnósticos

- para smoke tests e diagnósticos read-only, prefira `GALINT_DISABLE_BACKGROUND_SERVICES=true`
- isso evita scheduler, polling do Telegram e side effects de startup durante verificação local

### Templates base e JavaScript de páginas filhas

- `galint_flask/templates/base.html` precisa renderizar `{% block scripts %}{% endblock %}` perto do fim do `body`
- sem isso, a página pode abrir, mas perde o JavaScript inline da tela filha e o operador enxerga comportamento aparentemente aleatório em botões, uploads e bindings

### Data e hora

- datas e horas exibidas ao usuário devem usar `TimeService.now_local()` no backend
- evitar `new Date().toISOString().slice(0, 10)` no frontend, porque esse atalho usa UTC e pode adiantar o dia no Windows UTC-3

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

Observação importante:

- o projeto roda com `use_reloader=False`; qualquer mudança em rotas Python, blueprints ou templates carregados por uma instância antiga pode exigir restart manual do Flask para refletir o código atual

## Implantações recentes

O ciclo mais recente concentrou mudanças visuais, operacionais e de governança em áreas críticas do sistema.

- novo módulo ConversionEngine em Configurações, com visual dark, staging isolado por job, upload de SQL/ZIP/SQLite, score de compatibilidade, telemetria em tempo real, barra de progresso, pacote técnico e opção de download ou implantação direta da nova base quando a origem estiver apta ao pipeline PostgreSQL
- tela fiscal expandida com ajuda contextual, filtro e fechamento por período, além de inclusão assistida de item em NF
- estoque por categoria expandido com assistente rápido de imagem diretamente nos cards dos itens
- pipeline oficial de restauração blindado para o ConversionEngine, com bloqueio temporário de acessos durante restore, drenagem de conexões PostgreSQL, timeouts desativados no subprocesso de restore e reparo idempotente de colunas críticas após a implantação
- dashboard com cards operacionais refinados para leitura rápida de financeiro e fornecedores
- reforço no bloqueio de campos financeiros na edição de item depois do primeiro salvamento
- páginas de auditoria de ferramentas, reparos, detalhes do funcionário e detalhes do reparo com visual dark padronizado
- suporte a foto do funcionário em custódia e reaproveitamento de foto do item na tela de reparo
- sidebar Mako legada reescrita para não perder menus em páginas antigas do fluxo de lançamentos
- páginas administrativas Telegram, Backup, Rede, Empresa, Relatórios e Atualizações migradas para o padrão visual dark em abas
- fluxos de Materiais Comuns, Ferramentas e Fracionados revisados por dentro, com containers dark e leitura operacional melhorada
- Painel Mobile elevado a centro de controle, com KPIs, diagnóstico de operabilidade, leitura de Android e APK, bloqueio de usuário, logout forçado e edição de nome, cargo, setor e senha

## Como replicar este pacote

Existe uma observação prática importante neste workspace:

- a pasta `galint-mobile` está tratada como repositório Git separado
- o vínculo dela com o repositório principal ainda não está completamente normalizado por `.gitmodules`
- para replicação fiel em outra máquina, consultar também o documento [APLICACAO_EM_OUTRA_MAQUINA.md](APLICACAO_EM_OUTRA_MAQUINA.md)

### 1. Preparar ambiente

- garantir Python e PostgreSQL ativos no ambiente local
- criar ou reutilizar a venv em .venv
- instalar dependências do projeto

### 2. Subir o servidor

- usar a task existente Run GALINT server no workspace
- ou executar manualmente:

```powershell
.\.venv\Scripts\python.exe app.py
```

### 3. Garantir disponibilidade do Painel Mobile

- o painel usa o blueprint /mobile-panel
- o acesso depende da configuração FEATURE_MOBILE_PANEL_ENABLED, que neste repositório passou a assumir True por padrão em galint_flask/config.py
- como o projeto roda com use_reloader=False, qualquer mudança em rotas Python exige restart manual do Flask

### 4. Validar os fluxos alterados

- revisar o dashboard principal
- abrir Auditoria de Ferramentas e Em Reparo
- abrir detalhes do funcionário e testar upload de foto
- acessar Telegram, Backup, Rede, Empresa, Relatórios e Atualizações
- abrir Materiais Comuns, Ferramentas e Fracionados e conferir contraste dos containers dark
- acessar /mobile-panel/ com usuário administrador para validar KPIs, dispositivos e usuários mobile

### 5. Replicar o ConversionEngine

- abrir Configurações e acessar ConversionEngine pelo card ou pelo menu lateral
- garantir login com usuário administrador, porque os endpoints de job e implantação usam autenticação leve por sessão administrativa
- enviar um `.sql`, `.zip` com `.sql` ou SQLite, ou uma base `.sqlite`/`.db`; para deploy direto, preferir exportação `pg_dump` em formato plain
- acompanhar a análise pela barra de progresso, pelos KPIs e pela telemetria do job
- ao concluir:
	- usar Baixar nova base convertida para acionar o diálogo de download do Windows no navegador quando o dump estiver apto
	- usar Baixar pacote técnico para auditoria, homologação e ajustes manuais
	- usar Implantar nova base agora apenas quando o módulo liberar o deploy direto
- lembrar que origens ZIP e SQLite entram em staging e diagnóstico; o GALINT não passa a operar nativamente em MySQL ou SQLite com essa etapa
- depois de uma implantação direta, validar a aplicação e reiniciar manualmente o Flask se houver mudança recente de rotas Python, já que o projeto segue com use_reloader=False

### 6. Estrutura técnica do módulo

- serviço principal em galint_flask/services/conversion_engine.py
- rotas e downloads em galint_flask/views/pages.py
- interface dark em galint_flask/templates/config_conversionengine.html
- documentação detalhada do mecanismo em CONVERSIONENGINE.md

### 7. Como a página do ConversionEngine foi construída

- a entrada visual fica em Configurações e usa uma rota administrativa dedicada em galint_flask/views/pages.py para montar dashboard inicial, documentação em Markdown e permissões de uso
- a interface em galint_flask/templates/config_conversionengine.html foi desenhada em visual dark para combinar com o restante do painel administrativo e priorizar leitura contínua de progresso, KPIs e mensagens operacionais
- o conteúdo técnico exibido na mesma tela vem de CONVERSIONENGINE.md, convertido para HTML no servidor, para manter uma única fonte de documentação do módulo
- a análise roda em job assíncrono, preservando a interface responsiva enquanto o backend varre dumps SQL, ZIPs ou bases SQLite em staging isolado por job
- os botões de baixar SQL, baixar pacote técnico e implantar nova base apontam para endpoints separados, o que permite liberar ou bloquear cada ação conforme a compatibilidade real detectada
- a etapa de implantação direta foi ligada ao pipeline oficial de backup/restore do GALINT para evitar um restaurador paralelo com comportamento divergente
- a tela também passou a exibir aviso de manutenção durante a implantação, deixando explícito para o operador quando o sistema está temporariamente protegido para concluir o restore

## Erros corrigidos durante a implantação

- divergência entre local e remoto resolvida com cherry-pick e atualização controlada dos commits necessários
- BuildError em rotas novas corrigido após restart manual do Flask, porque o servidor não usa reloader
- rota de upload de foto de funcionário estabilizada em tool_custody após recarga do processo ativo
- menus faltando no sidebar de páginas antigas corrigidos ao reescrever o arquivo legado galint_flask/templates_mako/sidebar_layout.mako
- helper functions inseridas no lugar errado em api_mobile.py foram reposicionadas antes da validação final
- Painel Mobile deixando /mobile-panel/ em 404 corrigido ao habilitar a feature flag por padrão em galint_flask/config.py
- contraste fraco introduzido no fluxo de saídas dark foi corrigido nos estados informativos e vazios de Materiais Comuns e Fracionados
- para o ConversionEngine, a implantação foi fechada com validação de sintaxe em rotas, templates e serviço, além de teste funcional local cobrindo cenário com pacote técnico e cenário com deploy liberado
- erro de timeout de lock no PostgreSQL durante restore foi tratado com drenagem das outras sessões antes do psql e com PGOPTIONS específicos para zerar lock_timeout e statement_timeout no subprocesso de restauração
- falhas pós-restore por colunas ausentes, como entrada_documentos.chave_acesso e itens.preco_compra_chave_acesso, passaram a ser cobertas por correções idempotentes de schema aplicadas logo após a restauração
- consultas indevidas durante a restauração passaram a receber bloqueio controlado, com resposta 503 e mensagem de manutenção, para evitar novas disputas de conexão com a base em implantação
- a conexão com banco de manutenção usada para encerrar sessões foi corrigida para preservar a senha real da URI, evitando falha silenciosa por mascaramento de credencial
- a página do ConversionEngine recebeu banner explícito de manutenção para deixar claro quando a implantação já iniciou e por que parte do sistema fica temporariamente indisponível

## Observações operacionais

- o projeto mistura templates Jinja e Mako; ajustes visuais em lançamentos podem estar em galint_flask/templates_mako e não apenas em galint_flask/templates
- o Painel Mobile usa endpoints administrativos em galint_flask/views/admin_mobile.py e regras de autenticação em galint_flask/views/api_mobile.py
- se uma rota recém-criada parecer inexistente, valide primeiro se o processo Flask ativo foi reiniciado após a alteração
- o ConversionEngine agora aceita `.sql`, `.zip` com `.sql`/SQLite e `.sqlite`/`.db` para análise; a implantação direta continua restrita a artefatos PostgreSQL estruturalmente compatíveis com o GALINT
- como o servidor roda com use_reloader=False, qualquer ajuste em rotas Python, guard de manutenção ou fluxo de restore só entra em vigor depois de reiniciar manualmente o processo Flask ativo

## Documentação complementar

- [README_ESTOQUE_UNIFICADO.md](README_ESTOQUE_UNIFICADO.md): referência canônica de saldo, ledger, unidade base, embalagem, cache e cutover
- [README_PERSONALIZACAO_SAIDAS_DEVOLUCOES.md](README_PERSONALIZACAO_SAIDAS_DEVOLUCOES.md): direção de UX visual para saídas, devoluções, foto do item e futura tela espelho
- [README_CENTRAL_KITS_FERRAMENTAS.md](README_CENTRAL_KITS_FERRAMENTAS.md): desenho do módulo de kits, bolsa-chave e patrimônio de ferramentas
- [README_MENSAGERIA_CONDOMINIAL.md](README_MENSAGERIA_CONDOMINIAL.md): proposta do novo módulo condominial com modelagem relacional, enums, service transacional, migration inicial e blueprint base
- [README_PERCENTUAL_MOVIMENTOS.md](README_PERCENTUAL_MOVIMENTOS.md): detalhamento do relatório Percentual Movimentos
- [BUILD_APK_v1.3.0_INSTRUCOES.md](BUILD_APK_v1.3.0_INSTRUCOES.md): instruções de build do app
- [DB_MIGRATION.md](DB_MIGRATION.md): notas de migração de banco

## Direção atual do produto

GALINT hoje é uma plataforma operacional de almoxarifado com rastreabilidade real de entrada, fornecedor, documento e custódia. O foco deixou de ser apenas cadastrar saldo e passou a ser manter contexto, prova operacional e continuidade entre estoque, financeiro, auditoria e mobile.


