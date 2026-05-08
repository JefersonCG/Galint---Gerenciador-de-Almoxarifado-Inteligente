# Organização da Raiz do Repositório

## Objetivo

Reduzir a sobrecarga da raiz do projeto sem quebrar o runtime, as tasks do workspace ou a documentação já consolidada.

## Princípios

- A raiz deve manter apenas entradas principais, arquivos de configuração, documentação canônica e scripts com alto acoplamento operacional.
- Scripts manuais, diagnósticos e testes avulsos devem ir para subpastas em scripts/ por intenção.
- Artefatos de execução, análises pontuais e exports não devem voltar a se acumular na raiz.
- Pastas usadas diretamente pelo runtime devem permanecer estáveis.

## Estrutura-alvo curta

### Permanecem na raiz por enquanto

- app.py
- requirements.txt e requirements-docs.txt
- version.txt
- README.md
- scripts e PowerShell de build, HTTPS, instalação, restauração e inicialização principal
- scripts Python ainda acoplados por import direto ou por fluxo crítico de manutenção

### Saem da raiz e ficam organizados por intenção

- scripts/diagnostics
- scripts/migrations/manual
- scripts/notifications
- scripts/tests
- scripts/utilities/monitoring
- audit/analises
- audit/artefatos_execucao
- Etiquetas

## Regras práticas

- Novos diagnósticos e verificações ad hoc devem nascer em scripts/diagnostics.
- Migrações manuais fora do Alembic devem nascer em scripts/migrations/manual.
- Testes avulsos que não fazem parte da suíte principal devem nascer em scripts/tests.
- Scripts de notificação, reenvio e debug de mensageria devem nascer em scripts/notifications.
- Arquivos .galintetq usados ativamente pelo Barcode Studio continuam em data/label_layouts, inclusive em subpastas temáticas como data/label_layouts/Etiquetas.
- A pasta Etiquetas deve receber layouts/exportações soltas e utilitários relacionados a etiqueta que não façam parte do diretório runtime do app.

## Próxima onda sugerida

- Revisar scripts de repair/normalize ainda na raiz e mover os que não dependem de imports locais.
- Revisar PowerShell de build/deploy para separar setup, certificados e empacotamento sem quebrar instruções existentes.
- Consolidar CHECK_*.spec e arquivos de build em uma área dedicada após mapear o fluxo real de empacotamento.
