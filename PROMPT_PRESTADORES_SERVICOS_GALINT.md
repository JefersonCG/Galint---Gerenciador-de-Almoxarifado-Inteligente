# PROMPT - Modulo de Empresas Prestadoras de Servicos (GALINT)

Documento de referencia para futuras reavaliacoes do modulo de Empresas Prestadoras de Servicos no GALINT.

Criado em: 18 de maio de 2026  
Contexto: evolucao condominial do GALINT com foco em valor operacional para o Sublime Max.

## Objetivo

Implementar um modulo completo de empresas prestadoras de servicos no GALINT, mantendo consistencia visual com o sistema atual e preparando integracoes futuras com Portaria Digital, Dossie Vivo da Unidade, chamados/manutencao, almoxarifado e auditoria condominial.

## Regras Obrigatorias

- Seguir o estilo visual atual do GALINT: Bootstrap escuro/moderno, cards, abas, botoes, tipografia e espacamento consistentes.
- Formulario deve ser limpo, compacto e nada cansativo.
- Reaproveitar a estrutura de abas ja usada no cadastro de Proprietarios/Locatarios quando fizer sentido.
- Manter coerencia com o modulo condominial existente.
- Nao quebrar almoxarifado, custodia, ferramentas, NF, saidas, devolucoes ou financeiro.
- Antes de implementar novas etapas, reavaliar viabilidade, risco, dependencias e criterios de pronto.
- Tratar dados pessoais de prestadores com cuidado LGPD: minimizacao, consentimento, mascaramento e auditoria.

## Escopo Desejado

### 1. Tela Principal

Funcionalidades esperadas:

- Busca avancada por nome da empresa, CNPJ, tipo de servico, responsavel e status.
- Listagem em tabela ou cards com:
  - Nome da empresa.
  - Tipo(s) de servico.
  - Quantidade de funcionarios cadastrados.
  - Status do contrato: ativo, vencendo, vencido ou inativo.
  - Ultimo acesso na portaria.
  - Acoes: editar, ver detalhes e desativar.

### 2. Cadastro e Edicao da Empresa

Formulario com abas.

#### Aba 1: Dados da Empresa

- Razao social e nome fantasia.
- CNPJ com mascara e validacao.
- Inscricao estadual e municipal.
- Telefone principal e WhatsApp.
- E-mail.
- Endereco completo com busca de CEP.
- Responsavel legal: nome e CPF.
- Data de inicio do contrato.
- Data de vencimento do contrato.
- Tipos de servicos prestados em multi-select ou tags: limpeza, eletrica, hidraulica, pintura, dedetizacao, seguranca, jardinagem, piscina, elevador, TI, obras, outros.
- Valor mensal do contrato, opcional.
- Observacoes.
- Anexos: contrato, ART, seguro de responsabilidade, certificados e documentos operacionais.

#### Aba 2: Funcionarios / Prestadores Vinculados

- Lista de funcionarios da empresa.
- Botao destacado: Adicionar Prestador.
- Campos por prestador:
  - Nome completo.
  - CPF unico.
  - RG.
  - Funcao ou especialidade.
  - Foto: upload e futura opcao de webcam.
  - Telefone.
  - Placa do veiculo, se houver.
  - Dias da semana de trabalho recorrente.
  - Horario habitual.
  - Status: ativo ou bloqueado.
  - Observacoes.

#### Aba 3: Historico e Auditoria

- Historico de acessos na portaria.
- Ocorrencias registradas.
- Servicos realizados no condominio.
- Alteracoes de cadastro, bloqueios, desbloqueios e anexos.

## Integracoes Necessarias

- Portaria Digital: busca rapida por empresa, CPF, nome do prestador e placa.
- Dossie Vivo da Unidade: autorizacao de prestador para unidade especifica, com periodo e finalidade.
- Agenda condominial: vincular visita ou manutencao programada a empresa/prestador.
- Notificacoes: alertar quando contrato, seguro, ART ou documento importante estiver perto do vencimento.
- Almoxarifado/ferramentas: preparar integracao futura para retirada de ferramentas por prestador autorizado.
- Chamados/manutencao: permitir que uma ordem de servico seja atribuida a empresa ou funcionario.

## Instrucoes Tecnicas

- Usar o Blueprint `condominium` quando o modulo estiver dentro do dominio condominial.
- Avaliar Blueprint proprio `prestadores` somente se o modulo crescer para dominio independente.
- Criar models apropriados quando a etapa for aprovada:
  - `ServiceCompany`.
  - `ServiceProviderEmployee`.
  - Tabelas auxiliares para anexos, tipos de servico e autorizacoes, se necessario.
- Criar service layer em `services/condominium/prestadores_service.py` ou equivalente.
- Templates devem seguir o padrao atual, especialmente o layout de abas de `condominium_owners.html`.
- Incluir audit log em acoes importantes.
- Garantir LGPD para prestadores: consentimento, finalidade, mascaramento de documento e trilha de acesso/edicao.

## Etapas Recomendadas

### Etapa 0 - Reavaliacao de Viabilidade

Antes de codificar, verificar:

- O que ja existe em `pages.py`, models condominiais e templates.
- Se o Blueprint `condominium` ja foi criado.
- Como esta a navegacao enterprise para o item Prestadores.
- Se existe audit log reutilizavel.
- Se ha portaria digital implantada ou ainda planejada.
- Se ha necessidade imediata de dados reais do Sublime Max.

Resultado esperado: especificacao validada e escopo reduzido para MVP.

### Etapa 1 - Especificacao + Models

Entregar primeiro, sem tela ainda:

- Regras de negocio.
- Models SQLAlchemy sugeridos.
- Relacionamentos.
- Campos obrigatorios/opcionais.
- Indices e unicidade.
- Eventos auditaveis.
- Riscos LGPD.

### Etapa 2 - Estrutura de Service Layer

Criar services com regras centralizadas:

- Cadastro/edicao de empresa.
- Cadastro/edicao de funcionario.
- Status de contrato.
- Status de prestador.
- Validacao de CNPJ/CPF.
- Consulta para lista e busca.
- Gatilhos de auditoria.

### Etapa 3 - Tela Principal MVP

Implementar listagem inicial:

- Busca simples.
- Cards ou tabela responsiva.
- Status do contrato.
- Contador de funcionarios.
- Acoes basicas.

### Etapa 4 - Formulario com Abas

Implementar cadastro/edicao:

- Aba Dados da Empresa.
- Aba Funcionarios vinculados.
- Aba Historico/Auditoria em modo inicial.
- Validacoes basicas.

### Etapa 5 - Integracoes Operacionais

Depois do cadastro estar solido:

- Portaria Digital.
- Dossie da Unidade.
- Agenda.
- Chamados/manutencao.
- Notificacoes de vencimento.

### Etapa 6 - Integracao com Almoxarifado

Somente depois do fluxo de autorizacao estar maduro:

- Retirada de ferramentas por prestador autorizado.
- Responsavel interno pela liberacao.
- Registro de devolucao.
- Bloqueio por pendencia, contrato vencido ou prestador inativo.

## Criterios de Pronto

Uma entrega deste modulo so deve ser considerada pronta quando:

- Nao quebra fluxos existentes do GALINT.
- Mantem as URLs e navegacao esperadas.
- Tem permissao minima por perfil.
- Tem validacao manual documentada.
- Tem `py_compile` sem erro nos arquivos Python tocados.
- Tem `get_errors` sem erro nos arquivos alterados.
- Tem `git diff --check` limpo.
- Mantem o padrao visual atual.
- Dados sensiveis aparecem mascarados onde aplicavel.
- Acoes importantes ficam preparadas para auditoria.

## Formato de Resposta Desejado para LLM

Quando este prompt for usado, responder primeiro com:

1. Especificacao clara de regras de negocio.
2. Models SQLAlchemy sugeridos.
3. Estrutura de pastas/arquivos recomendada.
4. Riscos e dependencias.
5. Estimativa por etapa.
6. Pergunta de confirmacao antes de implementar.

Nao implementar codigo automaticamente quando o pedido for apenas analise, revisao, planejamento ou viabilidade.

## Prompt Original de Referencia

```markdown
# PROMPT - Modulo de Empresas Prestadoras de Servicos (GALINT)

Quero implementar o modulo de Empresas Prestadoras de Servicos no GALINT, mantendo total consistencia com o padrao visual e de usabilidade atual do sistema.

Funcionalidades desejadas:

- Tela principal com busca avancada, cards/tabela e acoes.
- Cadastro/edicao da empresa com abas.
- Funcionarios/prestadores vinculados.
- Historico e auditoria.
- Integracao futura com Portaria Digital, Dossie da Unidade, notificacoes e Almoxarifado.

Comece entregando Especificacao completa + Models primeiro, para validacao antes de continuar.
```