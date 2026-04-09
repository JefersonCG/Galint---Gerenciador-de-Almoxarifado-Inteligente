# README_AUDITORIA_NF_CUPOM_SEM_COMPROVACAO

## Resumo

- Data da auditoria: 2026-04-08
- Universo auditado: 117 itens com origem NF/Cupom no item ou no financeiro
- Itens com pendencia documental/financeira: 30
- Pendencias por tipo: finance:sem_comprovacao=13, sem_finance_lancamento=4, nf_sem_chave=19

## Criterio

- Item entra no universo se tiver origem de compra por NF/Cupom no cadastro do item ou em finance_lancamentos.
- O item entra na lista final se tiver ao menos uma destas pendencias: lancamento financeiro sem_comprovacao, ausencia de lancamento financeiro para origem NF/Cupom, ou NF sem chave de acesso em item/financeiro/documento de estoque.
- Placeholders textuais como None, SEM NF e SEM NF/CUPOM foram tratados como ausencia de comprovacao real.

## Itens para saneamento manual

| Codigo | Descricao | Categoria | Fonte item | Documento/NF/Cupom | Financeiro | Documento estoque | Chave | Pendencias |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0281 | ARCO DE SERRA | Ferramentas | Estimado | - | manual SEM NF / sem_comprovacao | manual 0277 | - | finance:sem_comprovacao |
| 789987456654100 | BOLSA DE FERRAMENTAS | Ferramentas | - | - | manual SEM NF/CUPOM / sem_comprovacao | manual SEM NF/CUPOM | - | finance:sem_comprovacao |
| 7897937446475 | COLHER DE PEDREIRO 8'' CANTO RETO | Ferramentas | Estimado | 7897937446475 | manual 7897937446475 / sem_comprovacao | manual 7897937446475 | - | finance:sem_comprovacao |
| 7899612712714 | ESPATULA DE ACO 12CM | Ferramentas | Estimado | - | manual SEM NF/CUPOM / sem_comprovacao | manual SEM NF/CUPOM | - | finance:sem_comprovacao |
| 7899833501500 | PERFILADO 38X38X300MM | Material Construcao | Estimado | - | manual SEM NF/CUPOM / sem_comprovacao | manual SEM NF/CUPOM | - | finance:sem_comprovacao |
| 7899710007767 | PAINEL SLIM EMBUTIDO 12W 3000K  BRANCA MORNA | Material Eletrico | compra_nf | 1113587 | nf 1113587 / sem_comprovacao | nf 1113587; nf 2344855 | ok | finance:sem_comprovacao |
| 7898542005255 | TAMPA SEGA 4X4 C/SUPORTE | Material Eletrico | Estimado | 7898542005255 | manual 7898542005255 / sem_comprovacao | manual 7898542005255 | - | finance:sem_comprovacao |
| 78998745665421 | TERMINAL GARFO 2,5MM VERMELHO | Material Eletrico | Estimado | - | manual SEM NF/CUPOM / sem_comprovacao | manual SEM NF/CUPOM | - | finance:sem_comprovacao |
| 789987456654002 | TERMINAL TUBULAR SIMPLES 1,5MM PRETO | Material Eletrico | NF | 089698 | nf 089698 / sem_comprovacao | nf 089698 | ok | finance:sem_comprovacao |
| 7899349172829 | SIFAO AJUSTAVEL RETO | Material Hidraulico | - | - | manual SEM NF/CUPOM / sem_comprovacao | manual SEM NF/CUPOM | - | finance:sem_comprovacao |
| 7897647011208 | DESEMPENADEIRA LISA  ACO TEMPERADO 12X29CM | Ferramentas | compra_nf | - | manual SEM NF/CUPOM / sem_comprovacao | manual SEM NF/CUPOM | - | finance:sem_comprovacao, nf_sem_chave |
| 7899874566540020 | PICARETA | Ferramentas | compra_nf | - | manual SEM NF/CUPOM / sem_comprovacao | manual SEM NF/CUPOM | - | finance:sem_comprovacao, nf_sem_chave |
| 7896257584119 | GRAFFIATO BRANCO NEVE 25KG | Mat. Pintura e Drywall | NF | 048259 | nf 048259 / sem_comprovacao | nf 048259 | - | finance:sem_comprovacao, nf_sem_chave |
| 7898255670726 | ALL CLEAN SABONETE ESPUMA 5L | Materiais de Limpeza | NF | 000090740 | nf 000090740 / comprovado | nf 000090740 | - | nf_sem_chave |
| 7898255672140 | BUTTERFLY  LIMPA-VIDRO VIDRAX 5L | Materiais de Limpeza | - | 000090740 | nf 000090740 / comprovado | nf 000090740 | - | nf_sem_chave |
| 7898255671037 | CONCENTRAX DESENGRAXRAX 5L | Materiais de Limpeza | - | 000090740 | nf 000090740 / comprovado | nf 000090740 | - | nf_sem_chave |
| 7897534802032 | DESINCRUSTANTE LIMPA REJUNTES 5L | Materiais de Limpeza | - | 000090740 | nf 000090740 / comprovado | nf 000090740 | - | nf_sem_chave |
| 7898255671327 | MAX DESINFETANTE 5L | Materiais de Limpeza | - | 000090740 | nf 000090740 / comprovado | nf 000090740 | - | nf_sem_chave |
| 7898255670818 | MAX DETERGENTE 5L | Materiais de Limpeza | - | 000090740 | nf 000090740 / comprovado | nf 000090740 | - | nf_sem_chave |
| 78998745600388 | RODO LIMPA VIDROS C/CABO 25CM | Materiais de Limpeza | NF | 000090740 | nf 000090740 / comprovado | nf 000090740 | - | nf_sem_chave |
| 7899682733107 | UPPRO EXPERT LIMPADOR MULTIUSO OX2 5L | Materiais de Limpeza | - | 000090740 | nf 000090740 / comprovado | nf 000090740 | - | nf_sem_chave |
| 000700070019 | TAMPAO DE ESGOTO REFORCADO | Material Construcao | NF | 17558 | nf 17558 / comprovado | nf 17558 | - | nf_sem_chave |
| 7891117006961 | ADAPT. TORNEIRA FEMEA 3/4 PARA 1/2 | Material Hidraulico | compra_nf | 2340725 | nf 2340725 / comprovado | nf 2340725 | - | nf_sem_chave |
| 7891117043478 | ENGATE RAPIDO 5/8 E 3/4 | Material Hidraulico | compra_nf | 2340725 | nf 2340725 / comprovado | nf 2340725 | - | nf_sem_chave |
| 7891117006992 | ESGUICHO REGULAVEL | Material Hidraulico | compra_nf | 2340725 | nf 2340725 / comprovado | nf 2340725 | - | nf_sem_chave |
| 7898542184028 | MANGUEIRA  TRANCADA 3/4 | Material Hidraulico | compra_nf | 2340725 | nf 2340725 / comprovado | nf 2340725 | - | nf_sem_chave |
| 7899452032119 | LAMPADA PERA 6.5K 6W 60W LUZ FRIA | Material Eletrico | compra_nf | 2323448 | - | manual 2323448; nf 2323448 | ok | sem_finance_lancamento |
| 7892022010432 | ARANDELA LED SOLAR | Material Eletrico | compra_nf | 7892022010432 | - | manual 7892022010432 | - | sem_finance_lancamento, nf_sem_chave |
| 7897432701123 | FITA TESTE | Material Piscina | compra_nf | 002998 | - | manual 002998 | - | sem_finance_lancamento, nf_sem_chave |
| 7898615542649 | ABRACADEIRA 300X3,6mm NYLON | Material/Uso geral | compra_nf | - | - | manual SEM NF/CUPOM | - | sem_finance_lancamento, nf_sem_chave |