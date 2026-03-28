# README - Plano de Modernizacao Visual e Tecnica do GALINT

## Objetivo

Este plano descreve como modernizar o GALINT com HTML5, CSS3 e Tailwind CSS sem apagar a personalidade operacional que o sistema ja construiu.

O alvo nao e transformar o GALINT em um site generico. O alvo e reforcar o que ele ja e hoje:

- plataforma operacional de almoxarifado
- ambiente tecnico de controle, rastreabilidade e auditoria
- sistema com cara de centro de operacoes, nao de dashboard decorativo
- produto com fluxos densos, validacoes serias e alto uso administrativo

O plano parte do principio de que a modernizacao visual precisa respeitar tres coisas:

1. continuidade da operacao
2. consistencia entre modulos
3. evolucao incremental sem reescrever o frontend inteiro de uma vez

---

## Visao de produto

O GALINT deve evoluir para uma linguagem visual unica, sobria, forte e claramente operacional.

Direcao visual desejada:

- identidade de centro de controle tecnico
- contraste alto para leitura rapida
- hierarquia forte entre contexto, alerta, acao e auditoria
- tabelas e formularios densos, mas legiveis
- modais e drawers como ferramentas operacionais, nao apenas popups
- comportamento responsivo para notebook, tablet e telas menores sem perder densidade

O resultado esperado e um sistema que continue com personalidade industrial e administrativa, mas com acabamento moderno, previsivel e escalavel.

---

## Stack proposta

### Camada estrutural

- HTML5 semantico para layout, formularios, tabelas e dialogs
- Jinja mantido como motor principal de template
- Mako preservado onde ainda existir, com convergencia gradual para o mesmo design system

### Camada visual

- Tailwind CSS para composicao visual e consistencia de espaco, tipografia, cor e estados
- CSS3 para tokens globais, animacoes, efeitos, themes, componentes muito especificos e casos que nao valem utilitario em linha
- CSS variables para identidade central do GALINT

### Camada comportamental

- JavaScript progressivo para modais, drawers, filtros, acoes em lote, feedback inline e estados assincronos
- fetch para acoes remotas ja existentes
- componentes leves em JS antes de considerar qualquer framework maior

### Build e pipeline

- Node apenas para pipeline de Tailwind
- content scan configurado para templates Jinja e Mako
- build de CSS versionado e empacotado no projeto Flask

---

## Principios de design

1. Operacao primeiro
Toda tela deve priorizar leitura, seguranca de acao e contexto do usuario.

2. Personalidade preservada
O GALINT nao deve parecer SaaS generico. Deve parecer sistema tecnico de operacao e governanca.

3. Densidade controlada
O sistema pode continuar denso, mas precisa de ritmo visual, respiro e hierarquia.

4. Acoes criticas bem marcadas
Excluir, restaurar, processar, implantar e reverter devem ter linguagem visual propria.

5. Reuso acima de improviso
Cards, tabelas, filtros, formularios, banners, modais e indicadores devem sair de componentes-base.

6. Migracao por familias
Nao redesenhar pagina por pagina de forma desconectada. Migrar por familias funcionais.

---

## Personalidade visual do GALINT

### O que manter

- linguagem escura e tecnica nas areas administrativas e sensiveis
- sensacao de painel operacional
- destaque forte para risco, status e acao
- tom de produto robusto, serio e utilitario

### O que melhorar

- tipografia mais consistente
- espacos mais padronizados
- tabelas menos cansativas
- filtros e ferramentas mais claros
- hierarquia melhor entre pagina, secao e registro
- estados vazios e erros menos improvisados

### Paleta sugerida

- fundo tecnico: grafite, azul-petroleo, ardosia profunda
- acento primario: azul eletrico controlado
- sucesso: verde operacional
- atencao: ambar industrial
- bloqueio: vermelho de risco
- neutros claros: gelo, cinza tecnico, branco suave

---

## Arquitetura visual proposta

### 1. Layout shell unico

Todo modulo deve compartilhar:

- header superior padronizado
- sidebar modular
- area de conteudo com largura e espacamento consistentes
- barra secundaria de contexto quando necessario
- rodape tecnico discreto

### 2. Sistema de paginas

Cada pagina deve ser composta por blocos previsiveis:

- page header
- action rail
- filtros
- KPIs
- corpo principal
- estado vazio/erro/loading
- acoes finais ou historico

### 3. Sistema de componentes

Componentes base obrigatorios:

- page header
- stat card
- operational card
- alert banner
- form section
- data table
- toolbar de filtros
- badge de status
- stepper
- drawer
- modal
- confirm dialog
- log panel
- skeleton loader

### 4. Sistema de modais

Tipos previstos:

- confirmacao simples
- confirmacao destrutiva
- edicao rapida
- inspecao
- assistente curto
- modal tecnico de log/diagnostico

### 5. Sistema de feedback

- inline validation em formularios
- toast curto para sucesso rapido
- banner para erro operacional
- bloco tecnico expansivel para erro detalhado
- progresso visual padronizado em jobs longos

---

## Estrategia de implementacao

## Fase 0 - Fundacao tecnica

Objetivo:
preparar a base para evolucao visual sem refatorar telas ainda.

Entregas:

- configurar pipeline Tailwind
- definir estrutura de arquivos CSS
- criar tokens globais com CSS variables
- criar layout shell base reutilizavel
- mapear templates Jinja e Mako usados por cada modulo
- definir convencao de classes e componentes

Tecnicas usadas:

- tailwind.config com content scan para galint_flask/templates e galint_flask/templates_mako
- app.css com layers base/components/utilities
- tokens em :root
- classes auxiliares para compatibilizar Bootstrap atual com a fase de transicao

Barreiras futuras:

- risco de conflito com CSS legado
- risco de build nao cobrir templates dinamicos
- risco de utilitarios em excesso sem padrao de componentes

Mitigacao:

- adotar componentes nomeados desde o inicio
- congelar classes legadas criticas durante a fase 0
- testar o build com scan real do projeto inteiro

---

## Fase 1 - Design system do GALINT

Objetivo:
criar a linguagem oficial do produto antes de tocar nas paginas.

Entregas:

- paleta oficial
- escala tipografica
- escala de espacamento
- grid e largura padrao
- botoes por severidade
- campos de formulario padrao
- estilos de tabela
- banners, badges e estados
- sistema de modais e drawers

Tecnicas usadas:

- componentes Tailwind em layers
- classes utilitarias compostas para variantes
- CSS variables para cores, radii, sombras e motion

Barreiras futuras:

- design system fraco vira decoracao sem governanca
- equipes podem voltar a improvisar CSS por pagina

Mitigacao:

- documentar o design system
- manter exemplos reais por componente
- criar checklist de uso antes de cada redesenho

---

## Fase 2 - Shell e navegacao global

Objetivo:
unificar a experiencia base sem alterar profundamente os fluxos ainda.

Entregas:

- novo topo global
- nova sidebar
- page header padrao
- breadcrumbs/contexto
- area de acoes rapidas
- padrao de container

Tecnicas usadas:

- layout semantico com header, aside, main, nav, section
- breakpoints consistentes
- componentes de navegacao com estados ativo, hover e colapsado

Barreiras futuras:

- telas antigas podem depender de espaçamentos ou containers soltos
- sidebars diferentes por modulo podem quebrar alinhamento

Mitigacao:

- criar shell compat layer na base.html
- migrar modulos por adaptacao progressiva

---

## Fase 3 - Familias de pagina prioritarias

Objetivo:
migrar as areas mais acessadas e mais representativas primeiro.

Ordem recomendada:

1. Dashboard
2. Itens cadastrados
3. Cadastro/edicao de item
4. Lançamentos
5. Documentos fiscais
6. Backup + ConversionEngine + Updates

Razao:

- sao as telas que definem a percepcao do produto
- concentram operacao, risco e fluxo administrativo
- servem como modelo para o restante do sistema

---

## Fase 4 - Familias administrativas e analiticas

Objetivo:
expandir o design system para o restante do sistema.

Escopo:

- fornecedores e financeiro
- ferramentas, custodia e reparos
- inventario de materiais e avariados
- relatorios
- usuarios
- Telegram e notificacoes
- painel mobile

Tecnicas usadas:

- reuso de blocos ja consolidados
- padrao de tabela + filtros + detalhe lateral
- padrao de wizard ou modal para operacoes curtas

Barreiras futuras:

- modulos com historico longo de remendos podem exigir limpeza estrutural antes do redesign
- telas com muitas regras de permissao podem demandar testagem mais forte

Mitigacao:

- separar redesign visual de refatoracao funcional quando possivel
- validar perfil admin, supervisor e usuario comum em cada pagina migrada

---

## Fase 5 - Modais, drawers e interacoes criticas

Objetivo:
padronizar os pontos de maior atrito operacional.

Escopo:

- exclusao
- confirmacao destrutiva
- edicao rapida
- detalhe tecnico
- progresso de jobs longos
- diagnosticos
- previews

Tecnicas usadas:

- dialogs acessiveis
- focus trap
- scroll lock
- estados de submit/loading/error
- drawers laterais para detalhe em vez de modais gigantes

Barreiras futuras:

- modais antigos podem estar acoplados a scripts inline
- existe risco de coexistencia caotica entre alert, confirm nativo e modal customizado

Mitigacao:

- inventariar todos os modais atuais
- substituir primeiro os destrutivos e os mais recorrentes

---

## Fase 6 - Responsividade operacional

Objetivo:
deixar o sistema forte em notebook e aceitavel em tablet/mobile administrativo.

Escopo:

- tabelas com comportamento responsivo inteligente
- filtros recolhiveis
- cards adaptativos
- rodapes de acao fixos em telas menores
- drawers no lugar de modais centrais em viewport estreita

Tecnicas usadas:

- grid responsivo do Tailwind
- sticky action bars
- overflow controlado
- breakpoints desenhados para o uso real do GALINT

Barreiras futuras:

- algumas paginas sao densas demais para phone sem redesenho funcional

Mitigacao:

- definir oficialmente quais areas sao desktop-first
- priorizar tablet e notebook em vez de prometer mobile para tudo

---

## Fase 7 - Performance, acabamento e governanca

Objetivo:
fechar a modernizacao com qualidade sustentavel.

Entregas:

- revisão de CSS morto
- consolidacao de componentes duplicados
- padrao de naming
- checklist de acessibilidade
- guideline de novas paginas
- auditoria visual final

Tecnicas usadas:

- purge correto do Tailwind
- lint/style review manual
- inspeção de contraste e keyboard flow

Barreiras futuras:

- crescimento do sistema sem governanca visual volta a degradar o frontend

Mitigacao:

- toda nova tela deve nascer em cima do design system
- toda excecao visual precisa ser justificada

---

## Plano por familias de tela

### Dashboard

Objetivo:
transformar o dashboard em centro de comando.

Estrutura alvo:

- hero operacional
- KPIs principais
- alertas criticos
- atividade recente
- atalhos rapidos
- blocos analiticos resumidos

Riscos:

- excesso de informacao visual
- virar vitrine em vez de painel funcional

### Itens cadastrados

Objetivo:
ser a referencia visual do sistema.

Estrutura alvo:

- busca forte
- filtros persistentes
- lista em modo tabela e card
- saldo, preco, categoria e risco visiveis
- acoes rapidas por item
- modais para foto, edicao curta e acoes em lote

Riscos:

- volume alto de informacao por item
- performance ao misturar imagem, saldo e preco em massa

### Cadastro de item

Objetivo:
reduzir fadiga de cadastro.

Estrutura alvo:

- abas ou secoes bem marcadas
- resumo lateral do item
- validacao inline
- rodape de acao fixo

Riscos:

- formulario excessivamente longo
- regras antigas espalhadas por JS inline

### Lançamentos

Objetivo:
deixar entrada, saida e devolucao coerentes e seguras.

Estrutura alvo:

- contexto da operacao no topo
- formulario central
- painel lateral de saldo e historico
- confirmacao clara antes de gravar

Riscos:

- coexistencia entre templates Jinja e Mako
- scripts antigos de validacao visual

### Documentos fiscais

Objetivo:
unir leitura documental e processamento operacional.

Estrutura alvo:

- tabela com filtros fortes
- linha expansivel ou drawer de detalhe
- status de processamento muito visivel
- modais tecnicos para erro e reprocesso

Riscos:

- fluxos densos e altamente condicionais
- dependencia de regras fiscais e de estoque ao mesmo tempo

### Backup, ConversionEngine e Updates

Objetivo:
formar um trio visualmente consistente de resiliencia e manutencao.

Estrutura alvo:

- pagina de backup com artefatos, risco e acoes
- ConversionEngine como laboratorio tecnico
- updates com governanca de versao e backup previo
- modais destrutivos e tecnicos padronizados

Riscos:

- alta sensibilidade operacional
- progresso e erros precisam ser muito claros

---

## Tecnicas de implementacao recomendadas

1. Tailwind utility-first com component extraction
Nao usar Tailwind como amontoado de classes. Extrair componentes base.

2. CSS variables como contrato visual
Tokens de cor, sombra, radius, spacing e motion em um lugar central.

3. HTML semantico
Main, section, aside, form, table, dialog, nav, header e footer usados corretamente.

4. JavaScript progressivo
Sem reescrever tudo com framework. Modernizar os comportamentos de alto valor primeiro.

5. Layout por families
Tabela administrativa, formulario tecnico, painel de risco, timeline, drawer de detalhe.

6. Design tokens + states
Todo estado importante deve ter variante de cor e comportamento claros.

---

## Barreiras futuras reais

### 1. Mistura de Jinja e Mako

Impacto:

- duplicacao de trabalho visual
- risco de estilos nao convergirem

Resposta:

- criar shell e componentes compartilhados
- migrar Mako de forma gradual quando fizer sentido

### 2. CSS legado espalhado

Impacto:

- conflitos de especificidade
- comportamento imprevisivel por tela

Resposta:

- mapear folhas antigas
- neutralizar aos poucos
- manter camadas bem definidas

### 3. Bootstrap coexistente

Impacto:

- componentes meio Bootstrap, meio Tailwind
- identidade inconsistente

Resposta:

- definir convivência temporaria
- substituir familias inteiras, nao pedaços aleatorios

### 4. Scripts inline antigos

Impacto:

- modais, validacoes e tabelas difíceis de padronizar

Resposta:

- extrair scripts criticos por familia de pagina
- padronizar os comportamentos mais repetidos

### 5. Densidade funcional alta

Impacto:

- risco de redesenhar bonito e piorar produtividade

Resposta:

- validar cada tela pelo uso operacional, nao so pela aparencia

### 6. Falta de governanca futura

Impacto:

- em poucos meses o visual degrada novamente

Resposta:

- checklist de design review
- biblioteca viva de componentes
- regra de ouro: tela nova nasce no design system

---

## Critérios de sucesso

O plano sera bem sucedido se o GALINT atingir estes pontos:

- identidade visual unica e reconhecivel
- modulos principais com linguagem consistente
- tabelas, formularios e modais claramente superiores aos atuais
- menor atrito visual nas operacoes de alto uso
- erro, loading, vazio e sucesso padronizados
- rollout incremental sem travar a operacao

---

## Ordem executiva recomendada

1. fundacao tecnica e pipeline
2. design system e tokens
3. shell global
4. dashboard
5. itens cadastrados
6. cadastro de item
7. lancamentos
8. documentos fiscais
9. backup + conversion engine + updates
10. familias restantes
11. acabamento, performance e governanca

---

## Fechamento

O GALINT nao precisa virar outro produto para parecer moderno. Ele precisa organizar a propria forca.

O caminho correto e modernizar sem diluir identidade:

- continuar tecnico
- continuar operacional
- continuar denso onde for necessario
- melhorar linguagem visual, legibilidade, consistencia e experiencia de uso

Esse plano assume exatamente isso: evolucao moderna, mas com a personalidade real do GALINT preservada.