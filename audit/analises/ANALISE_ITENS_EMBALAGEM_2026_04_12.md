# Analise de Itens com Embalagem - 2026-04-12

## Resumo

- Auditoria oficial recalculada com a mesma logica de fator, ledger e decomposicao usada pelo sistema.
- A contagem rapida anterior de 125 itens era heuristica. A auditoria oficial encontrou 163 itens com embalagem/fator resolvido e 132 com divergencia visual esperada entre total interno e leitura em embalagens/soltas.
- A correcao de codigo aplicada em galint_flask/views/inventory.py cobre o falso erro de salvamento para todos os 132 itens com divergencia visual esperada.

## Contagens

- Itens com embalagem e fator resolvido: 163
- Itens com divergencia visual total: 132
- Itens alinhados e esperados: 129
- Itens com metadado ignorado mas alinhados: 2
- Itens com inconsistencia real de read model: 1
- Itens com fator nao resolvido: 5

## Inconsistencia Real

- 7891114029925 | JOGO DE CHAVE DE FENDA 6 PEÇAS | tipo=pacote | saldo_base=71.0 | embalagens=12.0 | soltas=0.0

## Metadados Ignorados Pelo Estoque

- Esses itens caem na regra de toolkit/jogo, em que a embalagem nao deve governar o saldo operacional.

- 7891114029925 | JOGO DE CHAVE DE FENDA 6 PEÇAS | tipo=pacote | saldo_base=71.0 | embalagens=12.0 | soltas=0.0
- 7891504352909 | JOGO DE CHAVE DE FENDA ISOLADAS 1000V | tipo=caixa | saldo_base=18.0 | embalagens=3.0 | soltas=0.0
- 7899612702524 | JOGO DE CHAVE ALLEN LONGA | tipo=pacote | saldo_base=63.0 | embalagens=7.0 | soltas=0.0

## Fator Nao Resolvido

- Esses itens precisam de revisao de cadastro para informar corretamente o conteudo por embalagem ou remover o tipo de embalagem.

- 07892904021716 | BARRAMENTOS IEC CURTO TERMINAL COM PINO TCC 25 | tipo=pacote | saldo_base=1.0 | embalagens=0.0 | soltas=0.0
- 7898214962961 | TP-2322 PRÉ-ISOLADO 23MM 1,5-2,5MM 27A AZUL | tipo=pacote | saldo_base=1.0 | embalagens=0.0 | soltas=0.0
- 7898927870669 | JOGO DE SERRA COPO 11PEÇAS | tipo=caixa | saldo_base=0.0 | embalagens=0.0 | soltas=0.0
- CABO-RG6-001 | Cabo Coaxial RG6 Preto | tipo=rolo | saldo_base=0.0 | embalagens=0.0 | soltas=0.0
- UYLN30460 | SUPORTE DE PAREDE SUPER ADERENTE | tipo=pacote | saldo_base=10.0 | embalagens=0.0 | soltas=0.0

## Arquivo Completo

- A lista completa dos 168 itens auditados esta em analise_itens_embalagem_2026_04_12.csv.
- Coluna status_auditoria:
- divergencia_esperada: diferenca normal entre total interno e leitura em embalagens/soltas.
- metadado_ignorado_alinhado: item tipo jogo/kit com metadado de embalagem ignorado e estado coerente.
- metadado_ignorado_desalinhado: item tipo jogo/kit cujo read model de embalagem ficou desatualizado.
- fator_nao_resolvido: cadastro com tipo de embalagem, mas sem fator confiavel para conversao.
- sem_divergencia_visual: item com embalagem cujo total interno hoje coincide com a leitura simplificada.
