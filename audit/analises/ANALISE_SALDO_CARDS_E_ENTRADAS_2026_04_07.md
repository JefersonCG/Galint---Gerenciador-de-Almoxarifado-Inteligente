# Análise dos cards de saldo e das maiores entradas

Data: 2026-04-07

## Resumo

- O card "Saldo total" em Estoque por categoria não representa valor financeiro.
- A tela soma o campo `saldo` de todos os itens da categoria, mesmo quando os itens usam unidades internas diferentes (`un`, `L`, `Kg`, `m`, `Peça`, `Par`).
- Depois das correções de saldo e embalagem, o saldo individual dos itens passou a refletir melhor a unidade base canônica. Isso deixou o card ainda mais enganoso, porque ele agora soma números corretos de naturezas diferentes.

## Origem no código

- A listagem prepara `saldo` por item em `inventory_service.list_items()`.
- O card de categoria soma `saldo_total = sum(item["saldo"])` na view de inventário.
- O template apenas renderiza esse número bruto como `Saldo total`.

## Composição real dos maiores cards

### Mat. Pintura e Drywall

- Total do card: `998851.01`
- Composição por unidade interna: `997958 un + 479.4 L + 337.92 Kg + 28 m + resíduos de cadastro legado`
- Principal peso: `7898936842060 - PARAFUSO DRYWALL 25X3,5MM` com `994006 un`

### Materiais de Limpeza

- Total do card: `175847.5`
- Composição por unidade interna: `174501 un + 1162.5 L + 184 peças`
- Principal peso: `7899682763500 - PAPEL TOALHA INTERFOLHAS` com `144000 un`
- Também pesam: `300L` com `14200 un`, `200L` com `7500 un`, `100L` com `4800 un`

### Material Construção

- Total do card: `195407`
- Composição por unidade interna: `194278 un + 454 m + 394 Kg + 23 L`
- Principal peso: `7899482300370 - BUCHA N10` com `181903 un`

## Cruzamento das maiores entradas

### 7899682763500 - PAPEL TOALHA INTERFOLHAS

- Situação: consistente
- Fator de embalagem: `1000`
- Saldo atual: `144000 un`
- Documento financeiro encontrado: NF `012901`
- Linha documental: `60 pacotes`, `60000 un base`, `R$ 17,90 por pacote`, `R$ 1074,00 total`
- Histórico operacional:
  - Entradas totais no ledger: `167000 un`
  - Saídas totais no ledger: `23000 un`
  - Saldo: `144000 un`
- Leitura: o saldo atual fecha com o histórico. A entrada da NF `012901` é real e foi incorporada corretamente.

### 7897432701123 - FITA TESTE

- Situação: consistente
- Fator de embalagem: `25`
- Saldo atual: `400 un`
- Documento financeiro encontrado: NF `002998`
- Linha documental: `30 pacotes`, `750 un base`, `R$ 40,00 por pacote`, `R$ 1200,00 total`
- Histórico operacional:
  - Entrada legada: `425 un`
  - Saída total: `25 un`
  - Saldo: `400 un`
- Leitura: item coerente; há valor documental e o saldo fecha.

### 300L - SACO LIXO 300 LITROS

- Situação: operacionalmente coerente, mas sem lastro documental financeiro atual
- Fator de embalagem: `100`
- Saldo atual: `14200 un`
- Documento financeiro atual: não encontrado em `entrada_documento_itens`
- Histórico operacional:
  - Entrada legada total: `106 pacotes`
  - Entradas no ledger: `15600 un`
  - Saídas no ledger: `1400 un`
  - Saldo: `14200 un`
- Leitura: o saldo fecha operacionalmente, mas depende de legado e não há documento financeiro atual para validar o valor de compra.

### 7899482300370 - BUCHA N10

- Situação: saldo alto sem suporte documental financeiro atual
- Fator de embalagem: `427`
- Saldo atual: `181903 un`
- Documento financeiro atual: não encontrado
- Preço de compra atual no item: `None`
- Histórico operacional:
  - Entradas no ledger: `209662 un`
  - Saídas no ledger: `27759 un`
  - Saldo: `181903 un`
- Origem principal do saldo: ajuste legado em `inventario_evento` de `209230 un`
- Leitura: o saldo atual fecha matematicamente no ledger, mas não está suportado por documento financeiro atual; precisa ser tratado como estoque legado/importado.

### 7898936842060 - PARAFUSO DRYWALL 25X3,5MM

- Situação: item mais sensível da análise
- Fator de embalagem: `1000`
- Unidade canônica esperada: `un`
- Saldo atual: `994006 un`
- Documento financeiro atual: não encontrado
- Preço de compra atual no item: `None`
- Histórico operacional:
  - Entradas no ledger: `2281001`
  - Saídas no ledger: `1286995`
  - Saldo: `994006`
- Problema encontrado:
  - os movimentos do ledger estão com `unit_base='kg'`, embora o item seja de unidade canônica `un`
  - a origem do saldo é majoritariamente ajuste/importação legado, não NF atual
- Leitura: o saldo fecha dentro do ledger, mas o cadastro está semanticamente inconsistente e sem lastro financeiro atual. Este item merece revisão específica antes de qualquer uso financeiro.

### 7898159800083 - FITA VEDA ROSCA 18X50mm

- Situação: operacionalmente coerente
- Fator de embalagem: `50`
- Saldo atual: `850 m`
- Documento financeiro atual: não encontrado
- Histórico operacional:
  - Ajuste legado inicial: `950 m`
  - Saídas: `100 m`
  - Saldo: `850 m`
- Leitura: saldo coerente no operacional, mas sem documento financeiro atual.

## Conclusão

- O problema principal do card não é mais inflação simples de saldo item a item.
- O card está semanticamente errado porque soma quantidades físicas de unidades diferentes como se fossem comparáveis.
- Entre os maiores itens analisados:
  - com suporte documental/financeiro claro: `7899682763500`, `7897432701123`
  - coerentes no operacional, mas dependentes de legado: `300L`, `7898159800083`
  - altos e sem lastro financeiro atual, pedindo revisão: `7899482300370`, `7898936842060`

## Recomendação

- Não usar o card atual como indicador de valor ou volume agregado da categoria.
- Se a tela continuar exibindo resumo por categoria, o ideal é substituir por uma destas opções:
  - quantidade de itens na categoria
  - total por unidade interna (`un`, `L`, `Kg`, `m`)
  - valor financeiro real, usando o relatório de valor de estoque