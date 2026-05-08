# ConversionEngine

## Visão geral

O ConversionEngine é o módulo operacional do GALINT para triagem, leitura e preparação de bases externas antes de uma migração. Ele foi construído para funcionar dentro do visual dark do sistema, mas com execução isolada em job assíncrono para não travar a interface durante a análise.

Nesta evolução do módulo, o mecanismo aceita **dump SQL em texto plano (.sql)**, **pacotes `.zip` contendo `.sql` ou SQLite** e **bases SQLite (`.sqlite`/`.db`)** para análise estrutural. A decisão continua conservadora: o deploy direto permanece limitado a artefatos PostgreSQL compatíveis, enquanto ZIP e SQLite entram em um fluxo de staging e diagnóstico para evitar restaurações inseguras.

---

## Fluxo completo do mecanismo

1. O administrador abre a página ConversionEngine em Configurações.
2. Envia um arquivo `.sql` de origem.
3. O motor salva o arquivo em uma área isolada dentro de `instance/conversionengine/sources`.
4. O job cria um staging exclusivo em `instance/conversionengine/staging/<job>`.
5. Se a origem for ZIP, o mecanismo extrai o conteúdo com validação segura de caminhos e escolhe o artefato mais apropriado para análise.
6. Se a origem for SQLite, o motor lê o catálogo da base diretamente e conta linhas por tabela sem alterar o arquivo original.
7. Um job em background é criado com telemetria própria.
8. O job varre o dump linha a linha, ou introspecta a base SQLite, e identifica:
   - tabelas declaradas por `CREATE TABLE`
   - blocos de carga `COPY ... FROM stdin`
   - instruções `INSERT INTO`
   - colunas efetivamente presentes em cada tabela
   - volume estimado de linhas por tabela
9. O schema encontrado é comparado com o schema-alvo do GALINT, obtido diretamente do metadata SQLAlchemy da aplicação.
10. O motor calcula um score de compatibilidade e classifica risco, tempo estimado, cobertura de tabelas e aderência de colunas.
11. Ao fim, ele gera:
   - `manifest.json` com todo o diagnóstico
   - `README_implantacao.txt` com instruções operacionais
   - pacote `.zip` com origem + relatório + artefatos
   - base `.sql` pronta para restore, **somente quando a implantação direta é considerada segura**
   - rastros do staging usado na análise para homologação e auditoria

---

## O que significa “seguro para implantação direta”

O botão de implantar a nova base só é liberado quando o dump entregue já está estruturalmente compatível com o GALINT.

Na prática, o módulo exige simultaneamente:

1. Score final mínimo de compatibilidade.
2. Presença das tabelas críticas do GALINT no dump.
3. Correspondência exata dessas tabelas, sem depender de alias ou inferência de nome.
4. Origem detectada como PostgreSQL compatível com o pipeline de restore do sistema.
5. Existência de estrutura suficiente para que o restore seja feito usando o mesmo pipeline de restauração já utilizado nos backups do sistema.

Se essas condições não forem atendidas, o módulo **não tenta adivinhar uma conversão universal**. Em vez disso, ele entrega um pacote técnico com os bloqueios, o staging utilizado e as tarefas necessárias. Isso evita uma falsa sensação de segurança e reduz o risco de implantar uma base inconsistente.

---

## Como os KPIs são calculados

### Score de compatibilidade

O score final é uma composição ponderada entre:

1. Cobertura de tabelas mapeadas.
2. Aderência entre colunas do dump e colunas do schema GALINT.
3. Exatidão de nomenclatura das tabelas.
4. Penalidade por ausência de tabelas críticas.

O objetivo do número não é ser “bonito”. Ele deve refletir o quanto o dump pode ser tratado como base utilizável dentro do pipeline atual do GALINT.

### Risco operacional

O risco é derivado do score final e dos bloqueios críticos detectados. Mesmo um score relativamente bom pode continuar com risco elevado se faltar uma tabela central do processo, como usuários, itens, entradas ou saídas.

### Tempo estimado

O tempo estimado usa uma composição simples baseada em:

1. Tamanho do arquivo em MB.
2. Quantidade de linhas detectadas.
3. Quantidade de tabelas identificadas.

É uma previsão operacional para orientar o administrador e não um SLA rígido.

### KPIs de desempenho em tempo real

Durante a leitura do dump ou da base em staging, a tela mostra métricas atualizadas como:

1. Tabelas detectadas.
2. Linhas contabilizadas.
3. Percentual de varredura do arquivo.
4. Vazão aproximada em MB/s.
5. Tempo transcorrido.

Esses indicadores servem para acompanhar o comportamento do motor enquanto a análise ainda está acontecendo.

---

## Saídas geradas

### 1. Janela de download da nova base

Quando a base é considerada apta, o botão “Baixar nova base convertida” entrega um arquivo `.sql`. No Windows, o navegador abre o diálogo padrão de salvar arquivo, que é o comportamento esperado para o download operacional da nova base.

### 2. Implantação imediata da nova base

Quando a base é apta para deploy, o botão “Implantar nova base agora” envia o artefato convertido para o mesmo fluxo de restauração já adotado pelo módulo de backup do GALINT. Isso mantém o comportamento operacional consistente com o restante do sistema.

### 3. Pacote técnico

Mesmo quando a implantação direta não é liberada, o pacote técnico continua disponível. Ele é o artefato para auditoria, homologação e ajuste manual do dump externo, e pode incluir o arquivo analisado dentro do staging quando a origem foi ZIP.

---

## Limitações intencionais desta versão

1. Não existe conversão universal entre esquemas arbitrários.
2. Não há reescrita automática de nomes de tabelas ou transformação profunda de colunas incompatíveis.
3. O modo de deploy direto depende de artefatos PostgreSQL já muito próximos do schema GALINT.
4. SQLite e ZIP entram em análise e staging, mas não são restaurados diretamente no GALINT nesta fase.
5. Jobs são mantidos em memória do processo; reiniciar o servidor limpa o estado de acompanhamento.

Essas limitações existem para privilegiar segurança operacional. A próxima evolução natural é adicionar adaptadores de origem, staging e reescrita controlada por mapa de transformação.

---

## Caminho evolutivo recomendado

Se a meta for transformar o ConversionEngine em uma plataforma completa de migração, os próximos incrementos mais naturais são:

1. Adaptadores por origem: PostgreSQL, MySQL, SQLite, CSV/ZIP e ERP legado.
2. Staging database temporário para validar dados antes do deploy.
3. Regras declarativas de mapeamento de tabela e coluna.
4. Normalização automática de tipos e chaves.
5. Exportador controlado de SQLite/MySQL para SQL PostgreSQL compatível.
6. Checklist de homologação pós-implantação.
7. Histórico persistente de jobs e auditoria de conversões.

---

## Resumo operacional

O ConversionEngine não foi desenhado para “forçar” qualquer base a entrar no GALINT. Ele foi desenhado para dizer, com clareza técnica e visual operacional, **o quanto a base é compatível, quanto isso deve demorar, quais riscos existem, o que pode ser implantado imediatamente e o que ainda depende de intervenção humana**.