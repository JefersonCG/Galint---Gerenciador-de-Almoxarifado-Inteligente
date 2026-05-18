# GALINT Docs

Portal central da documentação operacional, técnica e de implantação do GALINT.

[Abrir Visão Geral](visao-geral.md){ .md-button .md-button--primary }
[README Principal](arquitetura/readme-principal.md){ .md-button }

## O que você encontra aqui

### Arquitetura

- README principal consolidado.
- plano de evolução.
- ledger e semantica de estoque.
- direção de valor financeiro do estoque.

### Operação

- estoque unificado.
- diagnóstico de saldos.
- ConversionEngine e backup associado.
- central de kits, reparos, saídas e relatórios.

### Comunicação

- instalação e automação de Telegram.
- formato de notificações.
- menu interativo e webhook.

### Infra e setup

- replicação de ambiente.
- HTTPS, backup PostgreSQL e setup local.
- executável, updates e pendrive Python portátil.

### Mobile e propostas

- build e replicação do APK.
- painel mobile e documentação dedicada.
- roadmap condominial, mensageria condominial e rastreabilidade.

## Rodar localmente

```powershell
pip install -r requirements-docs.txt
mkdocs serve
```

## Build estático

```powershell
mkdocs build --strict
```

## Como esta base foi montada

As páginas do portal usam inclusão de snippets centralizados em docs/_sources, com poucas exceções mantidas fora dessa pasta quando a origem real precisa continuar no local atual.