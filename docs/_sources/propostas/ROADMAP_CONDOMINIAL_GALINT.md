# Roadmap Condominial GALINT

Documento de acompanhamento da evolucao condominial do GALINT para o Sublime Max.

Atualizado em: 18 de maio de 2026.

## Visao do produto

O objetivo e transformar o GALINT em uma central viva de gestao condominial. Sindico, administracao, colaboradores e moradores devem conseguir enxergar o funcionamento dos setores do condominio com clareza operacional: cadastro, portaria, mensageria, manutencao, prestadores, documentos, ocorrencias, pendencias e indicadores.

A referencia de produto e uma visao de saude do condominio: cada setor funciona como um orgao, com sinais, filas, riscos e historico visiveis para quem precisa decidir ou executar.

## Prompts e referencias preservadas

- `PROMPT_PRESTADORES_SERVICOS_GALINT.md`: prompt de referencia do modulo de empresas prestadoras de servicos.
- `docs/_sources/propostas/README_MENSAGERIA_CONDOMINIAL.md`: proposta tecnica de Mensageria Condominial.

## Fases realizadas

### Topbar global

Concluido.

- Padronizacao visual do topbar em todo o sistema.
- Ajuste aplicado antes das fases condominiais para manter consistencia visual.

### Fase 0A - Base condominial

Concluida.

- Estrutura inicial de blocos, unidades e cadastros condominiais.
- Massa demo com 2 blocos e 5 moradores ficticios.
- Dois moradores ficticios marcados como locatarios.
- Base preparada para Dossie Vivo, Agenda e Portaria.

### Fase 0B - Prestadores, auditoria e Dossie Vivo

Concluida.

- Cadastro de empresas prestadoras de servicos.
- Documentos de prestadores com vencimentos.
- Funcionarios/prestadores vinculados a empresas.
- Auditoria condominial para acoes principais.
- Dossie Vivo da Unidade com busca e contexto operacional.

### Fase 1 - Operacao diaria condominial

Concluida.

- Portaria Digital MVP.
- Registro auditavel de entrada, saida, bloqueio e liberacao com observacao.
- Busca por unidade, morador, prestador, documento e placa.
- Regras automaticas de bloqueio para prestador inativo, empresa inativa, contrato vencido e documento vencido.
- Chamados e manutencao em fluxo operacional inicial.
- Recebimentos iniciais vinculados a unidade e morador.

### Fase 1.1 - Mensageria

Concluida.

- Area renomeada para Mensageria.
- Login do modulo Mensageria direciona para a tela operacional real.
- Fluxo de recebimento com transportadora, tipo, rastreio, unidade, morador e destinatario.
- Local de armazenamento fisico, como armario, prateleira ou sala.
- Status: recebido, armazenado, notificado, retirado e devolvido.
- Datas de armazenamento, notificacao e entrega.
- Colaborador responsavel por recebimento, armazenamento, notificacao e entrega.
- Campo de entregue para quem.
- Dashboard interno com rankings:
  - transportadoras que mais entregam;
  - unidades com mais recebimentos;
  - tipos de volume;
  - status dos recebimentos.
- Seed demo com transportadoras como Correios, Mercado Livre, Shopee, Amazon, DHL, FedEx, eBay e Jadlog.

## Fases pendentes

### Fase 2 - Portal do Morador

Pendente.

Objetivo: permitir que moradores, proprietarios e locatarios consultem informacoes da propria unidade.

Escopo previsto:

- Login/identificacao do morador.
- Visualizacao de dados da unidade.
- Consulta de encomendas pendentes e historico da Mensageria.
- Acompanhamento de chamados e manutencoes.
- Comunicados e solicitacoes basicas.
- Regras de privacidade para que cada morador veja apenas o proprio contexto.

### Fase 2.1 - Dashboard Geral do Condominio

Pendente.

Objetivo: criar uma visao executiva do funcionamento de todos os setores do condominio.

Escopo previsto:

- Painel geral do sistema por setor.
- Administracao: unidades, moradores, locatarios e documentos pendentes.
- Portaria: entradas, saidas, acessos bloqueados e prestadores frequentes.
- Mensageria: volumes recebidos, pendentes, transportadoras e unidades com maior demanda.
- Manutencao: chamados abertos, criticos, concluidos e tempo medio.
- Prestadores: contratos vencendo, documentos vencidos e empresas suspensas.
- Alertas executivos para gargalos, riscos e acumulado operacional.

### Fase 3 - Financeiro condominial

Pendente.

Escopo previsto:

- Rateios por unidade.
- Cobrancas e controle interno.
- Inadimplencia.
- Prestacao de contas.
- Relacao com despesas, contratos e prestadores.

### Fase 4 - Inteligencia, automacoes e BI avancado

Pendente.

Escopo previsto:

- Alertas inteligentes por vencimento, fila parada e chamados criticos.
- Relatorios por unidade, bloco, morador, prestador e setor.
- Exportacoes para Excel/CSV e eventual Power BI externo.
- Auditoria ampliada de leitura, edicao, exportacao e liberacao.
- Indicadores preditivos e visao historica de saude operacional.

## Proxima etapa recomendada

A proxima etapa logica e iniciar a Fase 2: Portal do Morador.

A Mensageria ja esta forte o suficiente para alimentar o portal com valor real: o morador podera consultar recebimentos pendentes, historico de retirada e status operacional. Chamados e dados da unidade tambem ja possuem base para exposicao controlada.

## Criterios permanentes de validacao

Antes de considerar cada fase pronta:

- Executar migrations necessarias.
- Rodar seed demo quando aplicavel.
- Validar renderizacao das telas afetadas.
- Executar smoke transacional com rollback para fluxos criticos.
- Rodar `py_compile` nos Python alterados.
- Rodar `get_errors` nos arquivos tocados.
- Rodar `git diff --check`.
- Criar commit local com escopo claro.
- Fazer push apenas quando solicitado.
