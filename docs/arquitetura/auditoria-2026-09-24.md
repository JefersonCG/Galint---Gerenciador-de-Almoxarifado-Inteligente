# Auditoria técnica do GALINT — 24/09/2026

Escrito para: quem mantém o código do GALINT (desenvolvimento e manutenção).

Auditoria do sistema inteiro: horário, redundâncias, CSS, defeitos de interface
e riscos estruturais. O que já foi corrigido está marcado como **corrigido**,
com o commit correspondente. O que ficou pendente está priorizado, com o
caminho de correção e o custo estimado.

Base medida: 131 arquivos Python (87.477 linhas), 376 rotas registradas,
80 templates, 6 folhas de estilo, banco PostgreSQL de produção consultado em
24/09/2026 (somente leitura).

---

## 1. Horário — **corrigido** (commit `fdcaccb8`)

### O que estava errado

O sistema tinha **quatro formas diferentes** de gravar data e hora:

| Forma | Ocorrências | O que gravava |
|---|---:|---|
| `datetime.utcnow()` | 162 | UTC sem fuso |
| `func.now()` (default de coluna) | 72 | hora do servidor PostgreSQL |
| `datetime.now()` | 51 | hora local do processo |
| `datetime.now(timezone.utc)` | 2 (nos pontos críticos) | dependia do fuso da sessão do banco |

Medição no banco de produção, **mesmo lançamento, mesma transação**:

```
saidas.data_saida              2026-09-24 09:42:03   (hora local)
retiradas_ferramentas.data_..  2026-09-24 09:42:02   (hora local)
stock_movements.created_at     2026-09-24 12:42:03   (UTC)  <- 3 horas de diferença
operation_logs.created_at      2026-09-24 12:42:03   (UTC)
```

E como `TimeService.to_local()` assumia que todo datetime sem fuso era UTC, a
saída registrada às **09:42 aparecia como 06:42** na tela, no Telegram e nos
relatórios.

Causa raiz de `data_saida`: gravava-se `datetime.now(timezone.utc)` numa coluna
`timestamp without time zone`. O PostgreSQL converte esse valor usando o fuso da
sessão (`America/Sao_Paulo`), então o valor final dependia da configuração do
servidor, não do código.

### Como ficou

Convenção única, documentada no `TimeService`: **o banco guarda hora de São
Paulo, sem tzinfo**. Toda escrita passa por `TimeService.now_db()`.
`as_db_naive()` normaliza datas vindas de fora; `to_utc()`/`isoformat_utc()`
continuam devolvendo UTC correto para as APIs.

Ficaram deliberadamente em UTC, por serem timestamps técnicos: sessão web,
backups, logs em SQLite, integrações externas e agendador. A lista está fixada
em `test_horario_padrao_banco.py`.

### Defeito adicional encontrado durante a validação: o relógio pulava 3 horas

O `TimeService` sincroniza a hora pela internet. A primeira fonte
(worldtimeapi) responde com fuso; a segunda (timeapi.io), usada quando a
primeira falha, responde `2026-09-24T14:40:00` — já em UTC, **mas sem fuso**.
O código fazia `.astimezone(timezone.utc)` sobre esse valor sem fuso, e o Python
assume o fuso da máquina nesse caso: o horário era lido como 14:40 de Brasília,
virava 17:40 UTC e o sistema inteiro passava a gravar **3 horas adiantado** até
a próxima sincronização.

Isso aparecia de forma intermitente — só quando a primeira fonte estava fora do
ar — e foi flagrado por um teste que falhou duas vezes seguidas com
`10798 segundos` (2h59m59s) de diferença.

Três correções, todas com teste:

1. Data sem fuso vinda de uma API passa a ser marcada como UTC.
2. `sync()` recusa correções acima de 5 minutos (configurável em
   `GALINT_TIME_MAX_OFFSET_SECONDS`) e registra o aviso no log: o relógio do
   servidor é sincronizado pelo sistema operacional, então um pedido de ajuste
   de horas vem de fonte mal interpretada.
3. Quando o banco de fusos (`tzdata`) não está disponível — o caso do
   executável empacotado —, o fuso de reserva passa a ser `-03:00` em vez de
   UTC. Antes, um ambiente sem `tzdata` gravaria tudo 3 horas adiantado sem
   nenhum aviso.

### O que não foi feito e por quê

**Os registros antigos não foram convertidos.** A tabela `saidas` tem dados
mistos: hora média por mês das saídas era 16,7 h em dezembro/2025 (comportamento
de UTC) e caiu para 11,3 h em setembro/2026 (hora local) — a virada ocorreu
entre março e abril de 2026. Uma correção em massa (`+3h` ou `-3h`) acertaria
uma parte e estragaria a outra.

Recomendação: se a hora histórica precisar ficar correta, fazer por faixa de
data, com backup antes e conferência por amostragem contra as notas fiscais e
os relatórios já emitidos. Estimativa: 1 dia de trabalho, com janela de parada.

---

## 2. Tela de Registro de Saída — **corrigido**

| Item | Situação | Commit |
|---|---|---|
| Página subia ao clicar em `+` / `-` | corrigido | `fdcaccb8` |
| Lista perdida ao fechar a aba | corrigido | `b00c343d` |
| Salvamento automático a cada 60 s | corrigido | `c30ce66d` |
| Item zerado invisível na busca | corrigido | `b00c343d` |
| "Sem saldo" em vez de dizer com quem está a ferramenta | corrigido | `b00c343d` |

O scroll acontecia porque, depois de redesenhar a tabela, o código chamava
`inputCodigo.focus()` — e o navegador rolava até o campo de código, no topo da
página. Agora o foco usa `preventScroll` e volta para o próprio botão clicado.
Os `onclick` inline da lista viraram um listener delegado no corpo da tabela.

---

## 3. Redundâncias — parcialmente corrigido

### 3.1 Utilitários JavaScript repetidos — **corrigido**

| Função | Cópias antes | Depois |
|---|---:|---|
| `escapeHtml` | 14 arquivos | `GalintCore.escapeHtml` |
| `fetchJson` | 7 arquivos | pendente (ver 5.2) |
| `normalizeAutocompleteText` | 4 arquivos | `GalintCore.normalizeText` |
| `formatCurrencyBR` | 3 arquivos | `GalintCore.formatCurrencyBR` |
| `publishMirrorState` / `buildMirrorPayload` | 4–5 arquivos | pendente (ver 5.2) |

As cópias não eram idênticas: algumas versões de `escapeHtml` imprimiam
`undefined` quando o valor chegava nulo, porque não tinham a guarda que as
outras tinham. A versão central trata isso. A regra diferente da tela
fracionada (mostrar `R$ 0,00` em vez de vazio) foi preservada explicitamente.

Ao todo, 54 nomes de função JS aparecem em mais de um arquivo — o levantamento
completo sai com:

```bash
grep -rn "function " --include="*.mako" --include="*.html" --include="*.js" galint_flask
```

### 3.2 Endpoints de busca de item — **corrigido**

`/movimentos/api/buscar-item` e `/ferramentas/buscar-item` repetiam o mesmo
trecho e cada um recarregava os modelos **um por um** para descobrir o valor de
referência. Agora ambos usam `services/item_lookup_service.py`, que carrega os
itens em uma consulta só. O payload dos dois endpoints foi comparado campo a
campo antes e depois: idêntico.

### 3.3 Código morto — **corrigido** (9 arquivos, ~14 mil linhas)

`telegram_service.py.bak_modelo3` (11.256 linhas), `templates/movements/saida.html`,
`templates/movements/index.html`, `inventory/form_old.html`,
`inventory/form_invisible.html`, `inventory/form_tabs.html`,
`config_condominium_blueprint.html`, `sidebar.html`, `sidebar_clean.html`.

Nenhum era referenciado por rota, `include` ou `extends`. Havia o risco concreto
de alguém editar a cópia errada — os arquivos `movements/saida.html` e
`movements/index.html` até avisavam no cabeçalho que eram legados.

Continuam no disco, **fora do git** (não foram apagados porque não estão
versionados): `templates/sobre.html.bak` e
`templates/inventory/form_soft_depth_backup.html`.

---

## 4. CSS — **corrigido** na base, com pendências de volume

### 4.1 O que foi feito

- `static/css/galint-tokens.css`: 71 custom properties CSS3 substituíram **2.051
  valores literais em 69 arquivos**. Havia 276 cores hexadecimais distintas
  espalhadas por até 61 telas (`#f8fafc` aparecia 352 vezes; `#ffffff`, 278).
- Recursos CSS3 agora valendo para todas as telas, via `:where()` (especificidade
  zero, não atropela o estilo de cada página): `:focus-visible`,
  `prefers-reduced-motion`, `color-scheme`, barra de rolagem fina, `::selection`,
  `text-wrap: balance/pretty`, tipografia fluida com `clamp()`, mídia
  responsiva, `:disabled` uniforme, `scroll-behavior` sob `@supports` e regras
  de impressão.
- O CSS da tela de saída (23 KB) saiu do template para
  `static/css/movements-saida.css`: o HTML caiu de 177 KB para 154 KB por acesso
  e o estilo passou a ser cacheado.
- Verificação: 82 blocos CSS analisados com `tinycss2`, zero erro de sintaxe;
  52 tokens usados, todos definidos, nenhum `var()` órfão.

### 4.2 O que falta

**872 KB de CSS ainda estão dentro dos templates** e são reenviados a cada
acesso. Os maiores:

| Template | CSS inline |
|---|---:|
| `inventory/list.html` | 86 KB |
| `inventory/form.html` | 71 KB |
| `dashboard/index.html` | 66 KB |
| `nf/index.html` | 56 KB |
| `movements/painel_espelho.html` | 50 KB |

Caminho: repetir o que foi feito na tela de saída — mover o bloco `<style>` para
`static/css/<tela>.css` e referenciar com `<link>`. Cada tela leva poucos
minutos, mas precisa de conferência visual, porque algumas usam variáveis de
template dentro do CSS. Estimativa: meio dia para as cinco maiores.

---

## 5. Pendências priorizadas

### 5.1 Peso das telas de estoque (alto impacto)

| Tela | HTML por acesso |
|---|---:|
| `/itens/consumo` | 6,18 MB |
| `/itens/valor-estoque` | 3,99 MB |
| `/itens/projecao-compras` | 3,16 MB |
| `/itens` | 2,16 MB |

Essas páginas montam a tabela inteira no HTML. Em rede local passa, mas em VPN
ou celular a espera é longa e o navegador trava ao renderizar. Caminho:
paginação no servidor ou carregamento por demanda (a API já existe em vários
casos). Estimativa: 1 a 2 dias por tela.

### 5.2 Espelho da operação duplicado (médio)

`publishMirrorState`, `buildMirrorPayload` e `cloneMirrorBatchItem` estão
copiados em `saida.mako`, `saida_fracionada.mako`, `retirar.mako` e
`entrada.html`, com divergências pequenas entre as cópias. Caminho: mover para
`static/js/mirror-screen-launcher.js`, que já existe e já é carregado por essas
telas. Estimativa: meio dia, com teste no segundo monitor.

### 5.3 Erros engolidos sem registro (médio)

170 blocos `except ...: pass` sem log, concentrados em
`telegram_service.py` (41), `services/inventory.py` (15),
`views/inventory.py` (13) e `services/backup.py` (12). Vários são legítimos
(fallback de conversão, notificação que não deve travar a operação), mas sem
log não se sabe quando o fallback foi acionado — uma falha de notificação, por
exemplo, some sem deixar rastro. Caminho: trocar `pass` por
`logger.debug(...)`/`logger.warning(...)` com a exceção, começando pelos
fluxos de estoque. Estimativa: 1 dia.

### 5.4 Arquivos e funções grandes demais (médio)

`telegram_service.py` tem 13.180 linhas; `services/inventory.py`, 7.320;
`views/inventory.py`, 5.295. Há 45 funções com mais de 200 linhas — a maior,
`_handle_item_create_text`, tem 629. Isso torna qualquer alteração arriscada,
porque o efeito colateral não cabe na cabeça de quem lê. Caminho: separar
`telegram_service.py` por assunto (notificações, relatórios, bot de comandos,
fluxo de cadastro), que já são blocos independentes. Estimativa: 2 a 3 dias,
feito por partes.

### 5.5 Três padrões de autorização convivendo (baixo, mas confunde)

Existem `@login_required`, `@token_required`/`@mobile_login_required` e
checagem manual dentro da função (`ferramentas.retirar_multipla`,
`devolucao_expressa_*`). **Nenhuma rota ficou desprotegida** — a checagem manual
existe para devolver JSON em vez do redirect HTML do Flask-Login. Caminho:
criar um decorator `@api_login_required` que devolva JSON e usar nas rotas de
API. Estimativa: 2 horas.

### 5.6 Arquivos soltos na raiz do projeto (baixo)

A raiz tem dezenas de scripts avulsos (`corrigir_*.py`, `fix_*.py`,
`check_*.py`, `repair_*.py`, `reverter_*.py`) misturados ao código da
aplicação, além de 8 arquivos `.spec` de build e várias pastas `.venv*`.
Caminho: mover para `scripts/manutencao/` e acrescentar as pastas de ambiente
ao `.gitignore`. Estimativa: 2 horas.

### 5.7 BOM em `telegram_service.py` (baixo)

O arquivo começa com BOM (`U+FEFF`). O Python aceita, mas ferramentas de
análise quebram ao ler o arquivo como UTF-8 puro. Caminho: regravar sem BOM.
Estimativa: 5 minutos — foi deixado de fora porque mexer no arquivo inteiro
polui o diff desta auditoria.

---

## 6. Verificações que ficaram como guarda automática

Três arquivos de teste novos impedem que os problemas voltem:

| Teste | O que trava |
|---|---|
| `test_horario_padrao_banco.py` (11 casos) | volta de `datetime.utcnow()` ou `default=func.now()`; hora gravada diferente da exibida |
| `test_auditoria_estrutura.py` (7 casos) | rota apontando para template inexistente; cópia de backup versionada; tela reimplementando utilitário central; `onclick` inline na lista de saída |
| `test_saida_disponibilidade_ferramenta.py` (7 casos) | mensagem de ferramenta em uso, em reparo e item zerado |

Suíte completa: 86 testes, todos verdes.

---

## 7. Como reproduzir as medições

```bash
# horário: compara as tabelas do mesmo lançamento
python -c "from galint_flask import create_app; ..."   # ver seção 1

# cores repetidas no CSS
grep -rno "#[0-9a-fA-F]\{6\}" galint_flask/static/css galint_flask/templates | sort | uniq -c | sort -rn

# funções JS com o mesmo nome em telas diferentes
grep -rn "function " --include="*.mako" --include="*.html" --include="*.js" galint_flask

# peso das telas
python -m pytest test_auditoria_estrutura.py -q
```
