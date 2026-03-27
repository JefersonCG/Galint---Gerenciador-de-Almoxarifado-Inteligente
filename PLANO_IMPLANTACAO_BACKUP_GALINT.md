# PLANO DE IMPLANTACAO DO BACKUP GALINT

## Objetivo

Este documento define como implantar uma estrategia de backup solida no GALINT, coerente com o ambiente atual do projeto e com a operacao real do sistema em Windows, Flask e PostgreSQL.

Como o GALINT ja possui geracao de backup por pg_dump e restauracao oficial via ConversionEngine, a abordagem proposta aqui nao parte do zero. Ela parte do estado atual e evolui para um modelo confiavel de:

- backup de banco com execucao previsivel
- restauracao controlada em pipeline oficial
- validacao em staging antes de qualquer acao destrutiva
- extensao futura para backup completo de replica
- rollback operacional documentado

Neste plano, eu trato “implantacao do backup” como um conjunto unico de backup, validacao, restore e governanca operacional. So gerar arquivo nao basta.

---

## Resumo da abordagem

Minha abordagem seria em 5 blocos:

1. estabilizar o backup atual de banco e seus pre-requisitos
2. endurecer a restauracao controlada e o staging
3. implantar verificacao de integridade e testes reais de restauracao
4. expandir para backup completo de replica do GALINT
5. operacionalizar retenção, monitoramento e rollback

Eu nao implantaria tudo de uma vez em producao. Eu faria em camadas, com prova de restauracao entre uma camada e outra.

---

## Estado atual do GALINT

Hoje o ambiente ja possui uma base importante:

1. servico de backup em Flask para PostgreSQL
2. uso de pg_dump para gerar backup em formato .sql
3. uso de psql para restauracao
4. heuristicas para localizar ferramentas PostgreSQL no Windows
5. pasta local de backups em instance/backups
6. restauracao oficial centralizada no ConversionEngine
7. staging isolado por job dentro de instance/conversionengine/staging
8. interface web para gerar backup e acionar o restaurador oficial

Isso e bom porque a implantacao nao precisa inventar outra esteira. Ela precisa endurecer a esteira existente.

---

## Escopo da implantacao

## Fase 1 - obrigatoria

Implantar com seguranca o backup e restore de banco PostgreSQL.

Inclui:

- configuracao de pg_dump e psql
- validacao de acesso ao banco
- geracao de backup
- retenção de artefatos
- teste de restore em ambiente isolado
- roteiro de rollback do banco

## Fase 2 - recomendada

Evoluir para backup completo de replica do GALINT.

Inclui:

- dump SQL
- fotos e anexos relevantes
- arquivos em instance
- arquivos gerados operacionalmente
- manifest de integridade
- validacao do pacote completo

---

## Arquitetura-alvo de implantacao

Eu estruturaria a implantacao assim:

1. camada de geracao:
   - cria backup SQL confiavel
   - registra metadados do artefato
2. camada de validacao:
   - verifica existencia, tamanho, formato e consistencia minima
   - identifica se o artefato pode seguir para restore ou staging
3. camada de staging:
   - executa analise e preparacao isolada
   - nunca restaura direto sem passar por criterios minimos
4. camada de restauracao:
   - restore controlado via pipeline oficial
   - com progresso, logs e bloqueios operacionais
5. camada de governanca:
   - retenção
   - auditoria
   - validacao periodica
   - rollback praticado

---

## Pontos criticos da implantacao

Estes sao os pontos que eu considero mais sensiveis no ambiente GALINT.

### 1. Localizacao de pg_dump e psql no Windows

O GALINT depende de ferramentas externas do PostgreSQL. Em Windows, isso costuma falhar por:

- PATH incompleto
- multiplas versoes de PostgreSQL instaladas
- instalacao em diretorio nao padrao
- permissao diferente entre usuario logado e servico que executa a aplicacao

### Risco

O backup aparenta estar habilitado, mas falha em runtime no momento mais critico.

### Tratamento

1. validar explicitamente BACKUP_PG_DUMP e BACKUP_PSQL antes da entrada em producao
2. registrar no checklist o caminho absoluto efetivo encontrado
3. testar backup e restore no mesmo contexto de execucao da aplicacao

---

### 2. Restore com conexoes abertas no PostgreSQL

Restauração de banco em ambiente ativo pode falhar porque usuarios, jobs ou o proprio app mantem conexoes abertas.

### Risco

- restore travado
- lock prolongado
- janela de manutencao estourada
- banco parcialmente restaurado se o processo for mal conduzido

### Tratamento

1. definir janela formal de restore
2. drenar conexoes antes da restauracao
3. desligar processos concorrentes do GALINT durante restore real
4. usar staging antes de restore destrutivo

---

### 3. Confiar em backup sem prova de restore

Esse e o erro operacional mais comum.

### Risco

Gerar muitos arquivos .sql e descobrir tarde demais que o restore falha por formato, permissao, schema, encoding ou ferramenta.

### Tratamento

1. definir politica de teste periodico de restauracao
2. validar pelo menos um restore completo por ciclo operacional relevante
3. considerar backup como valido somente apos restore de prova

---

### 4. Pensar que dump SQL ja e replica completa do GALINT

No GALINT ha artefatos fora do banco.

### Risco

O banco volta, mas o sistema restaurado fica incompleto por faltar:

- fotos
- logos
- barcodes
- PDFs
- arquivos de instance
- outros anexos operacionais

### Tratamento

1. separar claramente backup de banco e backup de replica completa
2. nao vender a fase 1 como solucao definitiva de replica
3. implantar manifest e inventario de arquivos para a fase 2

---

### 5. Restore oficial depender de autenticacao pesada em momento de incidente

No GALINT, endpoints de polling e jobs ja exigiram cuidado para nao depender de estados de autenticacao que consultam banco em situacoes de restore.

### Risco

O proprio painel de acompanhamento falha quando o banco esta indisponivel ou sob troca.

### Tratamento

1. manter endpoints de status com autenticacao leve quando aplicavel
2. isolar o acompanhamento do restore do caminho normal de uso do sistema
3. prever acesso tecnico de contingencia

---

### 6. Tempo de execucao e timeout

Backups grandes ou restore pesado podem ultrapassar timeouts mal configurados.

### Risco

- cancelamento falso de operacao valida
- artefato incompleto
- restauracao abortada no meio do processo

### Tratamento

1. revisar timeouts do backup e do restore no ambiente real
2. testar com volume proximo da producao
3. diferenciar timeout de interface de timeout de processo critico

---

## Etapas de implantacao

## Etapa 0 - Preparacao tecnica

### Objetivo

Garantir que o ambiente esta apto a operar backup e restore sem improviso.

### Passos

1. confirmar o banco PostgreSQL ativo do GALINT e a URI usada pela aplicacao
2. validar credenciais com privilegios suficientes para pg_dump e restore
3. localizar pg_dump e psql efetivos no servidor
4. registrar os caminhos configurados no ambiente
5. confirmar pasta instance/backups com permissao de escrita
6. confirmar pasta instance/conversionengine com permissao de escrita
7. revisar espaco em disco para backup, staging e artefatos temporarios
8. revisar timeouts configurados para subprocesso, conexao e restore

### Entregavel

Checklist de ambiente aprovado.

### Problemas possiveis

- usuario do processo sem permissao nas pastas
- pg_dump presente e psql ausente
- espaco de disco insuficiente
- URI apontando para base errada

---

## Etapa 1 - Homologacao do backup SQL

### Objetivo

Provar que a geracao do backup atual funciona de forma repetivel.

### Passos

1. gerar backup manual pelo fluxo web do GALINT
2. verificar nome, tamanho e data do artefato gerado
3. validar que o arquivo foi salvo na pasta esperada
4. inspecionar se o conteudo nao esta vazio e aparenta ser dump SQL valido
5. repetir o processo mais de uma vez para excluir sucesso acidental
6. registrar duracao da operacao

### Entregavel

Backups SQL gerados com sucesso e com evidencia operacional.

### Problemas possiveis

- falha de localizacao do pg_dump
- credenciais insuficientes
- timeout
- dump inconsistente ou corrompido

---

## Etapa 2 - Homologacao do restore em ambiente isolado

### Objetivo

Validar restore sem arriscar a base ativa.

### Passos

1. preparar ambiente de homologacao ou base copia
2. subir banco alvo separado do banco de producao
3. executar restore pelo pipeline oficial ou por fluxo tecnico controlado
4. acompanhar logs, progresso e mensagens de erro
5. validar se o schema final ficou utilizavel
6. subir a aplicacao contra a base restaurada
7. executar teste funcional minimo:
   - login
   - dashboard
   - listagem de itens
   - entrada/saida historica
   - configuracoes

### Entregavel

Prova de restauracao bem-sucedida fora da producao.

### Problemas possiveis

- erro de lock
- psql ausente
- metacomandos problematicos em dumps plain
- divergencia de schema entre dump e versao da aplicacao

---

## Etapa 3 - Endurecimento da esteira oficial

### Objetivo

Tornar o fluxo oficial resiliente para uso recorrente.

### Passos

1. garantir que o backup mostre claramente que ele e de banco, nao replica completa
2. registrar metadados por backup:
   - timestamp
   - origem
   - tamanho
   - status de validacao
3. definir criterios para artefato valido
4. reforcar a passagem obrigatoria por staging quando aplicavel
5. revisar mensagens operacionais para falhas comuns
6. separar melhor erro de ambiente, erro de credencial e erro de dump
7. definir politica de retencao local

### Entregavel

Esteira mais previsivel para suporte e operacao.

### Problemas possiveis

- mistura de mensagens tecnicas e operacionais confundir o usuario
- lixo acumulado em backups e staging
- restauracao ser iniciada sobre artefato nao validado

---

## Etapa 4 - Implantacao do backup completo de replica

### Objetivo

Evoluir do backup de banco para um pacote capaz de reconstruir o GALINT com mais fidelidade.

### Passos

1. inventariar todos os artefatos fora do banco
2. classificar arquivos em:
   - obrigatorios
   - importantes
   - opcionais
3. definir estrutura do pacote zip
4. criar manifest.json com:
   - versao do pacote
   - timestamp
   - host de origem
   - versao do GALINT
   - lista de arquivos
   - checksums
5. incluir dump SQL e diretorios de artefatos no pacote
6. implementar validacao do manifest
7. testar abertura e restauracao do pacote em staging
8. documentar limite do que o backup replica e do que nao replica

### Entregavel

Pacote de backup completo, validavel e restauravel em ambiente isolado.

### Problemas possiveis

- caminhos absolutos antigos nao baterem no ambiente novo
- anexos referenciados no banco nao existirem mais em disco
- pacote crescer demais para rotina frequente

---

## Etapa 5 - Go-live controlado

### Objetivo

Colocar a estrategia em operacao real sem improviso.

### Passos

1. aprovar checklist tecnico
2. aprovar restore de homologacao
3. comunicar janela de manutencao e procedimento de incidente
4. executar backup de seguranca pre-go-live
5. ativar monitoramento operacional minimo
6. publicar procedimento oficial para suporte e administracao
7. praticar restore de contingencia em ambiente controlado

### Entregavel

Backup implantado como processo operacional, nao apenas como funcionalidade de tela.

### Problemas possiveis

- equipe usar o fluxo sem seguir o checklist
- retention nao ser executada e lotar disco
- ninguem saber qual backup foi realmente testado

---

## Minha abordagem de implantacao

Eu faria a implantacao com postura conservadora.

### 1. Primeiro eu estabilizo o que ja existe

Nao comecaria escrevendo um grande pacote ZIP antes de provar que o backup SQL atual esta solido. O primeiro ganho real vem de garantir que:

- o backup atual funciona sempre
- o restore funciona fora de producao
- os erros comuns sao conhecidos

### 2. Depois eu provo restore, nao apenas geracao

Eu considero que backup so existe de verdade quando restaura. Por isso, minha abordagem prioriza homologacao de restore cedo.

### 3. So depois eu amplio para replica completa

Quando o fluxo banco + restore estiver confiavel, ai sim eu acrescento arquivos externos, manifest, checksums e pacote completo.

### 4. Tudo com rollback e criterio de saida

Cada etapa precisa terminar com evidencias objetivas, nao com impressao de que “parece funcionando”.

---

## Checklist de pontos criticos antes de producao

1. pg_dump encontrado no contexto real da aplicacao
2. psql encontrado no contexto real da aplicacao
3. backup SQL gerado com sucesso mais de uma vez
4. restore homologado fora da base ativa
5. espaco em disco validado
6. pasta de backup validada
7. staging validado
8. equipe sabe diferenciar backup de banco e replica completa
9. politica de retencao definida
10. rollback documentado e praticado

---

## Politica de validacao que eu adotaria

1. validar backup a cada implantacao relevante
2. validar restore completo periodicamente
3. manter pelo menos um backup recentemente testado
4. registrar qual artefato foi testado, quando e em qual ambiente
5. nunca considerar arquivo antigo como confiavel so porque existe na pasta

---

## Politica de rollback

Em qualquer implantacao que toque banco, eu faria assim:

1. gerar backup imediatamente antes da mudanca
2. registrar versao da aplicacao e versao do banco antes da execucao
3. se a implantacao falhar, interromper novas escritas
4. restaurar a copia pre-mudanca em ambiente controlado
5. validar subida da aplicacao
6. so reabrir operacao apos teste funcional minimo

Rollback sem teste funcional final e rollback incompleto.

---

## Definicao de sucesso

Eu consideraria a implantacao bem sucedida quando o GALINT atingir estes pontos:

1. backup SQL confiavel e repetivel
2. restore homologado e documentado
3. staging usado como etapa real de seguranca
4. equipe operando com checklist claro
5. trilha pronta para evolucao a backup completo de replica

---

## Proximo passo recomendado

Se eu fosse executar isso agora no projeto, eu abriria nesta ordem:

1. checklist tecnico do ambiente atual
2. homologacao de backup SQL
3. homologacao de restore em base isolada
4. endurecimento do fluxo oficial
5. desenho do pacote de replica completa

Essa ordem reduz risco e gera confianca real, sem vender maturidade que o ambiente ainda nao provou.
