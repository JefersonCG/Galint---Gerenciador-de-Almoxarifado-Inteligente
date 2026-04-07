# Diagnóstico do saldo dos cards de categoria

Data: 2026-04-07

## O que o card mostra hoje

- A tela de estoque por categoria renderiza `category.saldo_total` em `galint_flask/templates/inventory/list.html`.
- Esse valor é calculado em `galint_flask/views/inventory.py` como a soma simples de `item["saldo"]` de todos os itens da categoria.
- O `saldo` de cada item vem de `inventory_service.list_items()`, que usa o saldo físico total já corrigido para a unidade interna canônica do item.
- Resultado: o card mistura no mesmo número saldos em `un`, `L`, `Kg`, `m`, `Peça`, `Par` e também alguns cadastros antigos com unidade textual inconsistente.

## Conclusão sobre os números grandes do print

- O número do card não é valor financeiro.
- O número do card não é uma unidade única da categoria.
- O número do card é uma soma heterogênea de saldos físicos corrigidos item a item.
- Depois das correções recentes de saldo/unidade, o saldo individual dos itens ficou mais correto e mais visível; por isso o problema semântico do card ficou mais evidente.

## Composição real verificada

### Mat. Pintura e Drywall

- Card atual: `998851.01`
- Composição por unidade interna:
  - `997958 un`
  - `479.4 L`
  - `337.92 Kg`
  - `28 m`
- Maior peso: `7898936842060 - PARAFUSO DRYWALL 25X3,5MM` com `994006 un`.

### Materiais de Limpeza

- Card atual: `175847.5`
- Composição por unidade interna:
  - `174501 un`
  - `1162.5 L`
  - `184 Peça`
- Maiores pesos:
  - `7899682763500 - PAPEL TOALHA INTERFOLHAS`: `144000 un`
  - `300L - SACO LIXO 300 LITROS`: `14200 un`
  - `200L - SACO LIXO 200 LITROS`: `7500 un`

### Material Construção

- Card atual: `195407`
- Composição por unidade interna:
  - `194278 un`
  - `454 m`
  - `394 Kg`
  - `23 L`
- Maior peso: `7899482300370 - BUCHA N10` com `181903 un`.

## Cruzamento de entradas e valores dos maiores itens

### 7899682763500 - PAPEL TOALHA INTERFOLHAS

- Saldo atual: `144000 un`
- Lastro documental/financeiro identificado:
  - Documento `012901`
  - `60 pacotes`
  - `60000 un` em base
  - `R$ 1.074,00`
  - `R$ 17,90` por pacote
- Também existe histórico legado de entrada de `107 pacotes`.
- Ledger verificado:
  - entradas: `167000 un`
  - saídas: `-23000 un`
  - saldo final: `144000 un`
- Conclusão: o saldo atual fecha com o histórico; o número é alto, mas faz sentido para esse item.

### 7897432701123 - FITA TESTE

- Saldo atual: `400 un`
- Lastro documental/financeiro identificado:
  - Documento manual `002998`
  - `30 pacotes`
  - `750 un` em base
  - `R$ 1.200,00`
  - `R$ 40,00` por pacote
- Também existe histórico legado de entrada de `17 pacotes`.
- Ledger verificado:
  - entradas: `425 un`
  - saídas: `-25 un`
  - saldo final: `400 un`
- Conclusão: consistente.

### 789987456654003 - TERMINAL TUBULAR SIMPLES 2,5MM AZUL

- Saldo atual: `2000 un`
- Lastro documental/financeiro identificado:
  - Documento `089696`
  - `2 pacotes`
  - `R$ 116,20` total
  - `R$ 58,10` por pacote
- Ledger verificado:
  - entradas: `4000 un`
  - saídas: `-2000 un`
  - saldo final: `2000 un`
- Conclusão: o saldo atual é plausível, embora o documento financeiro não esteja preenchendo `quantidade_base`; o saldo não parece inflado.

## Itens grandes sem lastro financeiro/documental atual

### 7898936842060 - PARAFUSO DRYWALL 25X3,5MM

- Saldo atual: `994006 un`
- Não há linhas em `entrada_documento_itens`.
- Não há linhas em `finance_lancamentos`.
- O saldo atual vem principalmente de histórico legado e ajustes:
  - entradas legadas: `281 caixas`
  - grande ajuste inicial legado: `de 0 para 2000`
  - saídas legadas grandes: `1000`, `280` e outras
  - ajustes manuais adicionais no item
- Conclusão: o saldo existe no ledger, mas não tem comprovação financeira atual no modelo documental; é um saldo herdado de ajustes legados e merece revisão operacional.

### 7899482300370 - BUCHA N10

- Saldo atual: `181903 un`
- Não há linhas em `entrada_documento_itens`.
- Não há linhas em `finance_lancamentos`.
- O saldo atual vem de:
  - ajuste inicial legado `de 0 para 490`
  - várias saídas legadas
  - ajustes manuais via edição do item
- O fator cadastrado está em `427 un` por pacote.
- Conclusão: o saldo é derivado quase todo de ajuste manual legado, não de compra documentada; precisa ser tratado como saldo operacional herdado, não como saldo financeiro comprovado.

### 300L - SACO LIXO 300 LITROS

- Saldo atual: `14200 un`
- Não há documento de entrada atual vinculado.
- Há apenas lançamento financeiro estimado (`valor_estimado`) com valor total `0`.
- O saldo atual vem de:
  - entrada legada de `106 pacotes`
  - ajustes manuais de embalagem
  - saídas posteriores
- Conclusão: o saldo é operacionalmente plausível, mas não está lastreado por valor financeiro documental no modelo novo.

### 7898159800083 - FITA VEDA ROSCA 18X50mm

- Saldo atual: `850 m`
- Não há documento/financeiro atual vinculado.
- O saldo veio de:
  - ajuste inicial legado `19 rolos`
  - duas saídas de `1 rolo`
- Conclusão: saldo operacional coerente, mas sem lastro financeiro no modelo documental novo.

## Síntese final

- O card de categoria hoje soma saldos físicos heterogêneos; por isso o número não representa nem quantidade homogênea nem valor.
- Parte dos maiores itens está correta e documentada no financeiro novo.
- Outra parte dos maiores itens é saldo herdado por ajustes manuais/legado, sem documento financeiro associado.
- Se a tela continuar exibindo um único `saldo_total`, o usuário tende a interpretar esse número como algo que ele não é.

## Recomendações

- Remover o `saldo_total` único do card, ou
- Exibir o card quebrado por unidade interna (`un`, `L`, `Kg`, `m`), ou
- Trocar o card para valor financeiro real, usando o fluxo de `valor-estoque`.