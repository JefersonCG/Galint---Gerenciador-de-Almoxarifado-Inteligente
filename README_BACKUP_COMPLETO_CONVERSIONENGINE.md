# README - Backup Completo e Uso com ConversionEngine

## Objetivo

Este documento descreve a nova logica implantada para backup completo do GALINT, como ela se integra ao ConversionEngine e como esse fluxo deve ser usado na operacao.

O objetivo desta entrega nao foi reescrever todo o sistema de backup. O objetivo foi implantar a primeira fatia funcional e coerente com a arquitetura atual do GALINT:

- manter o backup SQL tradicional por pg_dump
- adicionar um pacote completo em ZIP
- incluir manifest.json com metadados e compatibilidade minima
- incluir artefatos de disco relevantes do ambiente
- deixar claro que o restore oficial do ZIP passa pelo ConversionEngine

---

## O que foi implantado

### 1. Dois tipos de backup na pagina de backup

Agora a tela de backup passa a permitir dois fluxos:

1. Backup SQL
   - gera somente o dump PostgreSQL em .sql
   - pode ser usado para restauracao direta de banco ou enviado ao ConversionEngine

2. Pacote completo
   - gera um arquivo .zip
   - inclui o dump SQL dentro do pacote
   - inclui manifest.json
   - inclui um README operacional dentro do pacote
   - inclui artefatos de disco relevantes do GALINT

---

## Como a nova logica foi criada

### Camada principal

A implementacao foi feita em cima do servico ja existente de backup, sem quebrar o fluxo antigo.

Arquivo principal:

- [galint_flask/services/backup.py](galint_flask/services/backup.py)

### Estrategia adotada

1. preservar o metodo atual de geracao do dump SQL
2. usar esse dump como nucleo do pacote completo
3. coletar artefatos de disco realmente existentes no ambiente GALINT
4. gerar um manifesto com metadados de origem, versao e compatibilidade
5. empacotar tudo em ZIP para envio ao ConversionEngine

Essa abordagem foi escolhida porque o ConversionEngine ja aceita ZIP com SQL dentro. Entao a forma mais segura de evoluir era produzir um ZIP compativel com o pipeline ja existente, e nao inventar um formato paralelo.

---

## O que entra no pacote completo

Na primeira implantacao, o pacote completo inclui:

### Banco

- dump SQL gerado por pg_dump

### Artefatos de disco

- static/uploads
- static/logo
- instance/barcodes
- instance/reports

### Arquivos de runtime selecionados

- instance/network_settings.json
- instance/secret_key.txt

### Metadados

- manifest.json
- README_backup_completo.txt

---

## Estrutura esperada do ZIP

O pacote completo segue uma estrutura semelhante a esta:

```text
galint_backup_full_YYYYMMDD_HHMMSS.zip
├── database/
│   └── galint_backup_YYYYMMDD_HHMMSS.sql
├── assets/
│   ├── static/uploads/...
│   ├── static/logo/...
│   ├── instance/barcodes/...
│   ├── instance/reports/...
│   ├── instance/network_settings.json
│   └── instance/secret_key.txt
├── manifest.json
└── README_backup_completo.txt
```

---

## O que o manifest.json informa

O manifesto foi criado para dar governanca minima ao backup completo.

Ele registra:

1. tipo do backup
2. versao do schema do manifesto
3. data de criacao
4. versao do GALINT na origem
5. host de origem
6. caminho do instance usado na criacao
7. dump SQL interno
8. compatibilidade minima declarada
9. lista dos artefatos incluidos
10. lista de artefatos esperados mas ausentes
11. criticidade minima por grupo de artefato

---

## Como usar com o ConversionEngine

### Fluxo recomendado

1. abrir Configuracoes > Backup
2. clicar em Gerar pacote completo
3. aguardar a criacao do arquivo ZIP
4. abrir Configuracoes > ConversionEngine
5. enviar o arquivo ZIP gerado
6. deixar o motor extrair e localizar o dump SQL interno
7. revisar staging, manifest.json e compatibilidade
8. somente depois decidir pela implantacao ou restauracao oficial

### Por que usar o ConversionEngine

Porque o pacote completo nao deve ser tratado como restore local direto.

O papel do ConversionEngine aqui e:

1. extrair o ZIP com seguranca
2. localizar o artefato SQL principal
3. preparar staging isolado
4. validar compatibilidade da origem
5. bloquear implantacao direta quando a origem nao for segura

---

## O que mudou na pagina de backup

Arquivo alterado:

- [galint_flask/templates/config_backup.html](galint_flask/templates/config_backup.html)

Mudancas principais:

1. botoes separados para backup SQL e pacote completo
2. explicacao explicita do papel de cada tipo
3. tabela de backups com classificacao visual por tipo
4. orientacao de uso do pacote completo no ConversionEngine
5. exibicao da versao do manifesto quando houver

---

## O que mudou na camada web

Arquivo alterado:

- [galint_flask/views/pages.py](galint_flask/views/pages.py)

Mudanca principal:

1. a rota de criacao de backup agora recebe o tipo solicitado
2. ela pode gerar tanto backup SQL quanto pacote completo

---

## O que mudou na camada de servico

Arquivo alterado:

- [galint_flask/services/backup.py](galint_flask/services/backup.py)

Mudancas principais:

1. listagem de backups agora reconhece .sql e .zip
2. criacao de backup agora aceita tipo database ou complete
3. foi criado o fluxo de empacotamento completo em ZIP
4. foi criada a geracao de manifest.json
5. foi criada a coleta dos artefatos de disco relevantes
6. a listagem passa a informar dica de uso e versao do manifesto
7. exclusao continua suportando os arquivos gerados pelo novo fluxo

---

## Limites desta primeira implantacao

Esta entrega e intencionalmente conservadora.

Ela ainda nao faz:

1. restore automatico de todos os arquivos do ZIP no ambiente final
2. analise profunda de compatibilidade por versao de schema do banco
3. integracao obrigatoria com o fluxo de update
4. classificacao completa de RTO e RPO por cenario
5. revalidacao automatica periodica dos backups existentes

Ou seja: esta entrega resolve a geracao do pacote completo e deixa o pacote compativel com o caminho oficial do ConversionEngine, mas ainda nao conclui toda a plataforma de resiliencia.

---

## Pontos criticos de uso

1. o pacote completo pode conter dados sensiveis do ambiente
2. o arquivo ZIP deve ser tratado com o mesmo nivel de cuidado de um backup de producao
3. o restore final deve continuar passando por staging e validacao
4. o fato de o ZIP existir nao significa que ele ja foi restaurado e homologado

---

## Proximos passos recomendados

1. adicionar politica formal de compatibilidade minima e maxima por versao
2. integrar backup valido como pre-condicao do update
3. criar validacao automatica do manifesto no lado do ConversionEngine
4. evoluir de pacote completo para restore completo assistido
5. registrar historico de testes de restore por artefato
