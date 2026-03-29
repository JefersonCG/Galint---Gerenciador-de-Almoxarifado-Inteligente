# Aplicacao Em Outra Maquina

Este documento consolida o plano seguro para integrar o que foi feito nesta maquina com o que ja foi feito em outra maquina, sem sobrescrever trabalho e sem gerar dor de cabeca para o outro programador.

## Objetivo

Existem hoje duas linhas de atualizacao:

1. Esta maquina
   - commit local principal: acbf41e
   - foco: shell visual, topbar, sidebar, login, ajustes responsivos, limpeza de instrucoes em telas operacionais, modais de ajuda, refinamentos de espacamento e hover, alem de arquivos novos de ledger que ja estavam no working tree

2. Outra maquina
   - commit principal: 7880242
   - mensagem: feat(notify): finalizar push mobile e payload visual
   - commit mobile: 0ba0ad6
   - mensagem: feat(notify): registrar push e badge no app mobile

O trabalho correto nao e copiar arquivos manualmente. O correto e integrar os commits de forma rastreavel.

## Ordem Recomendada

Primeiro sobe a base desta maquina. Depois o outro programador integra o trabalho dele em cima dela.

Ordem:

1. Publicar a branch desta maquina com o commit acbf41e
2. Na outra maquina, buscar essa branch e criar uma branch de integracao baseada nela
3. Integrar o commit 7880242 no repositorio principal
4. Integrar o commit 0ba0ad6 dentro do repositorio mobile
5. Atualizar o ponteiro de galint-mobile no repositorio principal
6. Validar tudo e so depois publicar a branch integrada

## Por Que Esta Ordem

As alteracoes desta maquina mudam a base visual compartilhada:

1. galint_flask/static/css/qss_like.css
2. galint_flask/static/css/galint-modern.css
3. galint_flask/static/css/app.tailwind.css
4. galint_flask/templates/base.html
5. galint_flask/templates_mako/base.mako
6. galint_flask/templates/auth/login.html
7. componentes de sidebar, topbar e telas operacionais

Essas mudancas servem melhor como base. O trabalho da outra maquina sobre notify, payload visual e push mobile tende a ser integrado por cima com menos conflito estrutural.

## Estado Atual Desta Maquina

### Repositorio principal

1. branch local: sync/central-dark-master
2. commit local consolidado: acbf41e
3. mensagem:

```text
fix: consolidar correcoes visuais e tecnicas do GALINT
```

### Escopo principal do commit acbf41e

1. topbar, sidebar e shell global refinados
2. login responsivo e mais limpo
3. orientacao movida de telas operacionais para modais de ajuda
4. normalizacao de hover e espacamento
5. ajustes em Jinja e Mako para o shell compartilhado
6. arquivos novos de ledger que ja estavam pendentes no workspace:
   - migrations/versions/b6f4d3a9e8c1_add_stock_ledger_tables.py
   - scripts/backfill_stock_ledger.py
   - scripts/reconcile_stock_ledger.py
   - test_stock_ledger.py

## Estado Informado Da Outra Maquina

### Repositorio principal

1. commit: 7880242
2. mensagem:

```text
feat(notify): finalizar push mobile e payload visual
```

### Mobile

1. commit: 0ba0ad6
2. mensagem:

```text
feat(notify): registrar push e badge no app mobile
```

### O Que Foi Feito La

1. push token automatico no app mobile
2. reaproveitamento do registro no login mobile
3. badge de nao lidas no menu mobile
4. resumo de inbox no mobile
5. payload visual generico para notificacoes de item no backend
6. padronizacao de notificadores Telegram antigos com media e payload visual

## Procedimento Para O Outro Programador

### Parte 1. Trazer a base desta maquina

No repositorio principal da outra maquina:

```powershell
git fetch origin
git checkout -b integracao/ui-notify origin/sync/central-dark-master
```

Se a branch ainda nao existir no remoto, substituir pelo nome real da branch publicada desta maquina.

### Parte 2. Integrar o backend da outra maquina

Se o commit 7880242 estiver em outra branch local ou remota:

```powershell
git cherry-pick 7880242
```

Se estiver em branch dedicada, tambem pode ser merge:

```powershell
git merge <branch-do-notify>
```

### Parte 3. Integrar o mobile na pasta galint-mobile

Entrar no repositorio mobile:

```powershell
cd galint-mobile
git fetch
git checkout <branch-mobile-correta>
git cherry-pick 0ba0ad6
```

Se o mobile estiver sendo integrado por merge em vez de cherry-pick:

```powershell
git merge <branch-mobile>
```

Depois publicar o mobile, se houver remoto configurado:

```powershell
git push origin <branch-mobile-correta>
```

### Parte 4. Atualizar o ponteiro do mobile no principal

Voltar para a raiz do projeto principal:

```powershell
cd ..
git add galint-mobile
git commit -m "chore: atualizar ponteiro do mobile com push e badge"
```

### Parte 5. Validar a integracao

No principal:

```powershell
git status
git log --oneline -n 5
```

Se houver migracoes pendentes:

```powershell
flask db upgrade
```

Se for usar submodulo e o ambiente exigir:

```powershell
git submodule update --init --recursive
```

## Checklist Tecnico De Validacao

### Web

1. topbar com marca em um extremo e acoes no extremo oposto
2. sidebar dark
3. fundo geral claro atras do shell
4. login com novo layout responsivo
5. telas operacionais mais limpas com modal de ajuda

### Backend notify

1. route_item_created com payload visual
2. operation_visual_payload com builder generico de item
3. notification_router anexando visual em eventos de item criado
4. telegram_service usando media_payload e outbox nos fluxos migrados

### Mobile

1. expo-notifications instalado e configurado
2. expo-constants instalado e configurado
3. app.json com plugin de notificacoes
4. login mobile reaproveitando o registro do push
5. menu mobile exibindo badge de unread_count
6. notifications screen atualizando o resumo da inbox

### Runtime

1. teste real de push em aparelho fisico Android
2. validacao de envio do token ao backend
3. build EAS acompanhado ate o fim
4. navegador recarregado com Ctrl+F5 para evitar cache antigo de CSS

## O Que O Outro Programador Deve Me Enviar

Para eu ajudar sem atrito e sem adivinhar o estado da outra maquina, eu preciso receber estes itens.

### Minimo obrigatorio

1. nome da branch onde ele integrou o trabalho
2. hash final do commit principal depois da integracao
3. hash final do commit do mobile depois da integracao
4. saida de:

```powershell
git log --oneline -n 10
git status
git -C galint-mobile log --oneline -n 10
git -C galint-mobile status
```

### Muito importante

1. lista dos arquivos que conflitaram
2. informacao se houve merge ou cherry-pick
3. confirmacao se rodou migracao
4. confirmacao se atualizou dependencias do mobile
5. confirmacao se o build EAS foi executado

### Melhor formato para eu receber

Preferencia de entrega:

1. resumo curto em texto
2. hashes finais
3. git show --stat do commit final principal
4. git show --stat do commit final do mobile
5. se houver conflito, diff dos arquivos conflitados

Exemplo ideal do que ele pode mandar:

```text
Branch de integracao: integracao/ui-notify
Commit final principal: <hash>
Commit final mobile: <hash>
Metodo usado: cherry-pick 7880242 + cherry-pick 0ba0ad6
Conflitos: nenhum
Migracao executada: sim/nao
Build EAS executado: sim/nao
Push em aparelho fisico: sim/nao
```

## Mensagem Pronta Para Encaminhar Ao Outro Programador

```text
Subi a base desta maquina com as correcoes visuais e tecnicas do GALINT.

Base para integrar:
- branch: sync/central-dark-master
- commit: acbf41e

O ideal e voce partir dessa base e integrar por cima:
- backend principal da sua maquina: 7880242
- mobile da sua maquina: 0ba0ad6

Ordem sugerida:
1. fetch da branch com acbf41e
2. criar branch de integracao a partir dela
3. cherry-pick ou merge do 7880242 no principal
4. entrar em galint-mobile e integrar 0ba0ad6
5. voltar ao principal e commitar o novo ponteiro de galint-mobile
6. validar web, backend notify e mobile

Checklist rapido:
- topbar e sidebar corretos
- login novo
- modais de ajuda nas telas operacionais
- payload visual em item criado
- mobile registrando push token
- badge de nao lidas no menu
- build EAS acompanhado

Quando terminar, me envie:
- nome da branch de integracao
- hash final do principal
- hash final do mobile
- se houve conflito e em quais arquivos
- confirmacao de migracao, build EAS e teste de push
```

## Regra Final

Nao copiar arquivos manualmente entre maquinas. Integrar por commit e por branch. Isso preserva historico, facilita suporte e evita perder correcoes de um lado ou do outro.