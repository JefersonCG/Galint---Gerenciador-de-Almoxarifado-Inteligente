# README - Plano de Evolução do GALINT

## Objetivo

Este documento descreve como eu conduziria a evolução do GALINT sem reescrever o sistema, preservando a operação atual, reduzindo risco de regressão e criando base para crescer em quatro frentes:

- confiabilidade operacional
- padronização de UI/UX
- arquivamento e exclusão segura de dados sensíveis
- backup/restauração como réplica real do ambiente

O foco aqui não é um texto conceitual. O foco é um plano executável, em ordem, com passos, dependências, riscos e validações.

---

## Visão executiva

Eu não faria essa evolução como um bloco único. Eu dividiria em trilhas paralelas, mas com uma ordem rígida de precedência:

1. estabilizar o núcleo operacional
2. fechar os pontos de backup e restauração
3. criar um design system mínimo para padronizar a interface
4. convergir telas por família funcional
5. implementar arquivamento controlado para exclusao de usuarios e dados historicos
6. preparar distribuição, atualização e rollback como disciplina própria

O motivo da ordem é simples:

- não adianta melhorar tela em cima de fluxo instável
- não adianta apagar ou migrar dados sem restauração confiável
- não adianta expandir produto sem padrão visual e técnico mínimo

---

## Principios obrigatorios

Antes de mexer, eu fixaria estas regras:

1. nenhuma etapa entra em producao sem rollback definido
2. toda mudanca estrutural precisa de validacao em base copia
3. toda tela alterada precisa manter compatibilidade com permissao, mobile e Telegram quando houver integracao
4. regra de negocio deve sair de view/template e ir para service sempre que possivel
5. documentacao precisa ser atualizada junto com a entrega, nao depois
6. migracoes devem ser idempotentes quando o historico do banco indicar legado heterogeneo

---

## Premissas reais do workspace

Este plano considera fatos ja observados no projeto:

- o backend principal e Flask com PostgreSQL
- existe legado ativo no schema e em partes da camada de estoque
- ha telas novas visualmente mais maduras e telas antigas ainda em Bootstrap operacional
- o backup atual e centrado em pg_dump e nao empacota automaticamente todos os artefatos de disco
- parte do produto depende de arquivos fora do banco, como fotos, logos, barcodes, PDFs e arquivos em instance
- o projeto tem integracoes relevantes com Telegram, mobile, relatorios e servicos de background

---

## Ordem de execucao recomendada

## Etapa 0 - Diagnostico congelado e baseline

### Objetivo

Criar uma linha de base tecnica para comparar antes e depois.

### Passo a passo

1. Mapear os modulos criticos do sistema:
   - dashboard
   - estoque
   - entradas por NF/cupom
   - fornecedores
   - usuarios
   - Telegram
   - mobile
   - backup e restore
2. Registrar os fluxos criticos por modulo:
   - criar item
   - editar item
   - registrar entrada
   - registrar saida
   - registrar devolucao
   - gerar relatorio
   - executar backup
   - restaurar backup
3. Tirar snapshots funcionais:
   - screenshots das telas centrais
   - exportacoes PDF/XLSX de referencia
   - exemplo de backup gerado
4. Registrar metricas iniciais:
   - tempo de carregamento do dashboard
   - tempo da listagem de itens
   - tempo de geracao de relatorios
   - tamanho do backup atual
5. Consolidar a matriz de risco por modulo.

### Possiveis problemas

- o time pular essa etapa e depois discutir regressao sem baseline
- metricas ficarem subjetivas porque nao foram medidas no mesmo ambiente
- telas diferentes terem comportamento diferente por permissao e nao por bug

### Criterio de saida

Existe um pacote minimo de referencia para comparar performance, layout e comportamento.

---

## Etapa 1 - Estabilização do núcleo operacional

### Objetivo

Reduzir a chance de quebrar operacao enquanto o sistema evolui.

### Passo a passo

1. Revisar os services que concentram comportamento de estoque e saldo.
2. Identificar regras duplicadas entre views, services e integracoes externas.
3. Padronizar pontos de entrada da regra de negocio:
   - web
   - mobile
   - Telegram
4. Garantir que consultas de dashboard nao repliquem logica pesada de saldo em varios lugares.
5. Separar claramente:
   - leitura agregada para dashboard
   - escrita operacional transacional
   - exportacao e relatorio
6. Revisar os pontos onde o schema legado ainda exige compatibilidade especial.
7. Criar testes de fumaça para os fluxos mais sensiveis.

### Possiveis problemas

- regra duplicada em endpoints diferentes gerar saldos divergentes
- schema legado com nomes diferentes, como codigo_item versus product_id, causar erro silencioso ou cleanup incompleto
- performance piorar se a centralizacao for feita sem cuidado com consultas agregadas
- alguma view depender implicitamente de comportamento acoplado ao template

### Mitigacao

1. tratar compatibilidade de schema explicitamente
2. validar leitura e escrita separadamente
3. medir antes e depois das consultas mais pesadas
4. usar feature flags quando a troca de comportamento for sensivel

### Criterio de saida

Os fluxos centrais operam com a mesma regra, com menos dispersao de logica e sem piora perceptivel de performance.

---

## Etapa 2 - Backup como replica real

### Objetivo

Fazer o backup deixar de ser apenas dump de banco e passar a ser um pacote de restauracao realista do ambiente.

### Passo a passo

1. Inventariar tudo que precisa entrar em um backup completo:
   - dump SQL
   - fotos de itens
   - logo da empresa
   - barcodes gerados
   - PDFs e arquivos de relatorio persistidos
   - arquivos relevantes em instance
   - configuracoes criticas necessarias para subir o sistema
2. Definir o formato do pacote:
   - arquivo zip versionado
   - manifest.json com versao, timestamp, origem e checksums
3. Separar claramente dois modos de backup:
   - backup rapido de banco
   - backup completo de replica
4. Implementar geracao do manifest.
5. Implementar coleta de arquivos com validacao de existencia.
6. Implementar compactacao do pacote final.
7. Adaptar a tela de backup para mostrar o tipo do backup.
8. Adaptar restore para distinguir:
   - restauracao somente de banco
   - restauracao completa
9. Adicionar verificacao de integridade antes da restauracao.
10. Testar restauracao em maquina limpa ou ambiente isolado.

### Possiveis problemas

- caminho de arquivo salvo no banco apontar para arquivo inexistente
- restauracao trazer banco sem os anexos corretos
- pacotes ficarem muito grandes para operacao normal
- restore sobrescrever arquivos locais importantes sem confirmacao
- versoes antigas de pacote nao serem compativeis com o restore novo

### Mitigacao

1. classificar arquivos em obrigatorios e opcionais
2. gerar relatorio de arquivos faltantes no backup
3. manter restore em staging antes do deploy efetivo
4. versionar o schema do manifest
5. permitir validacao sem restaurar

### Criterio de saida

Um pacote completo consegue reconstruir o sistema com banco e artefatos essenciais em ambiente separado.

---

## Etapa 3 - Design system minimo e padrao de interface

### Objetivo

Parar de redesenhar tela por tela sem padrao e criar uma base visual reutilizavel.

### Passo a passo

1. Definir tokens visuais globais:
   - cores base
   - superficies
   - bordas
   - sombras
   - espacamentos
   - tipografia
   - estados de foco, hover e erro
2. Consolidar esses tokens em um ponto central de CSS.
3. Padronizar componentes-base:
   - page header
   - card principal
   - KPI card
   - tabela operacional
   - formulario compacto
   - filtros
   - botoes primario, secundario e destrutivo
   - modais
   - badges e pills
4. Definir duas densidades oficiais:
   - operacional compacta
   - gerencial confortavel
5. Criar um guia simples dizendo quando usar cada componente.
6. Remover gradualmente estilos inline ou variantes soltas que nao obedecem ao padrao.

### Possiveis problemas

- cada pagina ter pequenas excecoes e virar argumento para nao padronizar nada
- tela antiga quebrar porque dependia de margem, padding ou classe Bootstrap especifica
- excesso de CSS acumulado aumentar conflito de prioridade e especificidade

### Mitigacao

1. padronizar primeiro o que mais se repete
2. evitar reescrever tudo de uma vez
3. substituir inline style por classes nomeadas e auditaveis
4. manter compatibilidade com o shell atual enquanto a convergencia acontece

### Criterio de saida

Existe um pequeno sistema visual reutilizavel capaz de sustentar a convergencia das telas sem improviso visual.

---

## Etapa 4 - Convergencia de telas por familia

### Objetivo

Padronizar a experiencia sem paralisar a operacao.

### Ordem que eu seguiria

1. dashboard e home operacional
2. estoque e cadastro de itens
3. entradas por NF/cupom e historico relacionado
4. fornecedores e financeiro associado
5. relatorios
6. usuarios, permissoes e configuracoes
7. paineis auxiliares como mobile panel e fluxos especiais

### Metodo por familia

Para cada familia, eu repetiria exatamente este ciclo:

1. mapear telas da familia
2. identificar componentes repetidos
3. alinhar layout ao design system minimo
4. reduzir variacoes desnecessarias de espacamento e cores
5. validar estados vazios, loading, erro e sucesso
6. validar responsividade minima
7. validar permissao por perfil
8. validar exportacao ou efeitos colaterais do modulo

### Possiveis problemas

- uma tela isolada misturar legado Mako com Jinja e dificultar convergencia
- formularios grandes demais tentarem virar redesign total em vez de refinamento incremental
- modulos auxiliares ficarem esquecidos e depois parecerem outro produto

### Mitigacao

1. trabalhar por familia, nao por arquivo aleatorio
2. fechar uma familia antes de abrir tres novas
3. documentar excecoes verdadeiras em vez de improvisar excecoes visuais

### Criterio de saida

Cada familia passa a ter linguagem visual e interacional consistente com o shell e com os componentes-base.

---

## Etapa 5 - Arquivamento e exclusao segura de usuarios

### Objetivo

Permitir retirada do usuario da operacao ativa sem destruir historico, auditoria e rastreabilidade.

### Como eu faria

Eu nao trataria isso como exclusao simples. Eu criaria um fluxo de descomissionamento.

### Passo a passo

1. Criar um servico de analise de impacto do usuario.
2. Levantar tudo que referencia a matricula ou o usuario:
   - saidas
   - entradas
   - custodia de ferramentas
   - reparos
   - Telegram
   - dispositivos e sessoes
   - logs e auditoria
3. Classificar vinculos em tres grupos:
   - bloqueantes
   - arquivaveis
   - descartaveis operacionais
4. Gerar um dossie do usuario antes de qualquer acao:
   - PDF executivo
   - JSON ou SQLite tecnico
5. Salvar esse pacote em repositorio de arquivo historico.
6. Bloquear a exclusao se houver pendencias operacionais abertas.
7. Oferecer tres acoes controladas:
   - desativar
   - arquivar e remover da operacao ativa
   - excluir somente o que for realmente seguro excluir
8. Liberar a matricula apenas quando o modelo de negocio permitir formalmente.

### Possiveis problemas

- dependencias nao mapeadas quebrarem na hora de excluir
- ORM tentar cascata em tabelas com legado inconsistente
- liberar matricula cedo demais causar colisoes historicas ou ambiguidades em auditoria
- PDF sozinho nao ser suficiente para restauracao ou consulta futura

### Mitigação

1. tratar o processo como arquivamento, não como delete bruto
2. manter identificador histórico imutável no dossiê arquivado
3. usar SQL controlado quando o ORM não refletir o schema real com segurança
4. exigir confirmação de leitura do impacto antes da ação final

### Critério de saída

O sistema consegue retirar um usuário da operação diária sem perder rastreabilidade nem corromper relacionamentos.

---

## Etapa 6 - Atualização, distribuição e rollback

### Objetivo

Fazer deploy e atualização virarem processo previsível.

### Passo a passo

1. Separar claramente artefatos de aplicacao e dados persistidos.
2. Revisar a estrategia de executavel e updater.
3. Garantir que update não substitua apenas um arquivo quando o build real é onedir.
4. Padronizar o pacote de release:
   - binarios
   - migracoes necessarias
   - manifest de versao
   - instrucoes de rollback
5. Criar checklist de pre-deploy.
6. Criar checklist de pos-deploy.
7. Testar rollback de uma versao completa.

### Possiveis problemas

- updater parcial deixar instalacao quebrada
- migracao de banco passar e interface nao ser compativel com a versao anterior
- ambiente do cliente ter diferencas de permissao, caminho ou antivirus que afetem update

### Mitigacao

1. tratar release como pacote completo
2. versionar banco e aplicacao de forma visivel
3. nunca publicar sem rollback praticado

### Criterio de saida

Existe um processo de release que pode ser repetido sem depender de improviso manual.

---

## Etapa 7 - Observabilidade e disciplina de manutencao

### Objetivo

Evitar que o sistema volte a acumular comportamento opaco.

### Passo a passo

1. Padronizar logs funcionais por modulo.
2. Identificar eventos que precisam de trilha de auditoria.
3. Padronizar mensagens operacionais de erro para usuario e logs tecnicos para suporte.
4. Criar rotinas periodicas de verificacao:
   - integridade de backups
   - jobs travados
   - filas pendentes
   - arquivos orfaos
5. Criar um pequeno painel tecnico ou checklist operacional para suporte.

### Possiveis problemas

- log demais esconder o que importa
- log de menos impedir diagnostico de incidente
- jobs antigos e servicos paralelos acumularem sem visibilidade

### Mitigacao

1. definir eventos realmente importantes
2. padronizar contexto minimo por log
3. revisar periodicamente ruido versus utilidade

### Criterio de saida

O sistema fica mais previsivel de operar, manter e diagnosticar.

---

## Ordem pratica de entregas

Se eu fosse executar isso no projeto, eu faria nesta sequencia de entregas curtas:

1. baseline tecnica e matriz de risco
2. consolidação do núcleo operacional mais sensível
3. backup completo com manifest e validacao sem restore
4. restore completo em staging
5. design system minimo documentado
6. convergencia visual do dashboard e estoque
7. convergencia visual de NF, fornecedores e relatorios
8. convergencia visual de usuarios e configuracoes
9. fluxo de arquivamento de usuarios
10. trilha de release, update e rollback

Essa ordem tem uma razao: primeiro eu garanto que o sistema aguenta crescer, depois eu melhoro a forma como ele aparece e, por fim, eu mexo nos processos mais sensiveis de ciclo de vida de dado e distribuicao.

---

## Riscos transversais que eu esperaria encontrar

1. legado de schema diferente do modelo ORM atual
2. dependencias ocultas entre modulos via importacao indireta
3. telas que parecem simples, mas carregam regra de negocio no template ou no JavaScript embutido
4. comportamento diferente por perfil de acesso
5. arquivos em disco sem governanca clara de localizacao e ciclo de vida
6. inconsistencias historicas que so aparecem quando a regra fica mais rigorosa
7. update parcial de executavel em arquitetura que exige pacote completo

---

## O que eu nao faria

1. nao reescreveria o sistema inteiro
2. nao tentaria padronizar todas as telas em um unico commit gigante
3. nao liberaria exclusao de usuario como atalho bruto
4. nao chamaria de backup completo algo que salva so banco
5. nao misturaria redesign visual com alteracao estrutural pesada no mesmo pacote sem isolamento

---

## Definicao de sucesso

Eu consideraria essa evolucao bem sucedida quando o GALINT atingir estes pontos:

1. operacao central estavel e previsivel
2. backup restauravel como replica funcional
3. interface coerente entre modulos principais
4. fluxo seguro para arquivamento de usuarios e historicos
5. release com update e rollback confiaveis
6. documentacao suficiente para nao depender de memoria informal

---

## Primeira sprint que eu abriria

Se fosse para comecar agora, eu abriria uma sprint curta com escopo fechado:

1. consolidar baseline tecnica
2. fechar inventario de artefatos do backup completo
3. definir manifest do backup
4. documentar tokens visuais globais
5. escolher a primeira familia de telas para convergencia total

Essa sprint nao entrega tudo, mas coloca o projeto em direcao correta com risco baixo e ganho estrutural real.
